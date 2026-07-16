import pytest
from datetime import datetime, timezone

from core.feed.tick_utils import normalized_tick_epoch
from core.ohlc_buffer import OhlcBuffer

def test_timestamp_truth_underlying():
    # underlying tick: exchange vs receipt
    payload = 1700000000.0
    receipt = 1700000001.0
    epoch = normalized_tick_epoch(
        payload_epoch=payload, receipt_epoch=receipt,
        use_receipt_time_for_options=True, is_underlying_token=True
    )
    assert epoch == payload, "Underlying tick should use payload (exchange) timestamp"

def test_timestamp_truth_option():
    # option tick: exchange vs receipt
    payload = 1700000000.0
    receipt = 1700000001.0
    epoch = normalized_tick_epoch(
        payload_epoch=payload, receipt_epoch=receipt,
        use_receipt_time_for_options=True, is_underlying_token=False
    )
    assert epoch == receipt, "Option tick should default to using receipt timestamp"

def test_timestamp_truth_delayed():
    # delayed payload: payload lag greater than max_payload_lag_sec
    payload = 1700000000.0
    receipt = 1700000005.0 # lag is 5 seconds > 2.0
    epoch = normalized_tick_epoch(
        payload_epoch=payload, receipt_epoch=receipt,
        previous_epoch=1700000000.0,
        market_open_now=True, max_payload_lag_sec=2.0,
        use_receipt_time_for_options=False, is_underlying_token=True
    )
    assert epoch == receipt, "Delayed payload should be substituted with receipt timestamp"

def test_timestamp_truth_out_of_order():
    # out-of-order payload: payload timestamp earlier than previous_epoch
    payload = 1700000000.0
    receipt = 1700000000.1
    previous = 1700000005.0
    epoch = normalized_tick_epoch(
        payload_epoch=payload, receipt_epoch=receipt,
        previous_epoch=previous,
        market_open_now=True,
        use_receipt_time_for_options=False, is_underlying_token=True
    )
    assert epoch == previous, "Out of order payload should be clamped forward to previous_epoch"

def test_ohlc_buffer_same_bucket_updates_latest_bar():
    buffer = OhlcBuffer()
    symbol = 123
    t_0929 = datetime(2023, 10, 10, 9, 29, 30, tzinfo=timezone.utc).timestamp()
    expected_bucket = datetime(2023, 10, 10, 9, 29, 0, tzinfo=timezone.utc)

    buffer.update_tick(symbol, 101, volume=None, ts=t_0929)
    buffer.update_tick(symbol, 102, volume=None, ts=t_0929)

    bars = buffer.get_bars(symbol)

    # In TradeBot, OhlcBuffer converts incoming timestamps into Asia/Kolkata aware datetimes
    from core.time_utils import IST_TZ
    expected_bucket_ist = expected_bucket.astimezone(IST_TZ)
    assert [
        {
            "ts": bar["ts"],
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
        }
        for bar in bars
    ] == [
        {
            "ts": expected_bucket_ist,
            "open": 101,
            "high": 102,
            "low": 101,
            "close": 102,
            "volume": 0,
        }
    ]

def test_ohlc_buffer_missing_minute_is_not_classified():
    buffer = OhlcBuffer()
    t1 = datetime(2023, 10, 10, 9, 15, 0, tzinfo=timezone.utc).timestamp()
    t2 = datetime(2023, 10, 10, 9, 17, 0, tzinfo=timezone.utc).timestamp()

    buffer.update_tick(1, 100, ts=t1)
    buffer.update_tick(1, 101, ts=t2)

    bars = buffer.get_bars(1)

    from core.time_utils import IST_TZ
    expected_0915 = datetime(2023, 10, 10, 9, 15, 0, tzinfo=timezone.utc).astimezone(IST_TZ)
    expected_0917 = datetime(2023, 10, 10, 9, 17, 0, tzinfo=timezone.utc).astimezone(IST_TZ)

    assert [bar["ts"] for bar in bars] == [
        expected_0915,
        expected_0917,
    ]

    assert (bars[1]["ts"] - bars[0]["ts"]).total_seconds() == 120.0

    assert "missing_reason" not in bars[0]

def test_ohlc_buffer_late_older_bucket_appends_out_of_order():
    buffer = OhlcBuffer()
    symbol = 123

    t_0928 = datetime(2023, 10, 10, 9, 28, 59, tzinfo=timezone.utc).timestamp()
    t_0929 = datetime(2023, 10, 10, 9, 29, 30, tzinfo=timezone.utc).timestamp()
    t_0931 = datetime(2023, 10, 10, 9, 31, 10, tzinfo=timezone.utc).timestamp()

    from core.time_utils import IST_TZ
    expected_0928 = datetime(2023, 10, 10, 9, 28, 0, tzinfo=timezone.utc).astimezone(IST_TZ)
    expected_0929 = datetime(2023, 10, 10, 9, 29, 0, tzinfo=timezone.utc).astimezone(IST_TZ)
    expected_0931 = datetime(2023, 10, 10, 9, 31, 0, tzinfo=timezone.utc).astimezone(IST_TZ)

    buffer.update_tick(symbol, 100, volume=None, ts=t_0928)
    buffer.update_tick(symbol, 101, volume=None, ts=t_0929)
    buffer.update_tick(symbol, 105, volume=None, ts=t_0931)

    bars_before = buffer.get_bars(symbol)
    assert [bar["ts"] for bar in bars_before] == [
        expected_0928,
        expected_0929,
        expected_0931,
    ]

    # Late 09:28 tick after a 09:31 bar exists
    t_late_0928 = datetime(2023, 10, 10, 9, 28, 55, tzinfo=timezone.utc).timestamp()
    buffer.update_tick(symbol, 999, volume=100, ts=t_late_0928)

    bars_after = buffer.get_bars(symbol)
    assert [bar["ts"] for bar in bars_after] == [
        expected_0928,
        expected_0929,
        expected_0931,
        expected_0928,
    ]

    assert bars_after[-1]['ts'] < bars_after[-2]['ts'], "tail timestamp is older than the prior tail"
    assert bars_after[-1]['close'] == 999, "tail close is 999"
    assert bars_after[-1]['volume'] == 100, "tail volume is 100"
    assert "missing_reason" not in bars_after[-1], "no rejection/classification field exists"

