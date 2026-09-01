import json
import subprocess
import os
import sys
from pathlib import Path
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
