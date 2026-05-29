from __future__ import annotations

from core.feed_zombie_state import (
    FEED_ZOMBIE_NO_SUBSCRIPTIONS,
    FEED_ZOMBIE_STALE_FEED,
    FEED_ZOMBIE_STATE,
    FEED_ZOMBIE_WS_DISCONNECTED,
    classify_feed_zombie_state,
)


def test_detects_market_open_live_feed_zombie():
    decision = classify_feed_zombie_state(
        {
            "ws_connected": False,
            "subscribed_tokens_count": 0,
            "subscribed_option_tokens_count": 0,
            "subscriptions_count": 0,
            "sla_status": "STALE",
            "reasons": ["ltp_stale:NIFTY age=445.07 max=2.50"],
        },
        market_open=True,
        mode="LIVE",
    )

    assert decision.is_zombie is True
    assert decision.state == FEED_ZOMBIE_STATE
    assert FEED_ZOMBIE_NO_SUBSCRIPTIONS in decision.blockers
    assert FEED_ZOMBIE_WS_DISCONNECTED in decision.blockers
    assert FEED_ZOMBIE_STALE_FEED in decision.blockers
    payload = decision.to_payload()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_healthy_live_feed_is_not_zombie():
    decision = classify_feed_zombie_state(
        {
            "ws_connected": True,
            "subscribed_tokens_count": 62,
            "subscribed_option_tokens_count": 59,
            "subscriptions_count": 62,
            "sla_status": "OK",
            "reasons": [],
            "runtime_state": "RUNNING",
        },
        market_open=True,
        mode="LIVE",
    )

    assert decision.is_zombie is False
    assert decision.state == "RUNNING"
    assert decision.blockers == ()


def test_market_closed_does_not_false_positive_without_live_requirement():
    decision = classify_feed_zombie_state(
        {
            "ws_connected": False,
            "subscribed_tokens_count": 0,
            "subscribed_option_tokens_count": 0,
            "sla_status": "STALE",
        },
        market_open=False,
        mode="LIVE",
    )

    assert decision.is_zombie is False
    assert FEED_ZOMBIE_NO_SUBSCRIPTIONS not in decision.blockers


def test_explicit_live_requirement_can_detect_zombie_offhours():
    decision = classify_feed_zombie_state(
        {
            "ws_connected": False,
            "subscribed_tokens_count": 0,
            "subscribed_option_tokens_count": 0,
            "sla_status": "BREACH",
        },
        market_open=False,
        mode="LIVE",
        require_live_feed=True,
    )

    assert decision.is_zombie is True
    assert decision.state == FEED_ZOMBIE_STATE


def test_partial_failure_is_not_zombie_until_all_zombie_conditions_hold():
    decision = classify_feed_zombie_state(
        {
            "ws_connected": True,
            "subscribed_tokens_count": 0,
            "subscribed_option_tokens_count": 0,
            "sla_status": "STALE",
        },
        market_open=True,
        mode="LIVE",
    )

    assert decision.is_zombie is False
    assert FEED_ZOMBIE_WS_DISCONNECTED not in decision.blockers
    assert FEED_ZOMBIE_NO_SUBSCRIPTIONS in decision.blockers
    assert FEED_ZOMBIE_STALE_FEED in decision.blockers