def test_ohlc_buffer_symbol_partitioning():
    buffer = OhlcBuffer()
    t1 = datetime(2023, 10, 10, 9, 15, 0, tzinfo=timezone.utc).timestamp()

    from core.time_utils import IST_TZ
    expected_bucket = datetime(2023, 10, 10, 9, 15, 0, tzinfo=timezone.utc).astimezone(IST_TZ)

    buffer.update_tick(1, 100, ts=t1)
    buffer.update_tick(2, 200, ts=t1)

    b1 = buffer.get_bars(1)
    b2 = buffer.get_bars(2)

    assert [bar["close"] for bar in b1] == [100]
    assert [bar["close"] for bar in b2] == [200]
    assert [bar["ts"] for bar in b1] == [expected_bucket]
    assert [bar["ts"] for bar in b2] == [expected_bucket]

def test_fetch_live_market_data_passes_forming_bar_to_indicators(monkeypatch):
    from core import market_data
    from core.time_utils import IST_TZ

    symbol = "NIFTY"
    now_ist_value = datetime(2023, 10, 10, 9, 29, 30, tzinfo=IST_TZ)
    now_utc_epoch_value = now_ist_value.timestamp()

    # Isolate global state
    from config import config as cfg
    original_bars = market_data.ohlc_buffer._bars.copy()
    original_symbols = cfg.SYMBOLS.copy()
    original_min_bars = cfg.OHLC_MIN_BARS

    cfg.SYMBOLS = {symbol: {}}
    cfg.OHLC_MIN_BARS = 0
    market_data.ohlc_buffer._bars.clear()

    try:
        from datetime import timedelta
        base_time = datetime(2023, 10, 10, 8, 59, 0, tzinfo=IST_TZ)
        # 30 bars ending before the current 09:29 minute
        for i in range(30):
            # 08:59 to 09:28
            t_hist = (base_time + timedelta(minutes=i)).timestamp()
            market_data.ohlc_buffer.update_tick(symbol, 100, volume=None, ts=t_hist)

        # Current 09:29 bar added through the active fetch path
        market_data.ohlc_buffer.update_tick(symbol, 100, volume=None, ts=now_utc_epoch_value)

        monkeypatch.setattr("core.market_data.now_ist", lambda: now_ist_value)
        monkeypatch.setattr("core.market_data.now_utc_epoch", lambda: now_utc_epoch_value)
        monkeypatch.setattr("core.market_data.get_ltp", lambda sym: 100.0)
        # Mock depth store to avoid network boundaries
        monkeypatch.setattr("core.market_data.depth_store.get", lambda sym: {})

        captured_bars = []
        original_compute_indicators = market_data.compute_indicators
        def compute_indicators_spy(bars, *args, **kwargs):
            captured_bars.extend(bars)
            return original_compute_indicators(bars, *args, **kwargs)

        monkeypatch.setattr("core.market_data.compute_indicators", compute_indicators_spy)

        all_snaps = market_data.fetch_live_market_data(allow_history_seed=False)
        snap = next((s for s in all_snaps if s["symbol"] == symbol), None)

        final_bar_ts = captured_bars[-1]["ts"]
        assert captured_bars, "compute_indicators called exactly once for tested symbol"

        timestamps = [b["ts"] for b in captured_bars]
        assert timestamps == sorted(timestamps), "captured timestamps are ordered"

        assert final_bar_ts == datetime(2023, 10, 10, 9, 29, 0, tzinfo=IST_TZ), "captured final timestamp is 09:29:00 IST"

        invocation_time = now_ist_value
        bar_start_time = final_bar_ts
        diff = (invocation_time - bar_start_time).total_seconds()
        assert 0 < diff < 60, "0 < invocation_time - final_bar_start < 60 seconds"

        assert snap["indicator_last_update_epoch"] == final_bar_ts.timestamp(), "snapshot indicator cutoff equals the forming bar timestamp"
    finally:
        market_data.ohlc_buffer._bars = original_bars
        cfg.SYMBOLS = original_symbols
        cfg.OHLC_MIN_BARS = original_min_bars

def test_zero_volume_vwap_uses_unit_volume_fallback():
    from core.indicators_live import compute_indicators

    data = []
    for i in range(35):
        t = datetime(2023, 10, 10, 9, 15 + i, 0, tzinfo=timezone.utc)
        data.append({'ts': t, 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 0})

    ind = compute_indicators(data)
    expected_fallback_vwap = 100.0

    assert ind['vwap'] == expected_fallback_vwap, "VWAP should fallback to unit volume and return equal-weight typical price"
    assert ind.get("ok") is True, "indicators ok is true"
    assert ind.get("last_ts") == data[-1]["ts"], "last_ts equals the final candle timestamp"
    assert [x["volume"] for x in data] == [0] * 35, "input contains exactly the intended number of candles"
