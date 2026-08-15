from core.live_indicator_readiness import build_live_indicator_readiness_report


def _underlying_snapshot():
    return {
        "symbol": "NIFTY",
        "instrument": "IDX",
        "ohlc_bars_count": 60,
        "indicator_last_update_epoch": 1_000.0,
        "vwap": 100.0,
        "rsi": 50.0,
        "ema": 100.0,
        "atr": 1.0,
        "compute_indicators_error": "",
    }


def _option_cycle_snapshot():
    return {"symbol": "NIFTY", "instrument": "OPT", "ltp": 100.0}


def test_readiness_requires_underlying_indicator_snapshot_not_option_row():
    underlying = build_live_indicator_readiness_report(
        [_underlying_snapshot()], now_epoch=1_030.0, warmup_min_bars=50
    )
    option_only = build_live_indicator_readiness_report(
        [_option_cycle_snapshot()], now_epoch=1_030.0, warmup_min_bars=50
    )

    assert underlying.decisions[0].ready is True
    assert underlying.decisions[0].ohlc_bars_count == 60
    assert option_only.decisions[0].ready is False
    assert "indicator_inputs_missing" in option_only.decisions[0].blockers
    assert "indicator_bars_below_warmup" in option_only.decisions[0].blockers
