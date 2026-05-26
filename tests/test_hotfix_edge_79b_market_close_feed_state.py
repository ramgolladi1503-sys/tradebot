"""HOTFIX/EDGE-79B market-close feed state classifier tests."""

from __future__ import annotations

from core.market_close_feed_state import (
    CLOSE_WINDOW_TICK_SLOWDOWN,
    CYCLE_LATENCY_STALE,
    FEED_STATE_HEALTHY,
    FEED_STATE_UNKNOWN,
    LTP_STALE,
    MARKET_CLOSED,
    OPTION_FEED_STALE,
    WEBSOCKET_DISCONNECTED,
    classify_market_close_feed_state,
)


def test_websocket_disconnected_is_distinct_state():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": False,
            "ltp_age_sec": 0.5,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.2,
        },
        now_epoch=1_000.0,
    )

    assert decision.state == WEBSOCKET_DISCONNECTED
    assert decision.feed_ok is False
    assert decision.ws_connected is False
    assert decision.decision_gate_reason == WEBSOCKET_DISCONNECTED
    assert WEBSOCKET_DISCONNECTED in decision.blockers


def test_ltp_stale_with_websocket_connected_is_not_socket_disconnect():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 9.0,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
        max_ltp_age_sec=2.5,
    )

    assert decision.state == LTP_STALE
    assert decision.feed_ok is False
    assert decision.ws_connected is True
    assert decision.websocket_ok is True
    assert decision.ltp_age_sec == 9.0
    assert decision.decision_gate_reason == LTP_STALE
    assert WEBSOCKET_DISCONNECTED not in decision.blockers


def test_close_window_tick_slowdown_explains_stale_ltp_near_close():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 8.0,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 120.0,
        },
        now_epoch=1_000.0,
        max_ltp_age_sec=2.5,
        close_window_sec=300.0,
    )

    assert decision.state == CLOSE_WINDOW_TICK_SLOWDOWN
    assert decision.feed_ok is False
    assert decision.ws_connected is True
    assert decision.close_window_active is True
    assert decision.decision_gate_reason == CLOSE_WINDOW_TICK_SLOWDOWN
    assert CLOSE_WINDOW_TICK_SLOWDOWN in decision.blockers
    assert WEBSOCKET_DISCONNECTED not in decision.blockers


def test_option_feed_stale_is_distinct_from_underlying_ltp_stale():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 0.5,
            "option_feed_age_sec": 9.0,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
        max_option_feed_age_sec=3.0,
    )

    assert decision.state == OPTION_FEED_STALE
    assert decision.feed_ok is False
    assert decision.option_feed_age_sec == 9.0
    assert decision.decision_gate_reason == OPTION_FEED_STALE
    assert OPTION_FEED_STALE in decision.blockers
    assert LTP_STALE not in decision.blockers


def test_cycle_latency_stale_precedes_tick_age_classification():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 9.0,
            "option_feed_age_sec": 9.0,
            "cycle_latency_sec": 20.0,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
        max_cycle_latency_sec=5.0,
    )

    assert decision.state == CYCLE_LATENCY_STALE
    assert decision.feed_ok is False
    assert decision.cycle_latency_sec == 20.0
    assert decision.decision_gate_reason == CYCLE_LATENCY_STALE
    assert CYCLE_LATENCY_STALE in decision.blockers


def test_market_closed_precedes_feed_staleness():
    decision = classify_market_close_feed_state(
        {
            "market_state": "CLOSED",
            "ws_connected": True,
            "ltp_age_sec": 99.0,
            "option_feed_age_sec": 99.0,
            "cycle_latency_sec": 99.0,
        },
        now_epoch=1_000.0,
    )

    assert decision.state == MARKET_CLOSED
    assert decision.feed_ok is False
    assert decision.market_closed is True
    assert decision.decision_gate_reason == MARKET_CLOSED
    assert MARKET_CLOSED in decision.blockers


def test_healthy_feed_state_when_all_inputs_fresh():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 0.4,
            "option_feed_age_sec": 0.8,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 1_800.0,
        },
        now_epoch=1_000.0,
    )
    payload = decision.to_payload()

    assert decision.state == FEED_STATE_HEALTHY
    assert decision.feed_ok is True
    assert decision.blockers == ()
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_empty_payload_fails_unknown_without_side_effects():
    decision = classify_market_close_feed_state({}, now_epoch=1_000.0)

    assert decision.state == FEED_STATE_UNKNOWN
    assert decision.feed_ok is False
    assert decision.decision_gate_reason == FEED_STATE_UNKNOWN
    assert FEED_STATE_UNKNOWN in decision.blockers
    assert decision.read_only is True
    assert decision.append is False
