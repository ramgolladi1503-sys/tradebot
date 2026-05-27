from __future__ import annotations

import json

from core.strategy_suspension_retirement_rules import (
    INVALID_LIFECYCLE_REPORT_REASON,
    INVALID_RULE_POLICY_REASON,
    LIFECYCLE_NOT_SUSPEND_OR_RETIRE_CANDIDATE_REASON,
    LOW_RETIREMENT_SAMPLE_REASON,
    LOW_SUSPENSION_SAMPLE_REASON,
    NO_LIFECYCLE_STATES_REASON,
    NON_NEGATIVE_EXPECTANCY_REVIEW_REASON,
    RETIRE_CANDIDATE_RULE_READY_REASON,
    RULE_DECISION_NO_ACTION,
    RULE_DECISION_RETIREMENT_CANDIDATE,
    RULE_DECISION_REVIEW_REQUIRED,
    RULE_DECISION_SUSPENSION_CANDIDATE,
    STRATEGY_SUSPENSION_RETIREMENT_BLOCKED,
    STRATEGY_SUSPENSION_RETIREMENT_EVALUATED,
    STRATEGY_SUSPENSION_RETIREMENT_SOURCE,
    SUSPEND_CANDIDATE_RULE_READY_REASON,
    build_strategy_suspension_retirement_report,
)


def _state(
    *,
    family: str = "zero_hero",
    lifecycle_state: str = "SUSPEND_CANDIDATE",
    closed_count: int = 12,
    expectancy: float = -12.5,
    win_rate: float = 0.35,
    sample_ok: bool = True,
    requires_review: bool = True,
    reason_code: str = "kill_family_suspend_candidate",
) -> dict:
    return {
        "strategy_family": family,
        "lifecycle_state": lifecycle_state,
        "reason_code": reason_code,
        "reasons": [reason_code],
        "source_recommendation": "KILL",
        "strategy_ids": [f"{family}_v1"],
        "regimes": ["EXPIRY"],
        "closed_count": closed_count,
        "net_expectancy_per_trade": expectancy,
        "net_win_rate": win_rate,
        "sample_ok": sample_ok,
        "eligible_for_promotion": False,
        "requires_review": requires_review,
        "promotion_applied": False,
        "suspension_applied": False,
        "retirement_applied": False,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def _lifecycle_report(states: list[dict], *, status: str = "STRATEGY_LIFECYCLE_REDUCED") -> dict:
    return {
        "schema_version": 1,
        "source": "strategy_lifecycle_states_v1",
        "status": status,
        "read_only": True,
        "append": False,
        "states": states,
    }


def test_suspension_retirement_rules_marks_suspend_candidate_ready():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report([_state(lifecycle_state="SUSPEND_CANDIDATE", closed_count=12, expectancy=-10.0)]),
        suspension_min_closed_trades=10,
    ).to_payload()

    assert payload["status"] == STRATEGY_SUSPENSION_RETIREMENT_EVALUATED
    assert payload["family_count"] == 1
    assert payload["suspension_candidate_count"] == 1
    decision = payload["decisions"][0]
    assert decision["decision"] == RULE_DECISION_SUSPENSION_CANDIDATE
    assert decision["reason_code"] == SUSPEND_CANDIDATE_RULE_READY_REASON
    assert decision["suspension_ready"] is True
    assert decision["retirement_ready"] is False
    assert decision["suspension_applied"] is False
    assert decision["lifecycle_state_mutated"] is False


def test_suspension_retirement_rules_marks_retired_candidate_ready():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report(
            [
                _state(
                    family="mean_reversion",
                    lifecycle_state="RETIRED_CANDIDATE",
                    closed_count=35,
                    expectancy=-18.0,
                    reason_code="kill_family_retired_candidate",
                )
            ]
        ),
        retirement_min_closed_trades=30,
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["retirement_candidate_count"] == 1
    assert decision["decision"] == RULE_DECISION_RETIREMENT_CANDIDATE
    assert decision["reason_code"] == RETIRE_CANDIDATE_RULE_READY_REASON
    assert decision["retirement_ready"] is True
    assert decision["suspension_ready"] is False
    assert decision["retirement_applied"] is False
    assert decision["lifecycle_state_mutated"] is False


