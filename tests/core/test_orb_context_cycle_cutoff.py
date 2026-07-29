from datetime import datetime, timedelta


def test_fetch_live_market_data_passes_cycle_cutoff_to_orb(monkeypatch):
    from config import config as cfg
    from core import market_data
    from core.time_utils import IST_TZ

    symbol = "NIFTY"
    cycle_cutoff = datetime(2026, 7, 21, 10, 0, 30, tzinfo=IST_TZ)
    captured_now_dt = []

    original_symbols = cfg.SYMBOLS
    original_min_bars = cfg.OHLC_MIN_BARS
    original_require_live_quotes = cfg.REQUIRE_LIVE_QUOTES
    original_bars = market_data.ohlc_buffer._bars.copy()

    def orb_state_spy(symbol_arg, bars, *, now_dt, segment, market_open, market_mode=None):
        captured_now_dt.append(now_dt)
        return {
            "symbol": symbol_arg,
            "window_min": 15,
            "orb_high": 105.0,
            "orb_low": 95.0,
            "bias": "UP",
            "status": "CONFIRMED",
            "window_bars": len(bars),
            "required_bars": 15,
        }

    try:
        cfg.SYMBOLS = {symbol: {}}
        cfg.OHLC_MIN_BARS = 1
        cfg.REQUIRE_LIVE_QUOTES = False
        market_data.ohlc_buffer._bars.clear()
        market_data._DATA_CACHE.clear()

        for idx in range(3):
            market_data.ohlc_buffer.update_tick(
                symbol,
                100.0 + idx,
                volume=None,
                ts=cycle_cutoff - timedelta(minutes=idx + 2),
            )

        monkeypatch.setattr(market_data, "now_ist", lambda: cycle_cutoff)
        monkeypatch.setattr(market_data, "get_ltp", lambda sym: 101.0)
        monkeypatch.setattr(market_data, "get_index_quote_snapshot", lambda sym: {})
        monkeypatch.setattr(market_data, "_refresh_index_quote_from_rest", lambda sym, force=False: None)
        monkeypatch.setattr(market_data, "update_index_quote_snapshot", lambda **kwargs: None)
        monkeypatch.setattr(market_data, "_fetch_option_chain_with_context", lambda *args, **kwargs: [])
        monkeypatch.setattr(market_data, "_hydrate_live_option_chain_liquidity", lambda symbol, chain, **kwargs: chain)
        monkeypatch.setattr(market_data, "_option_chain_health", lambda *args, **kwargs: {"ok": True})
        monkeypatch.setattr(market_data, "_orb_state_from_candles", orb_state_spy)

        rows = market_data.fetch_live_market_data(allow_history_seed=False)

        row = next(item for item in rows if item["symbol"] == symbol)
        assert captured_now_dt != []
        assert captured_now_dt == [cycle_cutoff]
        assert captured_now_dt[0] != cycle_cutoff - timedelta(seconds=1)
        assert row["orb_bias"] == "UP"
        assert row["orb_state"]["status"] == "CONFIRMED"
        assert row["timestamp_ist"] == cycle_cutoff.isoformat()
    finally:
        cfg.SYMBOLS = original_symbols
        cfg.OHLC_MIN_BARS = original_min_bars
        cfg.REQUIRE_LIVE_QUOTES = original_require_live_quotes
        market_data.ohlc_buffer._bars = original_bars
        market_data._DATA_CACHE.pop(symbol, None)
