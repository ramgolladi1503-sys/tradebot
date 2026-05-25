from __future__ import annotations

import json

from core.feed_policy import (
    FEED_POLICY_BLOCKER,
    INVALID_FEED_POLICY,
    LIVE_FEED_POLICY,
    PAPER_FEED_POLICY,
    SIM_FEED_POLICY,
    classify_feed_with_policy,
    thresholds_for_mode,
)


def _payload(*, option_age: float = 3.0, ltp_age: float = 3.0, depth_age: float = 6.0, ws_connected=True):
    return {
        "feed_ok": True,
        "effective_ws_connected": ws_connected,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE"},
        "last_tick_age_sec": ltp_age,
        "last_depth_age_sec": depth_age,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": option_age},
    }


def test_live_policy_is_stricter_than_paper_for_same_feed_age():
    payload = _payload(option_age=3.0, ltp_age=3.0, depth_age=6.0)

    live = classify_feed_with_policy(payload, mode="LIVE", symbols=("NIFTY",))
    paper = classify_feed_with_policy(payload, mode="PAPER", symbols=("NIFTY",))

    assert live.policy_name == LIVE_FEED_POLICY
    assert live.feed_ok is False
    assert "ltp_ticks_stale" in live.reasons
    assert "depth_ticks_stale" in live.reasons
    assert "NIFTY:option_ticks_stale" in live.reasons
    assert paper.policy_name == PAPER_FEED_POLICY
    assert paper.feed_ok is True
    assert paper.reasons == ()


def test_paper_policy_still_blocks_clearly_stale_feed():
    decision = classify_feed_with_policy(
        _payload(option_age=8.0, ltp_age=8.0, depth_age=12.0),
        mode="PAPER",
        symbols=("NIFTY",),
    )

    assert decision.feed_ok is False
    assert decision.policy_name == PAPER_FEED_POLICY
    assert "ltp_ticks_stale" in decision.reasons
    assert "depth_ticks_stale" in decision.reasons
    assert "NIFTY:option_ticks_stale" in decision.reasons
    assert decision.blockers == decision.reasons


def test_invalid_mode_fails_closed_and_is_non_action():
    decision = classify_feed_with_policy(_payload(), mode="DEMO", symbols=("NIFTY",))

    assert decision.mode == "INVALID"
    assert decision.policy_name == INVALID_FEED_POLICY
    assert decision.feed_ok is False
    assert decision.read_only is True
    assert decision.append is False
    assert decision.is_order_action is False
    assert decision.reasons == ("invalid_mode",)
    assert FEED_POLICY_BLOCKER in decision.blockers


def test_live_policy_requires_explicit_websocket_truth():
    decision = classify_feed_with_policy(
        _payload(option_age=0.5, ltp_age=0.5, depth_age=1.0, ws_connected=None),
        mode="LIVE",
        symbols=("NIFTY",),
    )

    assert decision.feed_ok is False
    assert decision.policy_name == LIVE_FEED_POLICY
    assert "websocket_required_by_policy" in decision.reasons


def test_sim_policy_allows_observation_without_websocket_requirement():
    decision = classify_feed_with_policy(
        _payload(option_age=30.0, ltp_age=30.0, depth_age=80.0, ws_connected=None),
        mode="SIM",
        symbols=("NIFTY",),
    )

    assert decision.feed_ok is True
    assert decision.policy_name == SIM_FEED_POLICY
    assert decision.thresholds.require_websocket is False
    assert decision.reasons == ()


def test_policy_decision_is_json_serializable_and_contains_non_action_marker():
    decision = classify_feed_with_policy(_payload(), mode="PAPER", symbols=("NIFTY",))

    payload = json.loads(decision.to_json())

    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["policy_name"] == PAPER_FEED_POLICY
    assert payload["metadata"]["policy"] == "feed_policy_v1"


def test_thresholds_for_mode_supports_aliases_and_invalid_defaults():
    assert thresholds_for_mode("production").policy_name == LIVE_FEED_POLICY
    assert thresholds_for_mode("paper_trading").policy_name == PAPER_FEED_POLICY
    assert thresholds_for_mode("backtest").policy_name == SIM_FEED_POLICY
    assert thresholds_for_mode("unknown").policy_name == INVALID_FEED_POLICY
