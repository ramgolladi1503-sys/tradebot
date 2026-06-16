from strategies.nifty_intraday import generate_signal


def test_nifty_intraday_unknown_regime_is_explicitly_flagged():
    signal = generate_signal(
        ltp=25100.0,
        vwap=25000.0,
        bias="bullish",
        regime="mystery",
    )

    assert signal is not None
    assert "unknown_regime_fallback" in signal["soft_flags"]
    assert "regime_confidence_degraded" in signal["soft_flags"]
    assert signal["regime_path"] == "UNKNOWN"


def test_nifty_intraday_range_regime_uses_mean_reversion_path():
    signal = generate_signal(
        ltp=24900.0,
        vwap=25000.0,
        bias="bearish",
        regime="RANGE",
    )

    assert signal is not None
    assert signal["setup_type"] == "MEAN_REVERSION"
    assert signal["direction"] == "BUY_CALL"
    assert signal["regime_path"] == "RANGE"
