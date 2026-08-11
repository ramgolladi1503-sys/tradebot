from strategies.nifty_intraday import generate_signal


def test_nifty_intraday_unknown_regime_fails_closed():
    debug = {}
    signal = generate_signal(
        ltp=25100.0,
        vwap=25000.0,
        bias="bullish",
        regime="mystery",
        debug_stats=debug,
    )

    assert signal is None
    assert debug["candidates_rejected_pre_score"] == 1
    assert debug["rejection_reason_counts"]["regime_not_declared_by_strategy_spec"] == 1


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
