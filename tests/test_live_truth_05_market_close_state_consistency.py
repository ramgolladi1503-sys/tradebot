from __future__ import annotations

import json

from core.live_truth_market_close_state_consistency import (
    CLOSE_STATE_OK_REASON,
    EXECUTABLES_NOT_ZERO_REASON,
    FEED_MARKET_OPEN_CONFLICT_REASON,
    HIGH_FREQUENCY_LOOP_ACTIVE_REASON,
    INVALID_MARKET_SNAPSHOT_REASON,
    MARKET_CLOSE_STATE_SOURCE,
    MARKET_CLOSE_STATUS_BLOCKED,
    MARKET_CLOSE_STATUS_CONSISTENT,
    MARKET_CLOSE_STATUS_INCONSISTENT,
    MARKET_CLOSE_STATUS_NOT_APPLICABLE,
    MARKET_OPEN_TRUE_REASON,
    MISSING_MARKET_OPEN_REASON,
    RUNTIME_HEALTH_NOT_QUIET_REASON,
    SOURCE_CANDIDATES_NOT_QUIET_REASON,
    TOP_MARKET_STATE_MISSING_REASON,
    TOP_MARKET_STATE_NOT_CLOSED_REASON,
    build_market_close_state_consistency_report,
    write_market_close_state_consistency_evidence,
)


def test_reports_consistent_when_market_closed_and_artifacts_are_quiet():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={
            "market_state": "MARKET_CLOSED",
            "source_candidate_count": 0,
            "executable_count": 0,
        },
        runtime_health={"runtime_state": "OFFHOURS", "quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_CONSISTENT
    assert payload["reason_code"] == CLOSE_STATE_OK_REASON
    assert payload["violation_count"] == 0
    assert payload["expected_market_state"] == "MARKET_CLOSED/OFFHOURS"


def test_not_applicable_when_market_is_open():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": True},
        feed_runtime={"market_open": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_NOT_APPLICABLE
    assert payload["reason_code"] == MARKET_OPEN_TRUE_REASON
    assert payload["expected_market_state"] == "MARKET_OPEN"


def test_blocks_invalid_market_snapshot():
    payload = build_market_close_state_consistency_report(
        market_snapshot=["bad"],
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_MARKET_SNAPSHOT_REASON


def test_blocks_missing_market_open_flag():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"source": "market_snapshot"},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_BLOCKED
    assert payload["reason_code"] == MISSING_MARKET_OPEN_REASON


def test_flags_feed_market_open_conflict_without_freshness_warning():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": True},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert FEED_MARKET_OPEN_CONFLICT_REASON in payload["reasons"]
    assert payload["feed_freshness_warning_present"] is False


def test_allows_feed_market_open_conflict_when_freshness_warning_is_present():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": True, "freshness_warning": "stale feed_runtime market_open value"},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_CONSISTENT
    assert payload["feed_freshness_warning_present"] is True


def test_flags_missing_top_opportunities_market_state():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert TOP_MARKET_STATE_MISSING_REASON in payload["reasons"]


def test_flags_normal_no_trade_state_after_close():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "NO_TRADE", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert TOP_MARKET_STATE_NOT_CLOSED_REASON in payload["reasons"]


def test_flags_source_candidate_count_after_close_when_offhours_planning_disabled():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "OFFHOURS_BLOCKED", "source_candidate_count": 4, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert SOURCE_CANDIDATES_NOT_QUIET_REASON in payload["reasons"]


def test_allows_source_candidate_count_when_offhours_planning_enabled():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={
            "market_state": "OFFHOURS_BLOCKED",
            "source_candidate_count": 4,
            "executable_count": 0,
            "offhours_planning_enabled": True,
        },
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_CONSISTENT
    assert payload["offhours_planning_enabled"] is True


def test_flags_executable_count_after_close():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 1},
        runtime_health={"quiet_mode": True},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert EXECUTABLES_NOT_ZERO_REASON in payload["reasons"]


def test_flags_runtime_health_not_quiet():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"runtime_state": "RUNNING"},
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert RUNTIME_HEALTH_NOT_QUIET_REASON in payload["reasons"]


def test_flags_high_frequency_loop_after_close():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True, "slo_loop_frequency_hz": 2.0},
        max_offhours_loop_frequency_hz=0.2,
    ).to_payload()

    assert payload["status"] == MARKET_CLOSE_STATUS_INCONSISTENT
    assert HIGH_FREQUENCY_LOOP_ACTIVE_REASON in payload["reasons"]
    assert payload["high_frequency_loop_active"] is True


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "market_close_state_consistency_latest.json"
    report = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    )

    out = write_market_close_state_consistency_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == MARKET_CLOSE_STATE_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_payload_is_json_serializable_and_non_action():
    payload = build_market_close_state_consistency_report(
        market_snapshot={"market_open": False},
        feed_runtime={"market_open": False},
        top_opportunities={"market_state": "MARKET_CLOSED", "source_candidate_count": 0, "executable_count": 0},
        runtime_health={"quiet_mode": True},
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == MARKET_CLOSE_STATE_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
    assert decoded["is_order_action"] is False
    assert decoded["broker_api_called"] is False
    assert decoded["live_order_action"] is False
    assert decoded["broker_order_action"] is False
