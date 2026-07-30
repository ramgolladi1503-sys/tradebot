import json
import subprocess
import os
import sys
from pathlib import Path


def test_session_orchestrator_preflight_only_resolves_contract_path(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    assert script.is_file(), f"expected orchestrator missing: {script}"
    master = repo_root / "runtime/reference/market_event_graph/kite_instruments/kite_nse_instruments_828c0c378e493972.json"
    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", "2026-07-30", "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--preflight-only"],
        check=True,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )

    payload = json.loads(result.stdout)
    assert payload["session_date"] == "2026-07-30"
    assert payload["observed_token_count"] == 51
    assert payload["contract_path"].endswith(".json")


def test_session_orchestrator_ignores_hostile_parent_argv(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"
    master = repo_root / "runtime/reference/market_event_graph/kite_instruments/kite_nse_instruments_828c0c378e493972.json"
    monkeypatch.setattr(sys, "argv", ["poison", "--output-dir", "/tmp/poison", "--kite-instruments-file", "wrong.json"])
    env = dict(os.environ)
    env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] = "true"
    env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--session-date", "2026-07-30", "--output-root", str(tmp_path), "--kite-instruments-file", str(master), "--preflight-only"],
        check=True,
        capture_output=True,
        text=True,
        env=env, cwd=repo_root,
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["reason"] == "OK"
    assert payload["configured_budget"] == 150
