import pytest
from datetime import datetime, timezone, timedelta

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

    r1 = buffer.update_tick(symbol, 101, volume=None, ts=t_0929)
    assert r1["status"] == "NEW_BAR"
    r2 = buffer.update_tick(symbol, 102, volume=None, ts=t_0929)
    assert r2["status"] == "UPDATED_CURRENT_BAR"

    bars = buffer.get_bars(symbol)

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

def test_ohlc_buffer_rejects_late_older_bucket_without_reordering():
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
    result = buffer.update_tick(symbol, 999, volume=100, ts=t_late_0928)

    assert result["accepted"] is False
    assert result["status"] == "REJECTED_LATE_BUCKET"

    bars_after = buffer.get_bars(symbol)
    assert [bar["ts"] for bar in bars_after] == [
        expected_0928,
        expected_0929,
        expected_0931,
    ]

    assert bars_after[-1]['ts'] > bars_after[-2]['ts'], "tail timestamp is newer than the prior tail"
    assert bars_after[-1]['close'] == 105, "tail close is 105"

def test_completed_bar_boundaries():
    buffer = OhlcBuffer()
    symbol = 123
    from core.time_utils import IST_TZ

    t_0928_00 = datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ).timestamp()
    t_0929_30 = datetime(2023, 10, 10, 9, 29, 30, tzinfo=IST_TZ).timestamp()

    buffer.update_tick(symbol, 100, volume=None, ts=t_0928_00)
    buffer.update_tick(symbol, 101, volume=None, ts=t_0929_30)

    # test exact boundaries
    as_of_0928_59 = datetime(2023, 10, 10, 9, 28, 59, 999000, tzinfo=IST_TZ)
    as_of_0929_00 = datetime(2023, 10, 10, 9, 29, 0, tzinfo=IST_TZ)
    as_of_0929_59 = datetime(2023, 10, 10, 9, 29, 59, 999000, tzinfo=IST_TZ)
    as_of_0930_00 = datetime(2023, 10, 10, 9, 30, 0, tzinfo=IST_TZ)

    bars_1 = buffer.get_completed_bars(symbol, as_of=as_of_0928_59)
    assert not bars_1, "Expected 0 bars"

    bars_2 = buffer.get_completed_bars(symbol, as_of=as_of_0929_00)
    assert [b["close"] for b in bars_2] == [100], "Expected 1 bar"

    bars_3 = buffer.get_completed_bars(symbol, as_of=as_of_0929_59)
    assert [b["close"] for b in bars_3] == [100], "Expected 1 bar"

    bars_4 = buffer.get_completed_bars(symbol, as_of=as_of_0930_00)
    assert [b["close"] for b in bars_4] == [100, 101], "Expected 2 bars"

def test_fetch_live_market_data_excludes_forming_bar_from_indicators(monkeypatch):
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

        # The 09:29 bar is forming, so it should be excluded. The final completed bar is 09:28.
        assert final_bar_ts == datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ), "captured final timestamp is 09:28:00 IST"

        # Verify the buffer actually contains the forming bar
        all_buffer_bars = market_data.ohlc_buffer.get_bars(symbol)
        assert all_buffer_bars[-1]["ts"] == datetime(2023, 10, 10, 9, 29, 0, tzinfo=IST_TZ), "buffer contains the forming 09:29 bar"

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

def test_get_completed_bars_fails_closed_invalid_args():
    buffer = OhlcBuffer()
    symbol = 123
    from core.time_utils import IST_TZ

    t_0928_00 = datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ).timestamp()
    buffer.update_tick(symbol, 100, volume=None, ts=t_0928_00)

    as_of = datetime(2023, 10, 10, 9, 29, 0, tzinfo=IST_TZ)

    assert buffer.get_completed_bars(symbol, as_of="not a datetime") == []
    assert buffer.get_completed_bars(symbol, as_of=as_of, interval_seconds=-10) == []
    assert buffer.get_completed_bars(symbol, as_of=as_of, interval_seconds=0) == []
    assert buffer.get_completed_bars(symbol, as_of=as_of, interval_seconds="60") == []

def test_get_completed_bars_fails_closed_corrupted_history():
    buffer = OhlcBuffer()
    symbol = 123
    from core.time_utils import IST_TZ

    t_0928_00 = datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ)
    t_0929_00 = datetime(2023, 10, 10, 9, 29, 0, tzinfo=IST_TZ)
    t_0927_00 = datetime(2023, 10, 10, 9, 27, 0, tzinfo=IST_TZ)

    # Manually corrupt the buffer
    buffer._bars[symbol].extend([
        {"ts": t_0928_00, "close": 100},
        {"ts": t_0929_00, "close": 101},
        {"ts": t_0927_00, "close": 99}, # Out of order
    ])

    as_of = datetime(2023, 10, 10, 9, 35, 0, tzinfo=IST_TZ)
    assert buffer.get_completed_bars(symbol, as_of=as_of) == []

def test_seed_bars_normalizes_and_enforces_strict_ordering():
    buffer = OhlcBuffer()
    symbol = 123
    from core.time_utils import IST_TZ

    # Input with string times, no tz, duplicates, and out of order
    bars = [
        {"ts": "2023-10-10T09:17:00", "close": 102},
        {"ts": "2023-10-10T09:15:00", "close": 100},
        {"ts": "2023-10-10T09:15:00", "close": 101}, # duplicate
        {"ts": "2023-10-10T09:16:00", "close": 105},
    ]

    buffer.seed_bars(symbol, bars)
    result = buffer.get_bars(symbol)

    timestamps = [b["ts"] for b in result]
    expected_15 = datetime(2023, 10, 10, 9, 15, 0, tzinfo=IST_TZ)
    expected_16 = datetime(2023, 10, 10, 9, 16, 0, tzinfo=IST_TZ)
    expected_17 = datetime(2023, 10, 10, 9, 17, 0, tzinfo=IST_TZ)

    assert timestamps == [expected_15, expected_16, expected_17]

    # The duplicate should keep the last provided
    assert [b["close"] for b in result] == [101, 105, 102]

    # Try seeding bars that are older than current tail
    bad_bars = [
        {"ts": "2023-10-10T09:16:30", "close": 200}, # Less than tail (09:17)
        {"ts": "2023-10-10T09:18:00", "close": 201},
    ]
    buffer.seed_bars(symbol, bad_bars)

    result_after = buffer.get_bars(symbol)
    # Should merge, truncating 09:16:30 to 09:16 and overwriting 105 with 200
    assert [b["close"] for b in result_after] == [101, 200, 102, 201]
