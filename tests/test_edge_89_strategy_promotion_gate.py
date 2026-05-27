from __future__ import annotations

import json

from core.strategy_promotion_gate import (
    ACTIVE_ELIGIBLE_PROMOTION_CANDIDATE_REASON,
    INVALID_LIFECYCLE_REPORT_REASON,
    INVALID_PROMOTION_POLICY_REASON,
    LIFECYCLE_NOT_ACTIVE_ELIGIBLE_REASON,
    LOW_PROMOTION_SAMPLE_REASON,
    LOW_WIN_RATE_REASON,
    NO_LIFECYCLE_STATES_REASON,
    NON_POSITIVE_EXPECTANCY_REASON,
    NOT_ELIGIBLE_FOR_PROMOTION_REASON,
    PROMOTION_DECISION_BLOCKED,
    PROMOTION_DECISION_CANDIDATE,
    PROMOTION_DECISION_REVIEW,
    PROMOTION_REVIEW_REQUIRED_REASON,
    STRATEGY_PROMOTION_GATE_BLOCKED,
    STRATEGY_PROMOTION_GATE_EVALUATED,
    STRATEGY_PROMOTION_GATE_SOURCE,
    build_strategy_promotion_gate_report,
)


def _state(
    *,
    family: str = "breakout",
    lifecycle_state: str = "ACTIVE_ELIGIBLE",
    closed_count: int = 24,
    expectancy: float = 42.5,
    win_rate: float = 0.6,
    sample_ok: bool = True,
    eligible_for_promotion: bool = True,
    requires_review: bool = False,
    reason_code: str = "keep_family_active_eligible",
) -> dict:
    return {
        "strategy_family": family,
        "lifecycle_state": lifecycle_state,
        "reason_code": reason_code,
        "reasons": [reason_code],
        "source_recommendation": "KEEP",
        "strategy_ids": [f"{family}_v1"],
        "regimes": ["TREND"],
        "closed_count": closed_count,
        "net_expectancy_per_trade": expectancy,
        "net_win_rate": win_rate,
        "sample_ok": sample_ok,
        "eligible_for_promotion": eligible_for_promotion,
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


def test_strategy_promotion_gate_marks_clean_active_eligible_as_candidate():
    payload = build_strategy_promotion_gate_report(_lifecycle_report([_state()])).to_payload()

    assert payload["status"] == STRATEGY_PROMOTION_GATE_EVALUATED
    assert payload["family_count"] == 1
    assert payload["promotion_candidate_count"] == 1
    assert payload["blocked_count"] == 0
    decision = payload["decisions"][0]
    assert decision["decision"] == PROMOTION_DECISION_CANDIDATE
    assert decision["reason_code"] == ACTIVE_ELIGIBLE_PROMOTION_CANDIDATE_REASON
    assert decision["promotion_ready"] is True
    assert decision["promotion_applied"] is False
    assert decision["lifecycle_state_mutated"] is False


def test_strategy_promotion_gate_blocks_non_active_lifecycle_state():
    payload = build_strategy_promotion_gate_report(
        _lifecycle_report(
            [
                _state(
                    family="vwap",
                    lifecycle_state="WATCHLIST",
                    eligible_for_promotion=False,
                    requires_review=True,
                    reason_code="watch_family_watchlist",
                )
            ]
        )
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["blocked_count"] == 0
    assert payload["review_required_count"] == 1
    assert decision["decision"] == PROMOTION_DECISION_REVIEW
    assert decision["reason_code"] == PROMOTION_REVIEW_REQUIRED_REASON
    assert LIFECYCLE_NOT_ACTIVE_ELIGIBLE_REASON in decision["reasons"]
    assert NOT_ELIGIBLE_FOR_PROMOTION_REASON in decision["reasons"]
    assert decision["promotion_ready"] is False


def test_strategy_promotion_gate_blocks_low_sample_even_when_active_eligible():
    payload = build_strategy_promotion_gate_report(
        _lifecycle_report([_state(closed_count=4, sample_ok=True)]),
        promotion_min_closed_trades=20,
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["blocked_count"] == 1
    assert decision["decision"] == PROMOTION_DECISION_BLOCKED
    assert decision["reason_code"] == LOW_PROMOTION_SAMPLE_REASON
    assert decision["promotion_ready"] is False


def test_strategy_promotion_gate_blocks_negative_expectancy():
    payload = build_strategy_promotion_gate_report(
        _lifecycle_report([_state(expectancy=-1.5)])
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["blocked_count"] == 1
    assert decision["decision"] == PROMOTION_DECISION_BLOCKED
    assert decision["reason_code"] == NON_POSITIVE_EXPECTANCY_REASON
    assert decision["promotion_ready"] is False


def test_strategy_promotion_gate_blocks_low_win_rate():
    payload = build_strategy_promotion_gate_report(
        _lifecycle_report([_state(win_rate=0.49)]),
        promotion_min_win_rate=0.5,
    ).to_payload()
    decision = payload["decisions"][0]

    assert payload["blocked_count"] == 1
    assert decision["decision"] == PROMOTION_DECISION_BLOCKED
    assert decision["reason_code"] == LOW_WIN_RATE_REASON
    assert decision["promotion_ready"] is False


def test_strategy_promotion_gate_blocks_invalid_lifecycle_report():
    payload = build_strategy_promotion_gate_report(
        _lifecycle_report([_state()], status="STRATEGY_LIFECYCLE_BLOCKED")
    ).to_payload()

    assert payload["status"] == STRATEGY_PROMOTION_GATE_BLOCKED
    assert payload["reason_code"] == INVALID_LIFECYCLE_REPORT_REASON
    assert payload["lifecycle_report_valid"] is False
    assert payload["decisions"] == []


def test_strategy_promotion_gate_blocks_empty_lifecycle_states():
    payload = build_strategy_promotion_gate_report(_lifecycle_report([])).to_payload()

    assert payload["status"] == STRATEGY_PROMOTION_GATE_BLOCKED
    assert payload["reason_code"] == NO_LIFECYCLE_STATES_REASON
    assert payload["lifecycle_report_valid"] is True
    assert payload["decisions"] == []


def test_strategy_promotion_gate_blocks_invalid_policy():
    payload = build_strategy_promotion_gate_report(
        _lifecycle_report([_state()]),
        promotion_min_closed_trades=0,
    ).to_payload()

    assert payload["status"] == STRATEGY_PROMOTION_GATE_BLOCKED
    assert payload["reason_code"] == INVALID_PROMOTION_POLICY_REASON
    assert payload["decisions"] == []


def test_strategy_promotion_gate_payload_is_json_serializable_and_non_action():
    report = build_strategy_promotion_gate_report(_lifecycle_report([_state()]))
    payload = report.to_payload()
    encoded = report.to_json()

    assert json.loads(encoded)["source"] == STRATEGY_PROMOTION_GATE_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["policy"]["is_order_action"] is False
    assert payload["decisions"][0]["is_order_action"] is False
    assert payload["decisions"][0]["broker_api_called"] is False
    assert payload["decisions"][0]["promotion_applied"] is False
    assert payload["decisions"][0]["lifecycle_state_mutated"] is False
