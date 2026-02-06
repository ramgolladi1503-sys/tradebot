from strategies.ensemble import ensemble_signal

def test_ensemble_signal_trend_up():
    md = {
        "ltp": 102,
        "vwap": 100,
        "vwap_slope": 0.5,
        "rsi_mom": 1.0,
        "atr": 1.0,
        "orb_high": 101,
        "orb_low": 99,
        "vol_z": 1.0
    }
    sig = ensemble_signal(md)
    assert sig is not None
    assert sig.direction in ("BUY_CALL", "BUY_PUT")
