from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from aixion_trade_intelligence.storage import load_events
from aixion_trade_intelligence.quality import VALID, validate_session


def _row():
    return {"timestamp": "2026-08-04T09:45:00+00:00", "ts_epoch": 1785836700.0, "cycle_id": "cycle-1", "mode": "live", "underlying": "NIFTY", "strategy_name": "trend_pullback", "candidate_id": "cand-1", "stage": "phase2", "stage_status": "blocked", "block_reason": "STALE_OPTION_TICK", "stale_quote": True, "executable": False}


def test_observer_converts_existing_candidate_lineage_once(tmp_path: Path):
    lineage = tmp_path / "candidate_funnel.jsonl"; output = tmp_path / "events.jsonl"; lineage.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/run_tradebot_intelligence_observer.py", "--lineage", str(lineage), "--output", str(output), "--session-id", "observer-test-session", "--once"], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)["source_rows_observed"] == 1
    events = load_events(output); assert [event.event_type for event in events] == ["SESSION_STARTED", "CANDIDATE_BLOCKED", "SESSION_ENDED"]
    manifest = validate_session(events); assert manifest.verdict == VALID
    assert manifest.reconciled_counts == {"aixion-live-observer": True, "tradebot-candidate-lineage": True}


def test_observer_can_defer_session_finalization(tmp_path: Path):
    lineage = tmp_path / "candidate_funnel.jsonl"; output = tmp_path / "events.jsonl"; lineage.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "scripts/run_tradebot_intelligence_observer.py", "--lineage", str(lineage), "--output", str(output), "--session-id", "observer-deferred-session", "--once", "--defer-finalization"], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    events = load_events(output); assert [event.event_type for event in events] == ["SESSION_STARTED", "CANDIDATE_BLOCKED", "OBSERVER_STOPPED"]
    assert not any(event.event_type == "SESSION_ENDED" for event in events)


def test_observer_preserves_valid_session_analytics_contract(tmp_path: Path):
    lineage = tmp_path / "candidate_funnel.jsonl"; output = tmp_path / "events.jsonl"; contract = tmp_path / "contract.json"
    lineage.write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    contract.write_text(json.dumps({"analytics_contract": {"index_instrument": "NSE_INDEX|Nifty 50", "required_metrics": ["index_path"]}}), encoding="utf-8")
    subprocess.run([sys.executable, "scripts/run_tradebot_intelligence_observer.py", "--lineage", str(lineage), "--output", str(output), "--session-id", "observer-contract-session", "--session-contract", str(contract), "--once", "--defer-finalization"], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    assert load_events(output)[0].payload["analytics_contract"]["index_instrument"] == "NSE_INDEX|Nifty 50"


def test_observer_rejects_contract_that_overrides_owned_fields(tmp_path: Path):
    lineage = tmp_path / "candidate_funnel.jsonl"; output = tmp_path / "events.jsonl"; contract = tmp_path / "contract.json"
    lineage.write_text("", encoding="utf-8"); contract.write_text(json.dumps({"observer_mode": "MUTATE"}), encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/run_tradebot_intelligence_observer.py", "--lineage", str(lineage), "--output", str(output), "--session-id", "observer-bad-contract", "--session-contract", str(contract), "--once"], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
    assert result.returncode != 0; assert "observer-owned fields" in (result.stderr + result.stdout)
