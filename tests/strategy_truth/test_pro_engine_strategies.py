from strategies.pro_layer.pro_strategy_engine import (
    VolatilityExpansionStrategy,
    LiquidityImbalanceStrategy,
    VWAPMeanReversionStrategy,
    OptionsFlowStrategy,
    TimeWindowStrategy,
)

def _mock_snapshot(overrides):
    base = {
        "symbol": "TEST",
        "ltp": 100.0,
        "vwap": 100.0,
        "atr": 5.0,
        "ltp_change_window": 1.0,
        "vol_z": 1.0,
        "bid_qty": 1000,
        "ask_qty": 500,
        "spread_pct": 0.001,
        "quote_age_sec": 1.0,
        "rsi_mom": 40.0,
        "call_oi_delta": 1000,
        "put_oi_delta": 500,
        "iv_change": 0.05,
        "ltp_change": 0.5,
    }
    base.update(overrides)
    return base

# VolatilityExpansionStrategy
def test_volatility_expansion_positive_trigger():
    s = VolatilityExpansionStrategy()
    res = s.generate(_mock_snapshot({"ltp_change_window": 5.0, "atr": 5.0, "vol_z": 1.5}))
    assert res is not None
    assert res.name == "vol_expansion"
    assert res.direction == "BUY_CALL"

def test_volatility_expansion_negative_no_trigger():
    s = VolatilityExpansionStrategy()
    res = s.generate(_mock_snapshot({"ltp_change_window": 1.0, "atr": 5.0, "vol_z": 0.5}))
    assert res is None

def test_volatility_expansion_bullish_bearish_maps_correctly():
    s = VolatilityExpansionStrategy()
    res_up = s.generate(_mock_snapshot({"ltp_change_window": 5.0, "atr": 5.0, "vol_z": 1.5}))
    assert res_up.direction == "BUY_CALL"
    res_down = s.generate(_mock_snapshot({"ltp_change_window": -5.0, "atr": 5.0, "vol_z": 1.5}))
    assert res_down.direction == "BUY_PUT"

def test_volatility_expansion_nan_fails_closed():
    s = VolatilityExpansionStrategy()
    res = s.generate(_mock_snapshot({"atr": float("nan"), "ltp_change_window": 5.0}))
    assert res is None

def test_volatility_expansion_missing_fails_closed():
    s = VolatilityExpansionStrategy()
    res = s.generate({"symbol": "TEST", "ltp": 100.0, "quote_age_sec": 1.0, "spread_pct": 0.001})
    assert res is None

# LiquidityImbalanceStrategy
def test_liquidity_imbalance_positive_trigger():
    s = LiquidityImbalanceStrategy()
    res = s.generate(_mock_snapshot({"bid_qty": 2000, "ask_qty": 500, "spread_pct": 0.001}))
    assert res is not None
    assert res.name == "liquidity_imbalance"
    assert res.direction == "BUY_CALL"

def test_liquidity_imbalance_negative_no_trigger():
    s = LiquidityImbalanceStrategy()
    res = s.generate(_mock_snapshot({"bid_qty": 1000, "ask_qty": 1000}))
    assert res is None

def test_liquidity_imbalance_bullish_bearish_maps_correctly():
    s = LiquidityImbalanceStrategy()
    res_up = s.generate(_mock_snapshot({"bid_qty": 2000, "ask_qty": 500}))
    assert res_up.direction == "BUY_CALL"
    res_down = s.generate(_mock_snapshot({"bid_qty": 500, "ask_qty": 2000}))
    assert res_down.direction == "BUY_PUT"

def test_liquidity_imbalance_nan_fails_closed():
    s = LiquidityImbalanceStrategy()
    res = s.generate(_mock_snapshot({"bid_qty": float("nan")}))
    assert res is None

def test_liquidity_imbalance_missing_fails_closed():
    s = LiquidityImbalanceStrategy()
    res = s.generate({"symbol": "TEST", "quote_age_sec": 1.0, "spread_pct": 0.001})
    assert res is None

# VWAPMeanReversionStrategy
def test_vwap_mean_reversion_positive_trigger():
    s = VWAPMeanReversionStrategy()
    res = s.generate(_mock_snapshot({"ltp": 99.0, "vwap": 100.0, "rsi_mom": -0.40}))
    assert res is not None
    assert res.name == "vwap_mean_reversion"
    assert res.direction == "BUY_CALL"