def test_suspension_retirement_rules_no_action_for_active_eligible():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report(
            [
                _state(
                    family="breakout",
                    lifecycle_state="ACTIVE_ELIGIBLE",
                    closed_count=40,
                    expectancy=25.0,
                    reason_code="keep_family_active_eligible",
                )
            ]
        )
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["no_action_count"] == 1
    assert decision["decision"] == RULE_DECISION_NO_ACTION
    assert decision["reason_code"] == LIFECYCLE_NOT_SUSPEND_OR_RETIRE_CANDIDATE_REASON
    assert decision["suspension_ready"] is False
    assert decision["retirement_ready"] is False


def test_suspension_rule_requires_review_for_low_sample():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report([_state(lifecycle_state="SUSPEND_CANDIDATE", closed_count=3, expectancy=-5.0)]),
        suspension_min_closed_trades=10,
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["review_required_count"] == 1
    assert decision["decision"] == RULE_DECISION_REVIEW_REQUIRED
    assert decision["reason_code"] == LOW_SUSPENSION_SAMPLE_REASON
    assert decision["suspension_ready"] is False


def test_retirement_rule_requires_review_for_low_sample():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report([_state(lifecycle_state="RETIRED_CANDIDATE", closed_count=12, expectancy=-5.0)]),
        retirement_min_closed_trades=30,
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["review_required_count"] == 1
    assert decision["decision"] == RULE_DECISION_REVIEW_REQUIRED
    assert decision["reason_code"] == LOW_RETIREMENT_SAMPLE_REASON
    assert decision["retirement_ready"] is False


def test_suspension_rule_requires_review_for_non_negative_expectancy():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report([_state(lifecycle_state="SUSPEND_CANDIDATE", closed_count=20, expectancy=0.0)]),
        suspension_min_closed_trades=10,
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["review_required_count"] == 1
    assert decision["decision"] == RULE_DECISION_REVIEW_REQUIRED
    assert decision["reason_code"] == NON_NEGATIVE_EXPECTANCY_REVIEW_REASON
    assert decision["suspension_ready"] is False


def test_suspension_retirement_rules_blocks_invalid_lifecycle_report():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report([_state()], status="STRATEGY_LIFECYCLE_BLOCKED")
    ).to_payload()

    assert payload["status"] == STRATEGY_SUSPENSION_RETIREMENT_BLOCKED
    assert payload["reason_code"] == INVALID_LIFECYCLE_REPORT_REASON
    assert payload["lifecycle_report_valid"] is False
    assert payload["decisions"] == []


def test_suspension_retirement_rules_blocks_empty_lifecycle_states():
    payload = build_strategy_suspension_retirement_report(_lifecycle_report([])).to_payload()

    assert payload["status"] == STRATEGY_SUSPENSION_RETIREMENT_BLOCKED
    assert payload["reason_code"] == NO_LIFECYCLE_STATES_REASON
    assert payload["lifecycle_report_valid"] is True
    assert payload["decisions"] == []


def test_suspension_retirement_rules_blocks_invalid_policy():
    payload = build_strategy_suspension_retirement_report(
        _lifecycle_report([_state()]),
        suspension_min_closed_trades=40,
        retirement_min_closed_trades=30,
    ).to_payload()

    assert payload["status"] == STRATEGY_SUSPENSION_RETIREMENT_BLOCKED
    assert payload["reason_code"] == INVALID_RULE_POLICY_REASON
    assert payload["decisions"] == []


def test_suspension_retirement_payload_is_json_serializable_and_non_action():
    report = build_strategy_suspension_retirement_report(_lifecycle_report([_state()]))
    payload = report.to_payload()
    encoded = report.to_json()

    assert json.loads(encoded)["source"] == STRATEGY_SUSPENSION_RETIREMENT_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["policy"]["is_order_action"] is False
    assert payload["decisions"][0]["is_order_action"] is False
    assert payload["decisions"][0]["broker_api_called"] is False
    assert payload["decisions"][0]["suspension_applied"] is False
    assert payload["decisions"][0]["retirement_applied"] is False
    assert payload["decisions"][0]["lifecycle_state_mutated"] is False
