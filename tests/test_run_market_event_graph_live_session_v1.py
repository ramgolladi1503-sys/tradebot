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
    monkeypatch.setattr(session.cfg, "LOCKS_ROOT", str(lock_root), raising=False)
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
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["allowed_for_live_execution"] is False
    assert not output_root.exists()


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
    else:
        assert payload["verdict"] == "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
        assert payload["production_token_count"] == 0
        assert payload["allowed_for_live_execution"] is False


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
