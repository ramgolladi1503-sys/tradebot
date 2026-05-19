from __future__ import annotations

import pytest

from core.paper_session_gate import (
    SESSION_GATE_FAIL,
    SESSION_GATE_PASS,
    PaperSessionGateError,
    build_paper_session_gate_report,
)


def _snapshot(**overrides):
    payload = {
        "session_id": "paper-session-1",
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


def test_clean_full_session_passes_gate():
    report = build_paper_session_gate_report(_snapshot())

    assert report.state == SESSION_GATE_PASS
    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.broker_order_action is False
    assert report.live_order_action is False
    assert report.session_id == "paper-session-1"
    assert report.feed_uptime_pct == 99.5
    assert report.paper_order_count == 3
    assert report.paper_fill_count == 2
    assert report.realized_pnl == 125.5
    assert report.blockers == ()
    assert report.reasons == ("paper_session_met_full_session_gate",)


def test_missing_snapshot_fails_closed_with_required_evidence_blockers():
    report = build_paper_session_gate_report(None)

    assert report.state == SESSION_GATE_FAIL
    assert "SESSION_SNAPSHOT_MISSING" in report.blockers
    assert "SESSION_ID_MISSING" in report.blockers
    assert "EVIDENCE_COMPLETE_MISSING" in report.blockers
    assert "CRASH_LOOP_SIGNAL_MISSING" in report.blockers
    assert "FEED_UPTIME_PCT_MISSING" in report.blockers
    assert "PAPER_FILL_COUNT_MISSING" in report.blockers


def test_fallback_stale_unresolved_and_missing_evidence_fills_fail_gate():
    report = build_paper_session_gate_report(
        _snapshot(
            fallback_paper_fill_count=1,
            stale_feed_paper_fill_count=1,
            unresolved_contract_paper_fill_count=1,
            missing_evidence_trade_count=1,
        )
    )

    assert report.state == SESSION_GATE_FAIL
    assert "FALLBACK_PAPER_FILLS_PRESENT" in report.blockers
    assert "STALE_FEED_PAPER_FILLS_PRESENT" in report.blockers
    assert "UNRESOLVED_CONTRACT_PAPER_FILLS_PRESENT" in report.blockers
    assert "MISSING_EVIDENCE_TRADES_PRESENT" in report.blockers


def test_feed_stability_thresholds_fail_gate():
    report = build_paper_session_gate_report(
        _snapshot(
            feed_uptime_pct=91.0,
            stale_feed_duration_sec=121.0,
            ws_disconnect_count=4,
            restart_count=2,
        )
    )

    assert report.state == SESSION_GATE_FAIL
    assert "FEED_UPTIME_BELOW_MIN" in report.blockers
    assert "STALE_FEED_DURATION_EXCEEDED" in report.blockers
    assert "WS_DISCONNECT_LIMIT_EXCEEDED" in report.blockers
    assert "RESTART_LIMIT_EXCEEDED" in report.blockers


def test_crash_loop_and_incomplete_evidence_fail_gate():
    report = build_paper_session_gate_report(_snapshot(crash_loop_detected=True, evidence_complete=False))

    assert report.state == SESSION_GATE_FAIL
    assert "CRASH_LOOP_DETECTED" in report.blockers
    assert "EVIDENCE_INCOMPLETE" in report.blockers


def test_unsafe_action_flags_fail_gate():
    for flag, blocker in [
        ("broker_order_action", "SESSION_SNAPSHOT_BROKER_ORDER_ACTION_REJECTED"),
        ("live_order_action", "SESSION_SNAPSHOT_LIVE_ORDER_ACTION_REJECTED"),
        ("is_order_action", "SESSION_SNAPSHOT_ORDER_ACTION_REJECTED"),
        ("append", "SESSION_SNAPSHOT_APPEND_TRUE_REJECTED"),
    ]:
        report = build_paper_session_gate_report(_snapshot(**{flag: True}))
        assert report.state == SESSION_GATE_FAIL
        assert blocker in report.blockers


def test_invalid_counts_and_relationships_fail_gate():
    report = build_paper_session_gate_report(
        _snapshot(
            candidate_count=2,
            paper_order_count=3,
            paper_fill_count=4,
            paper_rejection_count=-1,
        )
    )

    assert report.state == SESSION_GATE_FAIL
    assert "PAPER_REJECTION_COUNT_NEGATIVE" in report.blockers
    assert "PAPER_FILLS_EXCEED_PAPER_ORDERS" in report.blockers
    assert "PAPER_ORDERS_EXCEED_CANDIDATES" in report.blockers


def test_no_candidates_or_fills_warns_but_does_not_fail_by_itself():
    report = build_paper_session_gate_report(
        _snapshot(
            candidate_count=0,
            paper_order_count=0,
            paper_fill_count=0,
            paper_rejection_count=0,
        )
    )

    assert report.state == SESSION_GATE_PASS
    assert "NO_CANDIDATES_OBSERVED" in report.warnings
    assert "NO_PAPER_FILLS_OBSERVED" in report.warnings


def test_custom_thresholds_are_applied():
    report = build_paper_session_gate_report(
        _snapshot(feed_uptime_pct=98.0, stale_feed_duration_sec=61.0, max_drawdown=-101.0),
        thresholds={
            "min_feed_uptime_pct": 99.0,
            "max_stale_feed_duration_sec": 60.0,
            "max_drawdown_abs": 100.0,
        },
    )

    assert report.state == SESSION_GATE_FAIL
    assert "FEED_UPTIME_BELOW_MIN" in report.blockers
    assert "STALE_FEED_DURATION_EXCEEDED" in report.blockers
    assert "MAX_DRAWDOWN_EXCEEDED" in report.blockers


def test_invalid_thresholds_raise_configuration_error():
    with pytest.raises(PaperSessionGateError) as exc_info:
        build_paper_session_gate_report(_snapshot(), thresholds={"min_feed_uptime_pct": 101.0})

    assert "min_feed_uptime_pct_invalid" in str(exc_info.value)


def test_to_dict_is_json_friendly_and_stable():
    report = build_paper_session_gate_report(_snapshot())
    payload = report.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == SESSION_GATE_PASS
    assert payload["session_id"] == "paper-session-1"
    assert payload["pass_criteria"]["requires_zero_fallback_paper_fills"] is True
    assert payload["blockers"] == []
    assert payload["metadata"]["gate"] == "paper_session_gate_v1"
    assert payload["metadata"]["scope"] == "read_only_no_runtime_wiring_no_broker_calls_no_order_mutation_no_persistence"
