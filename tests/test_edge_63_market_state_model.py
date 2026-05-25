from __future__ import annotations

import json

from core.market_state import (
    BREADTH_BEARISH,
    BREADTH_BULLISH,
    LIQUIDITY_DEEP,
    LIQUIDITY_THIN,
    MARKET_STATE_INSUFFICIENT_EVIDENCE,
    SESSION_CLOSED,
    SESSION_CLOSING,
    SESSION_MIDDAY,
    SESSION_OPENING,
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UP,
    UNKNOWN,
    VOL_EXTREME,
    VOL_HIGH,
    VOL_LOW,
    build_market_state,
)


def _bullish_snapshot():
    return {
        "index_change_pct": 0.8,
        "vwap_distance_pct": 0.5,
        "ema_slope_pct": 0.35,
        "atr_pct": 0.55,
        "realized_vol_pct": 0.5,
        "india_vix": 14.0,
        "advance_decline_ratio": 1.8,
        "sector_positive_pct": 68.0,
        "avg_spread_bps": 10.0,
        "depth_score": 0.82,
        "quote_age_sec": 0.7,
        "market_minute": 90,
        "ignored_secret": "must_not_copy",
    }


def test_market_state_builds_bullish_deep_liquidity_state():
    state = build_market_state(_bullish_snapshot(), symbol="nifty", mode="paper")

    assert state.read_only is True
    assert state.append is False
    assert state.is_order_action is False
    assert state.broker_api_called is False
    assert state.symbol == "NIFTY"
    assert state.mode == "PAPER"
    assert state.trend.value == TREND_UP
    assert state.volatility.value != UNKNOWN
    assert state.breadth.value == BREADTH_BULLISH
    assert state.liquidity.value == LIQUIDITY_DEEP
    assert state.session.value == SESSION_MIDDAY
    assert state.blockers == ()
    assert state.confidence > 0.0


def test_market_state_detects_bearish_thin_high_volatility_state():
    state = build_market_state(
        {
            "index_change_pct": -0.9,
            "vwap_distance_pct": -0.7,
            "ema_slope_pct": -0.4,
            "atr_pct": 0.95,
            "realized_vol_pct": 0.8,
            "india_vix": 18.0,
            "advance_decline_ratio": 0.5,
            "sector_positive_pct": 35.0,
            "avg_spread_bps": 65.0,
            "depth_score": 0.25,
            "quote_age_sec": 6.0,
            "market_minute": 12,
        }
    )

    assert state.trend.value == TREND_DOWN
    assert state.volatility.value == VOL_HIGH
    assert state.breadth.value == BREADTH_BEARISH
    assert state.liquidity.value == LIQUIDITY_THIN
    assert state.session.value == SESSION_OPENING
    assert state.blockers == ()


def test_market_state_detects_extreme_and_low_volatility_boundaries():
    extreme = build_market_state({"india_vix": 23.0, "market_minute": 40})
    low = build_market_state({"india_vix": 11.5, "atr_pct": 0.2, "market_minute": 40})

    assert extreme.volatility.value == VOL_EXTREME
    assert low.volatility.value == VOL_LOW


def test_market_state_missing_evidence_sets_unknown_dimensions_and_blocker():
    state = build_market_state(None)

    assert state.trend.value == UNKNOWN
    assert state.volatility.value == UNKNOWN
    assert state.breadth.value == UNKNOWN
    assert state.liquidity.value == UNKNOWN
    assert state.session.value == UNKNOWN
    assert MARKET_STATE_INSUFFICIENT_EVIDENCE in state.blockers
    assert "trend_evidence_missing" in state.warnings
    assert state.evidence_snapshot == {"payload_present": False, "payload_type": "NoneType"}
    assert state.confidence == 0.0


def test_market_state_sideways_and_session_boundaries_are_deterministic():
    sideways = build_market_state(
        {
            "index_change_pct": 0.05,
            "vwap_distance_pct": -0.03,
            "ema_slope_pct": 0.02,
            "market_minute": 348,
        }
    )
    closed = build_market_state({"session_phase": "closed"})

    assert sideways.trend.value == TREND_SIDEWAYS
    assert sideways.session.value == SESSION_CLOSING
    assert closed.session.value == SESSION_CLOSED


def test_market_state_sanitizes_snapshot_and_keeps_unknown_keys_as_names_only():
    state = build_market_state(_bullish_snapshot())

    snapshot = state.evidence_snapshot

    assert snapshot["payload_present"] is True
    assert snapshot["index_change_pct"] == 0.8
    assert "ignored_secret" not in snapshot
    assert "ignored_secret" in snapshot["snapshot_keys"]


def test_market_state_json_payload_contains_non_action_contract_fields():
    state = build_market_state(_bullish_snapshot(), symbol="BANKNIFTY", mode="LIVE")

    payload = json.loads(state.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["mode"] == "LIVE"
    assert payload["symbol"] == "BANKNIFTY"
    assert payload["metadata"]["scope"] == "read_only_descriptive_market_state_no_strategy_selection"
    assert payload["trend"]["value"] == TREND_UP
