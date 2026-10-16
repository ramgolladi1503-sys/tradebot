import json
import subprocess
import os
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from core.daily_instrument_authority import produce_authority

def authority_args(repo_root, master, tmp_path, session_date="2026-07-30"):
    contract = json.loads((repo_root / "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json").read_text())
    out = tmp_path / "authority.json"
    produce_authority(master_path=master, output_path=out, session_date=session_date, source_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(), required_tokens=[int(contract["index_instrument_token"])] + [int(x["instrument_token"]) for x in contract["constituents"]], reviewed_pass=True)
    return ["--authority-artifact", str(out)]

def make_test_master(repo_root, tmp_path):
    contract = json.loads((repo_root / "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json").read_text())
    rows = [{"exchange":"NSE","instrument_token":int(contract["index_instrument_token"]),"tradingsymbol":"NIFTY 50","segment":"INDICES","instrument_type":"EQ","expiry":"","lot_size":1,"tick_size":0.05,"strike":0}]
    rows += [{"exchange":"NSE","instrument_token":int(x["instrument_token"]),"tradingsymbol":x["symbol"],"segment":"NSE","instrument_type":"EQ","expiry":"","lot_size":1,"tick_size":0.05,"strike":0} for x in contract["constituents"]]
    path = tmp_path / "master.json"; path.write_text(json.dumps(rows)); return path


