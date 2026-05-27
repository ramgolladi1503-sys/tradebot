from __future__ import annotations

import json

from core.strategy_lifecycle_states import (
    INVALID_FAMILY_REPORT_REASON,
    INVALID_LIFECYCLE_POLICY_REASON,
    KEEP_FAMILY_ACTIVE_ELIGIBLE_REASON,
    KILL_FAMILY_RETIRED_CANDIDATE_REASON,
    KILL_FAMILY_SUSPEND_CANDIDATE_REASON,
    LIFECYCLE_STATE_ACTIVE_ELIGIBLE,
    LIFECYCLE_STATE_CANDIDATE,
    LIFECYCLE_STATE_RETIRED_CANDIDATE,
    LIFECYCLE_STATE_SUSPEND_CANDIDATE,
    LIFECYCLE_STATE_WATCHLIST,
    LOW_SAMPLE_CANDIDATE_REASON,
    NO_FAMILY_RECOMMENDATIONS_REASON,
    STRATEGY_LIFECYCLE_BLOCKED,
    STRATEGY_LIFECYCLE_REDUCED,
    STRATEGY_LIFECYCLE_SOURCE,
    UNKNOWN_RECOMMENDATION_WATCHLIST_REASON,
    WATCH_FAMILY_WATCHLIST_REASON,
    build_strategy_lifecycle_report,
)


