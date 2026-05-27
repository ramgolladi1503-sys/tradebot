import json

from core.regime_replay_scenarios import (
    INVALID_SNAPSHOT_REASON,
    REGIME_EXPECTATION_MISMATCH_REASON,
    REGIME_REPLAY_BLOCKED,
    REGIME_REPLAY_FAILED,
    REGIME_REPLAY_PASSED,
    REGIME_REPLAY_SOURCE,
    REGIME_STEP_BLOCKED_REASON,
    TRANSITION_EXPECTATION_MISMATCH_REASON,
    RegimeReplayScenario,
    RegimeReplayStep,
    build_regime_replay_report,
    default_regime_replay_scenarios,
)


def test_default_regime_replay_scenarios_pass_with_non_action_flags():
    report = build_regime_replay_report()
    payload = report.to_payload()

    assert payload["status"] == REGIME_REPLAY_PASSED
    assert payload["source"] == REGIME_REPLAY_SOURCE
    assert payload["scenario_count"] == 2
    assert payload["passed_scenario_count"] == 2
    assert payload["failed_scenario_count"] == 0
    assert payload["blocked_scenario_count"] == 0
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False

    first = payload["results"][0]
    assert first["scenario_id"] == "opening_uptrend_to_midday_range"
    assert first["actual_transition_count"] == 1
    assert first["transition_count_ok"] is True
    assert first["first_regime_id"] == "UP_HIGH_BULLISH_DEEP_OPENING"
    assert first["terminal_regime_id"] == "SIDEWAYS_LOW_MIXED_NORMAL_MIDDAY"
    assert first["transitions"][0]["changed"] is True
    assert first["transitions"][0]["is_order_action"] is False


def test_regime_replay_accepts_mapping_scenario_and_detects_dimension_mismatch():
    scenario = default_regime_replay_scenarios()[0].to_payload()
    scenario["steps"][0]["expected_dimensions"]["trend"] = "DOWN"

    report = build_regime_replay_report([scenario])
    payload = report.to_payload()

    assert payload["status"] == REGIME_REPLAY_FAILED
    assert payload["reason_code"] == REGIME_EXPECTATION_MISMATCH_REASON
    result = payload["results"][0]
    assert result["status"] == "FAILED"
    assert result["failed_step_count"] == 1
    assert result["steps"][0]["reason_code"] == REGIME_EXPECTATION_MISMATCH_REASON
    assert result["steps"][0]["dimension_mismatches"] == ["trend"]


def test_regime_replay_blocks_invalid_snapshot_fail_closed():
    scenario = RegimeReplayScenario(
        scenario_id="bad_snapshot",
        description="Invalid snapshot must not be silently accepted.",
        steps=(
            {"step_id": "missing_snapshot", "snapshot": None},
        ),
    )

    report = build_regime_replay_report([scenario])
    payload = report.to_payload()

    assert payload["status"] == REGIME_REPLAY_BLOCKED
    assert payload["reason_code"] == REGIME_STEP_BLOCKED_REASON
    result = payload["results"][0]
    assert result["status"] == "BLOCKED"
    assert result["blocked_step_count"] == 1
    assert result["steps"][0]["reason_code"] == INVALID_SNAPSHOT_REASON
    assert result["steps"][0]["regime_id"] == "UNKNOWN"


def test_regime_replay_detects_transition_count_mismatch():
    scenario = default_regime_replay_scenarios()[0].to_payload()
    scenario["expected_transition_count"] = 0

    report = build_regime_replay_report([scenario])
    payload = report.to_payload()

    assert payload["status"] == REGIME_REPLAY_FAILED
    result = payload["results"][0]
    assert result["reason_code"] == TRANSITION_EXPECTATION_MISMATCH_REASON
    assert result["actual_transition_count"] == 1
    assert result["expected_transition_count"] == 0
    assert result["transition_count_ok"] is False


def test_regime_replay_blocks_when_market_state_has_insufficient_evidence():
    scenario = RegimeReplayScenario(
        scenario_id="insufficient_market_state_evidence",
        description="Missing dimensions should block replay evidence.",
        steps=(
            RegimeReplayStep(
                step_id="empty_snapshot",
                snapshot={},
                expected_regime_id="UP_HIGH_BULLISH_DEEP_OPENING",
            ),
        ),
    )

    report = build_regime_replay_report([scenario])
    payload = report.to_payload()

    assert payload["status"] == REGIME_REPLAY_BLOCKED
    step = payload["results"][0]["steps"][0]
    assert step["status"] == "BLOCKED"
    assert step["regime_id"] == "UNKNOWN"
    assert "market_state_insufficient_evidence" in step["blockers"]


def test_regime_replay_to_json_is_serializable():
    report = build_regime_replay_report()
    payload = json.loads(report.to_json())

    assert payload["source"] == REGIME_REPLAY_SOURCE
    assert payload["status"] == REGIME_REPLAY_PASSED
    assert payload["metadata"]["evidence_only"] is True
