from __future__ import annotations

import json
from pathlib import Path

from core.paper_session_gate import SESSION_GATE_FAIL, SESSION_GATE_PASS, build_paper_session_gate_report

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper_session_gate"

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "state",
    "read_only",
    "is_order_action",
    "append",
    "broker_order_action",
    "live_order_action",
    "session_id",
    "feed_uptime_pct",
    "stale_feed_duration_sec",
    "ws_disconnect_count",
    "restart_count",
    "crash_loop_detected",
    "evidence_complete",
    "candidate_count",
    "paper_order_count",
    "paper_fill_count",
    "paper_rejection_count",
    "fallback_paper_fill_count",
    "stale_feed_paper_fill_count",
    "unresolved_contract_paper_fill_count",
    "missing_evidence_trade_count",
    "realized_pnl",
    "max_drawdown",
    "pass_criteria",
    "blockers",
    "warnings",
    "reasons",
    "metadata",
}


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _clean_snapshot(**overrides):
    payload = {
        "session_id": "paper-session-clean",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "broker_order_action": False,
        "live_order_action": False,
        "feed_uptime_pct": 99.5,
        "stale_feed_duration_sec": 10.0,
        "ws_disconnect_count": 1,
        "restart_count": 0,
        "crash_loop_detected": False,
        "evidence_complete": True,
        "candidate_count": 20,
        "paper_order_count": 3,
        "paper_fill_count": 2,
        "paper_rejection_count": 1,
        "fallback_paper_fill_count": 0,
        "stale_feed_paper_fill_count": 0,
        "unresolved_contract_paper_fill_count": 0,
        "missing_evidence_trade_count": 0,
        "realized_pnl": 125.5,
        "max_drawdown": -40.0,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_clean_session_pass_report_matches_contract_snapshot():
    report = build_paper_session_gate_report(_clean_snapshot()).to_dict()

    assert report == _load_fixture("clean_session_pass_report.json")
    assert report["state"] == SESSION_GATE_PASS


def test_unsafe_fills_fail_report_matches_contract_snapshot():
    report = build_paper_session_gate_report(
        _clean_snapshot(
            session_id="paper-session-unsafe-fills",
            fallback_paper_fill_count=1,
            stale_feed_paper_fill_count=1,
            unresolved_contract_paper_fill_count=1,
            missing_evidence_trade_count=1,
        )
    ).to_dict()

    assert report == _load_fixture("unsafe_fills_fail_report.json")
    assert report["state"] == SESSION_GATE_FAIL


def test_missing_snapshot_fail_report_matches_contract_snapshot():
    report = build_paper_session_gate_report(None).to_dict()

    assert report == _load_fixture("missing_snapshot_fail_report.json")
    assert report["state"] == SESSION_GATE_FAIL


def test_contract_snapshots_lock_required_keys_and_safety_flags():
    for fixture_name in [
        "clean_session_pass_report.json",
        "unsafe_fills_fail_report.json",
        "missing_snapshot_fail_report.json",
    ]:
        payload = _load_fixture(fixture_name)

        assert set(payload) == REQUIRED_TOP_LEVEL_KEYS
        assert payload["schema_version"] == 1
        assert payload["read_only"] is True
        assert payload["is_order_action"] is False
        assert payload["append"] is False
        assert payload["broker_order_action"] is False
        assert payload["live_order_action"] is False
        assert payload["metadata"]["gate"] == "paper_session_gate_v1"
        assert payload["metadata"]["scope"] == "read_only_no_runtime_wiring_no_broker_calls_no_order_mutation_no_persistence"


def test_contract_snapshots_lock_unsafe_fill_blockers():
    payload = _load_fixture("unsafe_fills_fail_report.json")

    assert payload["blockers"] == [
        "FALLBACK_PAPER_FILLS_PRESENT",
        "MISSING_EVIDENCE_TRADES_PRESENT",
        "STALE_FEED_PAPER_FILLS_PRESENT",
        "UNRESOLVED_CONTRACT_PAPER_FILLS_PRESENT",
    ]
    assert payload["pass_criteria"]["requires_zero_fallback_paper_fills"] is True
    assert payload["pass_criteria"]["requires_zero_stale_feed_paper_fills"] is True
    assert payload["pass_criteria"]["requires_zero_unresolved_contract_paper_fills"] is True
    assert payload["pass_criteria"]["requires_zero_missing_evidence_trades"] is True


def test_contract_snapshots_lock_missing_evidence_fail_closed_behavior():
    payload = _load_fixture("missing_snapshot_fail_report.json")

    assert "SESSION_SNAPSHOT_MISSING" in payload["blockers"]
    assert "EVIDENCE_COMPLETE_MISSING" in payload["blockers"]
    assert "CRASH_LOOP_SIGNAL_MISSING" in payload["blockers"]
    assert "FEED_UPTIME_PCT_MISSING" in payload["blockers"]
    assert "PAPER_FILL_COUNT_MISSING" in payload["blockers"]
    assert payload["state"] == SESSION_GATE_FAIL