def _recommendation(
    *,
    family: str = "breakout",
    recommendation: str = "KEEP",
    closed_count: int = 20,
    sample_ok: bool = True,
    reason_code: str = "positive_net_expectancy",
    reasons: list[str] | None = None,
) -> dict:
    return {
        "strategy_family": family,
        "recommendation": recommendation,
        "reason_code": reason_code,
        "reasons": reasons or [reason_code],
        "strategy_ids": [f"{family}_v1"],
        "regimes": ["TREND"],
        "closed_count": closed_count,
        "net_expectancy_per_trade": 42.5,
        "net_win_rate": 0.6,
        "sample_ok": sample_ok,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def _family_report(recommendations: list[dict], *, status: str = "STRATEGY_FAMILY_REPORT_REDUCED") -> dict:
    return {
        "schema_version": 1,
        "source": "strategy_family_kill_keep_report_v1",
        "status": status,
        "read_only": True,
        "append": False,
        "recommendations": recommendations,
    }


def test_strategy_lifecycle_maps_keep_family_to_active_eligible():
    payload = build_strategy_lifecycle_report(
        _family_report([_recommendation(recommendation="KEEP")])
    ).to_payload()

    assert payload["status"] == STRATEGY_LIFECYCLE_REDUCED
    assert payload["family_count"] == 1
    assert payload["active_eligible_count"] == 1
    state = payload["states"][0]
    assert state["lifecycle_state"] == LIFECYCLE_STATE_ACTIVE_ELIGIBLE
    assert state["reason_code"] == KEEP_FAMILY_ACTIVE_ELIGIBLE_REASON
    assert state["eligible_for_promotion"] is True
    assert state["requires_review"] is False
    assert state["promotion_applied"] is False


def test_strategy_lifecycle_maps_watch_family_to_watchlist():
    payload = build_strategy_lifecycle_report(
        _family_report([_recommendation(family="vwap", recommendation="WATCH")])
    ).to_payload()
    state = payload["states"][0]

    assert payload["watchlist_count"] == 1
    assert state["strategy_family"] == "vwap"
    assert state["lifecycle_state"] == LIFECYCLE_STATE_WATCHLIST
    assert state["reason_code"] == WATCH_FAMILY_WATCHLIST_REASON
    assert state["requires_review"] is True


def test_strategy_lifecycle_maps_low_sample_to_candidate_even_when_keep():
    payload = build_strategy_lifecycle_report(
        _family_report(
            [
                _recommendation(
                    family="mean_reversion",
                    recommendation="KEEP",
                    closed_count=2,
                    sample_ok=False,
                    reason_code="insufficient_family_sample",
                    reasons=["insufficient_family_sample"],
                )
            ]
        )
    ).to_payload()
    state = payload["states"][0]

    assert payload["candidate_count"] == 1
    assert state["lifecycle_state"] == LIFECYCLE_STATE_CANDIDATE
    assert state["reason_code"] == LOW_SAMPLE_CANDIDATE_REASON
    assert state["eligible_for_promotion"] is False


def test_strategy_lifecycle_maps_kill_to_suspend_candidate_below_retire_threshold():
    payload = build_strategy_lifecycle_report(
        _family_report([_recommendation(family="zero_hero", recommendation="KILL", closed_count=12)]),
        retire_min_closed_trades=30,
    ).to_payload()
    state = payload["states"][0]

    assert payload["suspend_candidate_count"] == 1
    assert payload["retired_candidate_count"] == 0
    assert state["lifecycle_state"] == LIFECYCLE_STATE_SUSPEND_CANDIDATE
    assert state["reason_code"] == KILL_FAMILY_SUSPEND_CANDIDATE_REASON
    assert state["suspension_applied"] is False


def test_strategy_lifecycle_maps_kill_to_retired_candidate_at_retire_threshold():
    payload = build_strategy_lifecycle_report(
        _family_report([_recommendation(family="zero_hero", recommendation="KILL", closed_count=30)]),
        retire_min_closed_trades=30,
    ).to_payload()
    state = payload["states"][0]

    assert payload["retired_candidate_count"] == 1
    assert state["lifecycle_state"] == LIFECYCLE_STATE_RETIRED_CANDIDATE
    assert state["reason_code"] == KILL_FAMILY_RETIRED_CANDIDATE_REASON
    assert state["retirement_applied"] is False


def test_strategy_lifecycle_unknown_recommendation_fails_safe_to_watchlist():
    payload = build_strategy_lifecycle_report(
        _family_report([_recommendation(family="custom", recommendation="PROMOTE_NOW")])
    ).to_payload()
    state = payload["states"][0]

    assert payload["watchlist_count"] == 1
    assert state["lifecycle_state"] == LIFECYCLE_STATE_WATCHLIST
    assert state["reason_code"] == UNKNOWN_RECOMMENDATION_WATCHLIST_REASON
    assert state["requires_review"] is True


def test_strategy_lifecycle_blocks_invalid_family_report():
    payload = build_strategy_lifecycle_report(
        _family_report([], status="STRATEGY_FAMILY_REPORT_BLOCKED")
    ).to_payload()

    assert payload["status"] == STRATEGY_LIFECYCLE_BLOCKED
    assert payload["reason_code"] == INVALID_FAMILY_REPORT_REASON
    assert payload["family_report_valid"] is False
    assert payload["states"] == []


def test_strategy_lifecycle_blocks_empty_recommendations():
    payload = build_strategy_lifecycle_report(_family_report([])).to_payload()

    assert payload["status"] == STRATEGY_LIFECYCLE_BLOCKED
    assert payload["reason_code"] == NO_FAMILY_RECOMMENDATIONS_REASON
    assert payload["family_report_valid"] is True
    assert payload["states"] == []


def test_strategy_lifecycle_blocks_invalid_policy():
    payload = build_strategy_lifecycle_report(
        _family_report([_recommendation()]),
        retire_min_closed_trades=0,
    ).to_payload()

    assert payload["status"] == STRATEGY_LIFECYCLE_BLOCKED
    assert payload["reason_code"] == INVALID_LIFECYCLE_POLICY_REASON
    assert payload["states"] == []


def test_strategy_lifecycle_payload_is_json_serializable_and_non_action():
    report = build_strategy_lifecycle_report(_family_report([_recommendation()]))
    payload = report.to_payload()
    encoded = report.to_json()

    assert json.loads(encoded)["source"] == STRATEGY_LIFECYCLE_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["policy"]["is_order_action"] is False
    assert payload["states"][0]["is_order_action"] is False
    assert payload["states"][0]["broker_api_called"] is False
    assert payload["states"][0]["promotion_applied"] is False
    assert payload["states"][0]["suspension_applied"] is False
    assert payload["states"][0]["retirement_applied"] is False