def test_vwap_mean_reversion_negative_no_trigger():
    s = VWAPMeanReversionStrategy()
    res = s.generate(_mock_snapshot({"ltp": 100.0, "vwap": 100.0}))
    assert res is None

def test_vwap_mean_reversion_bullish_bearish_maps_correctly():
    s = VWAPMeanReversionStrategy()
    res_up = s.generate(_mock_snapshot({"ltp": 99.0, "vwap": 100.0, "rsi_mom": -0.40}))
    assert res_up.direction == "BUY_CALL"
    res_down = s.generate(_mock_snapshot({"ltp": 101.0, "vwap": 100.0, "rsi_mom": 0.40}))
    assert res_down.direction == "BUY_PUT"

def test_vwap_mean_reversion_nan_fails_closed():
    s = VWAPMeanReversionStrategy()
    res = s.generate(_mock_snapshot({"vwap": float("nan")}))
    assert res is None

def test_vwap_mean_reversion_missing_fails_closed():
    s = VWAPMeanReversionStrategy()
    res = s.generate({"symbol": "TEST", "quote_age_sec": 1.0, "spread_pct": 0.001})
    assert res is None

# OptionsFlowStrategy
def test_options_flow_positive_trigger():
    s = OptionsFlowStrategy()
    res = s.generate(_mock_snapshot({"call_oi_delta": 500, "put_oi_delta": 2000, "ltp_change": 1.0}))
    assert res is not None
    assert res.name == "options_flow_alignment"
    assert res.direction == "BUY_CALL"

def test_options_flow_negative_no_trigger():
    s = OptionsFlowStrategy()
    res = s.generate(_mock_snapshot({"call_oi_delta": 1000, "put_oi_delta": 1000}))
    assert res is None

def test_options_flow_bullish_bearish_maps_correctly():
    s = OptionsFlowStrategy()
    res_up = s.generate(_mock_snapshot({"call_oi_delta": 500, "put_oi_delta": 2000, "ltp_change_window": 1.0}))
    assert res_up.direction == "BUY_CALL"
    res_down = s.generate(_mock_snapshot({"call_oi_delta": 2000, "put_oi_delta": 500, "ltp_change_window": -1.0}))
    assert res_down.direction == "BUY_PUT"

def test_options_flow_nan_fails_closed():
    s = OptionsFlowStrategy()
    res = s.generate(_mock_snapshot({"call_oi_delta": float("nan"), "put_oi_delta": float("nan"), "iv_change": 0.0}))
    assert res is None

def test_options_flow_missing_fails_closed():
    s = OptionsFlowStrategy()
    res = s.generate({"symbol": "TEST", "quote_age_sec": 1.0, "spread_pct": 0.001})
    assert res is None

# TimeWindowStrategy
def test_time_window_positive_trigger():
    s = TimeWindowStrategy()
    res = s.generate(_mock_snapshot({"hour": 9, "minute": 25, "ltp_change": 1.0}))
    assert res is not None
    assert res.name == "time_window_momentum"
    assert res.direction == "BUY_CALL"

def test_time_window_negative_no_trigger():
    s = TimeWindowStrategy()
    res = s.generate(_mock_snapshot({"hour": 11, "minute": 0, "ltp_change": 1.0}))
    assert res is None

def test_time_window_bullish_bearish_maps_correctly():
    s = TimeWindowStrategy()
    res_up = s.generate(_mock_snapshot({"hour": 9, "minute": 25, "ltp_change_window": 1.0}))
    assert res_up.direction == "BUY_CALL"
    res_down = s.generate(_mock_snapshot({"hour": 9, "minute": 25, "ltp_change_window": -1.0}))
    assert res_down.direction == "BUY_PUT"

def test_time_window_nan_fails_closed():
    s = TimeWindowStrategy()
    res = s.generate(_mock_snapshot({"ltp_change": float("nan")}))
    assert res is None

def test_time_window_missing_fails_closed():
    s = TimeWindowStrategy()
    res = s.generate({"symbol": "TEST"})
    assert res is None
