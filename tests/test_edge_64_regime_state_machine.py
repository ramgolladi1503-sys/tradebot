from __future__ import annotations

import json

from core.market_state import build_market_state
from core.regime_state import (
    REGIME_BEAR_TREND,
    REGIME_BULL_TREND,
    REGIME_INSUFFICIENT_MARKET_STATE,
    REGIME_LIQUIDITY_STRESSED,
    REGIME_LIQUIDITY_STRESSED_BLOCKER,
    REGIME_OPENING_DISCOVERY,
    REGIME_OUT_OF_SESSION,
    REGIME_OUT_OF_SESSION_BLOCKER,
    REGIME_RANGE_BOUND,
    REGIME_UNKNOWN,
    REGIME_VOLATILITY_STRESSED,
    REGIME_VOLATILITY_STRESSED_BLOCKER,
    TRANSITION_CHANGED,
    TRANSITION_STABLE,
    TRANSITION_UNKNOWN,
    build_regime_state,
)


def _bullish_market_state(**overrides):
    snapshot = {
        "index_change_pct": 0.8,
        "vwap_distance_pct": 0.55,
        "ema_slope_pct": 0.35,
        "atr_pct": 0.45,
        "realized_vol_pct": 0.4,
        "india_vix": 14.0,
        "advance_decline_ratio": 1.8,
        "sector_positive_pct": 68.0,
        "avg_spread_bps": 10.0,
        "depth_score": 0.82,
        "quote_age_sec": 0.8,
        "market_minute": 120,
        "ignored_secret": "must_not_leak_to_regime_summary",
    }
    snapshot.update(overrides)
    return build_market_state(snapshot, symbol="nifty", mode="paper")


def _bearish_market_state(**overrides):
    snapshot = {
        "index_change_pct": -0.9,
        "vwap_distance_pct": -0.65,
        "ema_slope_pct": -0.45,
        "atr_pct": 0.55,
        "realized_vol_pct": 0.5,
        "india_vix": 15.0,
        "advance_decline_ratio": 0.55,
        "sector_positive_pct": 34.0,
        "avg_spread_bps": 12.0,
        "depth_score": 0.78,
        "quote_age_sec": 0.7,
        "market_minute": 150,
    }
    snapshot.update(overrides)
    return build_market_state(snapshot, symbol="banknifty", mode="paper")


def test_regime_state_classifies_stable_bull_trend_from_market_state():
    state = build_regime_state(_bullish_market_state(), previous_regime=REGIME_BULL_TREND)

    assert state.read_only is True
    assert state.append is False
    assert state.is_order_action is False
    assert state.broker_api_called is False
    assert state.regime == REGIME_BULL_TREND
    assert state.stable is True
    assert state.transition.transition_type == TRANSITION_STABLE
    assert state.transition.changed is False
    assert state.blockers == ()
    assert state.symbol == "NIFTY"
    assert state.mode == "PAPER"
    assert state.confidence > 0.0


def test_regime_state_detects_bear_trend_transition_from_previous_bull_regime():
    state = build_regime_state(_bearish_market_state(), previous_regime=REGIME_BULL_TREND)

    assert state.regime == REGIME_BEAR_TREND
    assert state.transition.previous_regime == REGIME_BULL_TREND
    assert state.transition.current_regime == REGIME_BEAR_TREND
    assert state.transition.transition_type == TRANSITION_CHANGED
    assert state.transition.changed is True
    assert state.stable is False
    assert state.blockers == ()


def test_regime_state_classifies_range_bound_without_strategy_selection():
    market_state = build_market_state(
        {
            "index_change_pct": 0.05,
            "vwap_distance_pct": -0.03,
            "ema_slope_pct": 0.02,
            "atr_pct": 0.2,
            "realized_vol_pct": 0.25,
            "india_vix": 11.5,
            "advance_decline_ratio": 1.0,
            "sector_positive_pct": 50.0,
            "avg_spread_bps": 24.0,
            "depth_score": 0.60,
            "quote_age_sec": 1.1,
            "market_minute": 180,
        }
    )

    state = build_regime_state(market_state)

    assert state.regime == REGIME_RANGE_BOUND
    assert state.transition.changed is False
    assert state.blockers == ()
    payload = json.loads(state.to_json())
    assert "selected_strategy" not in payload
    assert "eligible_strategies" not in payload


def test_regime_state_prioritizes_liquidity_and_volatility_stress_before_direction():
    thin = build_regime_state(
        _bullish_market_state(avg_spread_bps=70.0, depth_score=0.25, quote_age_sec=6.5)
    )
    extreme = build_regime_state(_bullish_market_state(india_vix=24.0, atr_pct=1.4))

    assert thin.regime == REGIME_LIQUIDITY_STRESSED
    assert REGIME_LIQUIDITY_STRESSED_BLOCKER in thin.blockers
    assert extreme.regime == REGIME_VOLATILITY_STRESSED
    assert REGIME_VOLATILITY_STRESSED_BLOCKER in extreme.blockers


def test_regime_state_handles_missing_market_state_as_unknown_and_blocked():
    state = build_regime_state(None, previous_regime=REGIME_BEAR_TREND)

    assert state.regime == REGIME_UNKNOWN
    assert state.transition.transition_type == TRANSITION_UNKNOWN
    assert state.transition.changed is False
    assert REGIME_INSUFFICIENT_MARKET_STATE in state.blockers
    assert "market_state_payload_missing" in state.blockers
    assert state.confidence == 0.0


def test_regime_state_treats_session_boundaries_as_read_only_regimes():
    opening = build_regime_state(_bullish_market_state(session_phase="opening"))
    closed = build_regime_state(_bullish_market_state(session_phase="closed"))

    assert opening.regime == REGIME_OPENING_DISCOVERY
    assert "opening_session_regime_unstable" in opening.warnings
    assert opening.blockers == ()
    assert closed.regime == REGIME_OUT_OF_SESSION
    assert REGIME_OUT_OF_SESSION_BLOCKER in closed.blockers


def test_regime_state_accepts_serialized_market_state_payload_without_leaking_snapshot():
    market_state = _bullish_market_state()
    state = build_regime_state(market_state.to_payload())
    payload = json.loads(state.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["regime"] == REGIME_BULL_TREND
    assert "evidence_snapshot" not in payload["market_state_summary"]
    assert "must_not_leak_to_regime_summary" not in json.dumps(payload["market_state_summary"])
    assert payload["metadata"]["scope"] == "read_only_descriptive_regime_state_no_strategy_selection"
