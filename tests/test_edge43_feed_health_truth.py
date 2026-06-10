from __future__ import annotations

from core.feed_health_truth import (
    FEED_HEALTH_TRUTH_BLOCK_REASON,
    GLOBAL_FEED_UNHEALTHY_REASON,
    OPTION_FEED_BLOCKED_REASON,
    OPTION_TICKS_STALE_REASON,
    WEBSOCKET_DISCONNECTED_REASON,
    classify_feed_health_truth,
    classify_symbol_feed_truth,
)


def _payload(**overrides):
    payload = {
        "feed_ok": True,
        "ws_connected": True,
        "effective_ws_connected": True,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK", "BANKNIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5, "BANKNIFTY": 0.8},
        "symbol_feed_ok_by_symbol": {"NIFTY": True, "BANKNIFTY": True},
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "subscribed_option_tokens_count": 2,
    }
    payload.update(overrides)
    return payload


def test_feed_health_truth_allows_consistent_healthy_feed():
    decision = classify_feed_health_truth(_payload(), symbols=("NIFTY", "BANKNIFTY"))

    assert decision.feed_ok is True
    assert decision.reason_code == "ok"
    assert decision.global_feed_ok is True
    assert decision.websocket_ok is True
    assert decision.reasons == ()
    assert {symbol.symbol for symbol in decision.symbols} == {"NIFTY", "BANKNIFTY"}
    assert all(symbol.feed_ok for symbol in decision.symbols)


def test_global_feed_unhealthy_blocks_even_when_symbol_reason_is_ok():
    decision = classify_feed_health_truth(
        _payload(feed_ok=False, option_feed_block_reason_by_symbol={"NIFTY": "OK"}),
        symbols=("NIFTY",),
    )

    assert decision.feed_ok is False
    assert decision.reason_code == FEED_HEALTH_TRUTH_BLOCK_REASON
    assert GLOBAL_FEED_UNHEALTHY_REASON in decision.reasons
    assert decision.symbols[0].feed_ok is True


def test_websocket_disconnected_blocks_feed_truth():
    decision = classify_feed_health_truth(
        _payload(ws_connected=False, effective_ws_connected=False),
        symbols=("NIFTY",),
    )

    assert decision.feed_ok is False
    assert WEBSOCKET_DISCONNECTED_REASON in decision.reasons


def test_symbol_stale_option_ticks_block_symbol_and_global_truth():
    decision = classify_feed_health_truth(
        _payload(option_last_tick_age_by_symbol={"NIFTY": 12.0}),
        symbols=("NIFTY",),
        max_option_tick_age_sec=3.0,
    )

    assert decision.feed_ok is False
    assert "NIFTY:option_ticks_stale" in decision.reasons
    assert decision.symbols[0].feed_ok is False
    assert OPTION_TICKS_STALE_REASON in decision.symbols[0].reasons


def test_symbol_option_feed_blocker_is_preserved():
    symbol_truth = classify_symbol_feed_truth(
        _payload(option_feed_block_reason_by_symbol={"BANKNIFTY": "quote_exceeds_threshold"}),
        "BANKNIFTY",
        max_option_tick_age_sec=3.0,
    )

    assert symbol_truth.feed_ok is False
    assert OPTION_FEED_BLOCKED_REASON in symbol_truth.reasons
    assert symbol_truth.option_feed_block_reason == "quote_exceeds_threshold"


def test_symbols_are_collected_from_payload_when_not_requested():
    decision = classify_feed_health_truth(
        _payload(
            option_feed_block_reason_by_symbol={"MIDCPNIFTY": "OK"},
            option_last_tick_age_by_symbol={"MIDCPNIFTY": 0.2},
        )
    )

    assert [symbol.symbol for symbol in decision.symbols] == ["MIDCPNIFTY"]
    assert decision.feed_ok is True


def test_invalid_payload_fails_closed():
    decision = classify_feed_health_truth(None)

    assert decision.feed_ok is False
    assert decision.reason_code == FEED_HEALTH_TRUTH_BLOCK_REASON
    assert decision.reasons == ("invalid_payload",)


def test_to_payload_is_serializable_and_preserves_symbol_reasons():
    decision = classify_feed_health_truth(
        _payload(option_last_tick_age_by_symbol={"NIFTY": 10.0}),
        symbols=("NIFTY",),
        max_option_tick_age_sec=3.0,
    )

    payload = decision.to_payload()

    assert payload["feed_ok"] is False
    assert payload["symbols"][0]["symbol"] == "NIFTY"
    assert payload["symbols"][0]["reasons"] == (OPTION_TICKS_STALE_REASON,)