def test_session_orchestrator_preflight_only_resolves_contract_path(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    assert script.is_file(), f"expected orchestrator missing: {script}"
    master = make_test_master(repo_root, tmp_path)
    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    env["LOCKS_ROOT"] = str(tmp_path / "locks")
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", "2026-07-30", "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--preflight-only", *authority_args(repo_root, master, tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["session_date"] == "2026-07-30"
    assert payload["observed_token_count"] == 51
    assert payload["contract_path"].endswith(".json")
    assert payload["verdict"] == "PASS_STATIC_LIVE_SOURCE_PREFLIGHT"
    assert payload["broker_api_called"] is False
    assert not (tmp_path / "locks" / "meg_read_only_observation.lock").exists()


def test_active_observation_lock_blocks_before_capture_directory_creation(monkeypatch, tmp_path, capsys):
    from scripts import run_market_event_graph_live_session_v1 as session

    lock_root = tmp_path / "locks"
    monkeypatch.setattr(session.reliability_cfg, "MEG_OBSERVATION_LOCKS_ROOT", str(lock_root), raising=False)
    owner = session._new_observation_session_lock()
    acquired, _ = owner.acquire()
    assert acquired is True
    output_root = tmp_path / "captures"
    args = Namespace(output_root=output_root, authority_artifact=tmp_path / "authority.json")

    try:
        result = session._run_observation_capture(
            args=args,
            session_date="2026-07-30",
            registry=SimpleNamespace(canonical_sha256="registry", contract_path="contract.json"),
            master_path=tmp_path / "master.json",
            master_sha="master-sha",
            broker_metadata_called=False,
            launch_plan={"launch_plan_sha256": "plan-sha"},
        )
    finally:
        owner.release()

    payload = json.loads(capsys.readouterr().out.strip())
    assert result == 2
    assert payload["verdict"] == "BLOCKED_BY_OBSERVATION_SESSION_ALREADY_ACTIVE"
    assert payload["lock_path"] == str((lock_root / "meg_read_only_observation.lock").resolve())
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["allowed_for_live_execution"] is False
    assert not output_root.exists()


def test_observation_lock_defaults_to_one_path_across_checkout_roots(monkeypatch, tmp_path):
    from scripts import run_market_event_graph_live_session_v1 as session

    monkeypatch.delenv("MEG_OBSERVATION_LOCKS_ROOT", raising=False)
    monkeypatch.delenv("LOCKS_ROOT", raising=False)
    monkeypatch.setattr(session.reliability_cfg, "MEG_OBSERVATION_LOCKS_ROOT", str(Path.home() / ".tradebot" / "locks"), raising=False)
    first_checkout = tmp_path / "checkout-a"
    second_checkout = tmp_path / "checkout-b"

    monkeypatch.setattr(session, "REPO_ROOT", first_checkout)
    first = session._new_observation_session_lock()
    monkeypatch.setattr(session, "REPO_ROOT", second_checkout)
    second = session._new_observation_session_lock()

    assert first.lock_path == second.lock_path
    assert first.lock_path == (Path.home() / ".tradebot" / "locks" / "meg_read_only_observation.lock").resolve()
    acquired, _ = first.acquire()
    assert acquired is True
    blocked, holder = second.acquire()
    try:
        assert blocked is False
        assert holder["pid"] == os.getpid()
    finally:
        first.release()
        second.release()


def test_observation_capture_manifest_records_shared_lock_path(monkeypatch, tmp_path):
    from scripts import run_market_event_graph_live_session_v1 as session

    lock_root = tmp_path / "shared-locks"
    monkeypatch.setattr(session.reliability_cfg, "MEG_OBSERVATION_LOCKS_ROOT", str(lock_root), raising=False)
    monkeypatch.setattr(session, "_commit_sha", lambda: "test-commit")
    monkeypatch.setattr(
        session.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(args=[], returncode=0),
    )
    output_root = tmp_path / "captures"
    args = Namespace(output_root=output_root, authority_artifact=tmp_path / "authority.json")

    result = session._run_observation_capture(
        args=args,
        session_date="2026-07-30",
        registry=SimpleNamespace(canonical_sha256="registry", contract_path="contract.json"),
        master_path=tmp_path / "master.json",
        master_sha="master-sha",
        broker_metadata_called=False,
        launch_plan={"launch_plan_sha256": "plan-sha"},
    )

    manifest_path = next((output_root / "2026-07-30").glob("*/presession_manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert result == 0
    assert manifest["observation_lock_path"] == str(
        (lock_root / "meg_read_only_observation.lock").resolve()
    )
    assert manifest["read_only"] is True
    assert manifest["is_order_action"] is False
    assert manifest["broker_api_called"] is False
    assert manifest["allowed_for_live_execution"] is False


def test_session_orchestrator_ignores_hostile_parent_argv(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = make_test_master(repo_root, tmp_path)
    monkeypatch.setattr(sys, "argv", ["poison", "--output-dir", "/tmp/poison", "--kite-instruments-file", "wrong.json"])
    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", "2026-07-30", "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--preflight-only", *authority_args(repo_root, master, tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["verdict"] == "PASS_STATIC_LIVE_SOURCE_PREFLIGHT"


def test_session_orchestrator_launch_preflight_uses_production_builder_once(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = make_test_master(repo_root, tmp_path)
    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", "2026-07-30", "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--launch-preflight-only", *authority_args(repo_root, master, tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )
    assert result.returncode in {0, 2}
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    if result.returncode == 0:
        assert payload["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
        assert payload["observation_token_count"] == 51
        assert payload["final_union_count"] <= payload["configured_budget"]
        assert payload["production_token_count"] > 0
        assert payload["launch_plan_sha256"]
        production = set(payload["production_tokens"])
        observations = set(payload["observation_tokens"])
        assert production.isdisjoint(observations)
        assert set(payload["final_union_tokens"]) == production | observations
        assert payload["production_token_count"] == len(production)
    else:
        assert payload["verdict"] == "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
        assert payload["production_token_count"] == 0
        assert payload["allowed_for_live_execution"] is False


def test_production_launch_plan_forwards_t1_heritage_environment_binding(monkeypatch, tmp_path):
    """The session entrypoint hashes and round-trips configured heritage references."""
    from scripts import run_market_event_graph_live_session_v1 as session

    manifest_path = "/read-only/evidence/t1-heritage-manifest.json"
    manifest_sha256 = "a" * 64
    monkeypatch.setenv("TRADEBOT_T1_HERITAGE_MANIFEST_PATH", manifest_path)
    monkeypatch.setenv("TRADEBOT_T1_HERITAGE_MANIFEST_SHA256", manifest_sha256)

    from core import kite_depth_ws

    monkeypatch.setattr(
        kite_depth_ws,
        "build_production_subscription_tokens",
        lambda _symbols, *, max_tokens: (
            [101, 102, 103],
            [{
                "symbol": "NIFTY", "index_token": 101, "tokens": [101, 102],
                "option_count": 1, "final_option_count": 1, "option_min_required": 1,
            }],
        ),
    )
    monkeypatch.setattr(kite_depth_ws, "get_sticky_tokens", lambda: [103])
    result = session._build_production_launch_plan(
        session_date="2026-10-12",
        registry=SimpleNamespace(
            all_tokens=list(range(1000, 1051)), canonical_sha256="b" * 64
        ),
        master_sha="a" * 64,
        broker_metadata_called=False,
    )
    path = tmp_path / "launch_plan.json"
    session.write_launch_plan(path, result)
    from core.market_event_graph_live_launch_plan import load_launch_plan
    loaded = load_launch_plan(path)

    assert loaded["ok"] is True
    assert loaded["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    assert loaded["heritage_manifest_path"] == manifest_path
    assert loaded["heritage_manifest_sha256"] == manifest_sha256
    assert loaded["t1_manifest_reference_status"] == "HERITAGE_MANIFEST_REFERENCE_CONFIGURED_UNVERIFIED"
    assert loaded["read_only"] is True
    assert loaded["is_order_action"] is False
    assert loaded["broker_api_called"] is False
    assert loaded["allowed_for_live_execution"] is False


def test_session_orchestrator_allows_existing_session_directory_with_prior_runs(monkeypatch, tmp_path):
    """An existing session_date folder with prior run subdirectories must pass static preflight."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = make_test_master(repo_root, tmp_path)
    session_date = "2026-07-30"

    # Create prior run directory inside session_date directory
    prior_run_dir = tmp_path / session_date / "meg-live-2026-07-30-prevrun-123456"
    prior_run_dir.mkdir(parents=True, exist_ok=True)
    (prior_run_dir / "launch_plan.json").write_text("{}")
    (prior_run_dir / "live_observation.log").write_text("prior log")

    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", session_date, "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--preflight-only", *authority_args(repo_root, master, tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["verdict"] == "PASS_STATIC_LIVE_SOURCE_PREFLIGHT"


def test_session_orchestrator_blocks_collision_on_governed_files_at_session_root(monkeypatch, tmp_path):
    """If governed files exist directly in session_date root, static preflight must fail with BLOCKED_BY_GOVERNED_OUTPUT_COLLISION."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = make_test_master(repo_root, tmp_path)
    session_date = "2026-07-30"

    # Simulate collision by creating governed file at session root
    session_root = tmp_path / session_date
    session_root.mkdir(parents=True, exist_ok=True)
    (session_root / "launch_plan.json").write_text("{}")

    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", session_date, "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--preflight-only", *authority_args(repo_root, master, tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["verdict"] == "BLOCKED_BY_GOVERNED_OUTPUT_COLLISION"


def test_session_orchestrator_accepts_and_verifies_heritage_manifest_sha256(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = make_test_master(repo_root, tmp_path)
    session_date = "2026-07-30"

    manifest_path = tmp_path / "heritage_manifest.json"
    manifest_content = '{"session_date": "2026-07-29", "nodes": []}'
    manifest_path.write_text(manifest_content)
    import hashlib
    manifest_sha = hashlib.sha256(manifest_content.encode("utf-8")).hexdigest()

    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "--session-date",
            session_date,
            "--output-root",
            str(tmp_path),
            "--kite-instruments-file",
            str(master),
            "--heritage-manifest",
            str(manifest_path),
            "--heritage-manifest-sha256",
            manifest_sha,
            "--preflight-only",
            *authority_args(repo_root, master, tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=repo_root,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["verdict"] == "PASS_STATIC_LIVE_SOURCE_PREFLIGHT"


def test_session_orchestrator_rejects_heritage_manifest_sha256_mismatch(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = make_test_master(repo_root, tmp_path)
    session_date = "2026-07-30"

    manifest_path = tmp_path / "heritage_manifest.json"
    manifest_path.write_text('{"session_date": "2026-07-29", "nodes": []}')

    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "--session-date",
            session_date,
            "--output-root",
            str(tmp_path),
            "--kite-instruments-file",
            str(master),
            "--heritage-manifest",
            str(manifest_path),
            "--heritage-manifest-sha256",
            "invalid_sha256_digest",
            "--launch-preflight-only",
            *authority_args(repo_root, master, tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=repo_root,
    )
    assert result.returncode == 1
    assert "BLOCKED_BY_HERITAGE_MANIFEST_SHA256_MISMATCH" in result.stderr
