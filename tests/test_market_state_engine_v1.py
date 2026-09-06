from core.live_market_state_runtime import evaluate_live_market_state
from core.market_state_engine_v1 import BEARISH, BULLISH, NO_TRADE, classify_cross_index_consensus, classify_market_state


def _base(**overrides):
    row = {
        "price": 25000.0,
        "vwap": 24950.0,
        "atr": 100.0,
        "quote_age_sec": 0.5,
        "feed_authority": True,
        "session_open": True,
        "ema_fast": 24990.0,
        "ema_slow": 24920.0,
        "ema_slope_atr": 0.6,
        "structure_score": 0.8,
        "momentum_score": 0.7,
        "weighted_breadth": 0.8,
        "breadth": 0.6,
        "breadth_momentum": 0.5,
        "open_location_score": 0.4,
        "futures_confirmation_score": 0.5,
        "orb_high": 24970.0,
        "orb_low": 24780.0,
        "swing_high": 24980.0,
        "swing_low": 24860.0,
        "support": 24850.0,
        "resistance": 25200.0,
    }
    row.update(overrides)
    return row


def test_bullish_classification_and_levels():
    state = classify_market_state(_base(), symbol="NIFTY")
    assert state.zone == BULLISH
    assert state.score >= 45
    assert state.bull_trend_price > 24980
    assert state.bull_reversal_price < state.bull_trend_price
    assert state.to_payload()["order_authority"] is False
    assert state.broker_api_called is False


def test_bearish_classification():
    row = _base(
        price=24850.0,
        vwap=24950.0,
        ema_fast=24870.0,
        ema_slow=24950.0,
        ema_slope_atr=-0.8,
        structure_score=-0.9,
        momentum_score=-0.8,
        weighted_breadth=-0.8,
        breadth=-0.7,
        breadth_momentum=-0.6,
        open_location_score=-0.5,
        futures_confirmation_score=-0.5,
    )
    state = classify_market_state(row, symbol="BANKNIFTY")
    assert state.zone == BEARISH
    assert state.score <= -45


def test_conflict_defaults_to_no_trade():
    row = _base(
        price=24955.0,
        ema_fast=24950.0,
        ema_slow=24950.0,
        ema_slope_atr=0.0,
        structure_score=-0.1,
        momentum_score=0.1,
        weighted_breadth=-0.2,
        breadth=0.2,
        breadth_momentum=0.0,
        open_location_score=0.0,
        futures_confirmation_score=0.0,
    )
    state = classify_market_state(row, symbol="SENSEX")
    assert state.zone == NO_TRADE
    assert state.entry_state == "WAIT"


def test_hysteresis_keeps_existing_bull_until_exit_threshold_breaks():
    row = _base(
        price=24975.0,
        structure_score=0.25,
        momentum_score=0.20,
        weighted_breadth=0.2,
        breadth=0.2,
        breadth_momentum=0.2,
        open_location_score=0.1,
        futures_confirmation_score=0.0,
    )
    state = classify_market_state(row, symbol="NIFTY", previous_zone=BULLISH)
    assert 25 <= state.score < 45
    assert state.zone == BULLISH


def test_stale_quote_fails_closed_to_no_trade():
    state = classify_market_state(_base(quote_age_sec=7.0), symbol="NIFTY")
    assert state.zone == NO_TRADE
    assert state.entry_state == "BLOCKED"
    assert "STALE_QUOTE" in state.blockers
    assert state.confidence == 0.0


def test_missing_critical_input_fails_closed():
    row = _base()
    row.pop("atr")
    state = classify_market_state(row, symbol="NIFTY")
    assert state.zone == NO_TRADE
    assert "MISSING_ATR" in state.blockers


def test_extended_bull_is_bullish_regime_but_not_entry():
    state = classify_market_state(_base(price=25100.0, vwap=24950.0, atr=100.0), symbol="NIFTY")
    assert state.zone == BULLISH
    assert state.entry_state == "NO_TRADE_EXTENDED"
    assert "PRICE_EXTENDED_FROM_VWAP" in state.warnings


def test_near_resistance_waits_for_pullback():
    state = classify_market_state(_base(price=25000.0, resistance=25020.0), symbol="NIFTY")
    assert state.zone == BULLISH
    assert state.entry_state == "WAIT_PULLBACK"
    assert "NEAR_RESISTANCE" in state.warnings


def test_cross_index_conflict_is_no_trade():
    bull = classify_market_state(_base(), symbol="NIFTY")
    bear = classify_market_state(
        _base(price=24800.0, vwap=24950.0, ema_fast=24830.0, ema_slow=24950.0,
              ema_slope_atr=-1.0, structure_score=-1.0, momentum_score=-1.0,
              weighted_breadth=-1.0, breadth=-1.0, breadth_momentum=-1.0,
              open_location_score=-1.0, futures_confirmation_score=-1.0),
        symbol="BANKNIFTY",
    )
    neutral = classify_market_state(_base(price=24950.0, structure_score=0.0, momentum_score=0.0,
                                          weighted_breadth=0.0, breadth=0.0, breadth_momentum=0.0,
                                          open_location_score=0.0, futures_confirmation_score=0.0,
                                          ema_fast=24950.0, ema_slow=24950.0, ema_slope_atr=0.0), symbol="SENSEX")
    consensus = classify_cross_index_consensus({"NIFTY": bull, "BANKNIFTY": bear, "SENSEX": neutral})
    assert consensus["consensus"] == NO_TRADE
    assert consensus["reason"] == "CROSS_INDEX_CONFLICT"


def test_runtime_requires_all_three_index_authorities_for_healthy_verdict():
    payload = evaluate_live_market_state({"NIFTY": _base(), "BANKNIFTY": _base(), "SENSEX": {}})
    assert payload["verdict"] == "BLOCKED"
    assert payload["regime_healthy"] is False
    assert payload["indices"]["SENSEX"]["zone"] == NO_TRADE
    assert payload["broker_order_calls"] == 0
