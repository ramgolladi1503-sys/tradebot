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
        {"ts": "2023-10-10T09:17:00", "open": 102, "high": 102, "low": 102, "close": 102},
        {"ts": "2023-10-10T09:15:00", "open": 100, "high": 100, "low": 100, "close": 100},
        {"ts": "2023-10-10T09:15:00", "open": 101, "high": 101, "low": 101, "close": 101}, # duplicate
        {"ts": "2023-10-10T09:16:00", "open": 105, "high": 105, "low": 105, "close": 105},
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
        {"ts": "2023-10-10T09:16:30", "open": 200, "high": 200, "low": 200, "close": 200}, # Less than tail (09:17)
        {"ts": "2023-10-10T09:18:00", "open": 201, "high": 201, "low": 201, "close": 201},
    ]
    buffer.seed_bars(symbol, bad_bars)

    result_after = buffer.get_bars(symbol)
    # Should merge, truncating 09:16:30 to 09:16 and overwriting 105 with 200
    assert [b["close"] for b in result_after] == [101.0, 105.0, 102.0, 201.0]

from core.time_utils import now_ist, IST_TZ

def test_seed_bars_atomic_batch_invalid_no_mutation():
    buffer = OhlcBuffer()
    ts = now_ist().replace(second=0, microsecond=0)
    buffer.update_tick("RELIANCE", 2500.0, ts=ts)

    # invalid batch: missing timestamp
    seed_batch = [
        {"open": 2490, "high": 2500, "low": 2480, "close": 2495, "volume": 100},
        {"ts": ts - timedelta(minutes=1), "open": 2480, "high": 2490, "low": 2470, "close": 2485, "volume": 100}
    ]
    res = buffer.seed_bars("RELIANCE", seed_batch)
    assert res == {
        "accepted": False,
        "status": "INVALID_SEED_BATCH",
        "symbol": "RELIANCE",
        "seeded_bars": 0,
        "overlap_preserved": 0,
    }

    # assert no mutation
    bars = buffer.get_bars("RELIANCE")
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
            "ts": ts,
            "open": 2500.0,
            "high": 2500.0,
            "low": 2500.0,
            "close": 2500.0,
            "volume": 0,
        }
    ]

def test_seed_bars_idempotent():
    buffer = OhlcBuffer()
    ts = now_ist().replace(second=0, microsecond=0)

    seed_batch = [
        {"ts": ts - timedelta(minutes=2), "open": 2480, "high": 2490, "low": 2470, "close": 2485, "volume": 100},
        {"ts": ts - timedelta(minutes=1), "open": 2485, "high": 2495, "low": 2475, "close": 2490, "volume": 150}
    ]
    res1 = buffer.seed_bars("RELIANCE", seed_batch)
    assert res1 == {
        "accepted": True,
        "status": "SEEDED",
        "symbol": "RELIANCE",
        "seeded_bars": 2,
        "overlap_preserved": 0,
    }

    # idempotence
    res2 = buffer.seed_bars("RELIANCE", seed_batch)
    assert res2 == {
        "accepted": True,
        "status": "NO_CHANGE",
        "symbol": "RELIANCE",
        "seeded_bars": 0,
        "overlap_preserved": 2,
    }

def test_seed_bars_overlap_preserves_runtime_ohlc_volume():
    buffer = OhlcBuffer()
    ts = now_ist().replace(second=0, microsecond=0)
    buffer.update_tick("RELIANCE", 2500.0, volume=100, ts=ts)
    buffer.update_tick("RELIANCE", 2510.0, volume=50, ts=ts)

    # overlap
    seed_batch = [
        {"ts": ts - timedelta(minutes=1), "open": 2480, "high": 2490, "low": 2470, "close": 2485, "volume": 100},
        {"ts": ts, "open": 2000, "high": 2000, "low": 2000, "close": 2000, "volume": 9999}
    ]
    res = buffer.seed_bars("RELIANCE", seed_batch)
    assert res == {
        "accepted": True,
        "status": "SEEDED",
        "symbol": "RELIANCE",
        "seeded_bars": 1,
        "overlap_preserved": 1,
    }

    bars = buffer.get_bars("RELIANCE")
    # assert existing runtime survived overlapping history seed
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
            "ts": ts - timedelta(minutes=1),
            "open": 2480.0,
            "high": 2490.0,
            "low": 2470.0,
            "close": 2485.0,
            "volume": 100.0,
        },
        {
            "ts": ts,
            "open": 2500.0,
            "high": 2510.0,
            "low": 2500.0,
            "close": 2510.0,
            "volume": 150.0,
        }
    ]

def test_get_completed_bars_naive_internal_timestamp_fails_closed():
    buffer = OhlcBuffer()
    ts = datetime(2023, 10, 10, 9, 28, 0) # naive
    buffer._bars["RELIANCE"].append({"ts": ts, "close": 100})
    completed = buffer.get_completed_bars("RELIANCE", as_of=ts.replace(tzinfo=IST_TZ) + timedelta(minutes=5))
    assert completed == []

def test_get_completed_bars_mixed_timestamps_fails_closed():
    buffer = OhlcBuffer()
    ts1 = datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ)
    ts2 = datetime(2023, 10, 10, 9, 29, 0) # naive
    buffer._bars["RELIANCE"].extend([{"ts": ts1, "close": 100}, {"ts": ts2, "close": 101}])
    completed = buffer.get_completed_bars("RELIANCE", as_of=ts1 + timedelta(minutes=5))
    assert completed == []

def test_get_completed_bars_single_utc_aware_timestamp_normalized():
    buffer = OhlcBuffer()
    from datetime import timezone
    ts_utc = datetime(2023, 10, 10, 3, 58, 0, tzinfo=timezone.utc) # 09:28 IST
    buffer._bars["RELIANCE"].append({"ts": ts_utc, "close": 100})

    as_of = ts_utc + timedelta(minutes=5)
    completed = buffer.get_completed_bars("RELIANCE", as_of=as_of)
    expected_ts = ts_utc.astimezone(IST_TZ)
    assert completed == [{"ts": expected_ts, "close": 100}]
    assert completed[0]["ts"].tzinfo == IST_TZ

def test_get_completed_bars_single_ist_aware_timestamp():
    buffer = OhlcBuffer()
    ts = datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ)
    buffer._bars["RELIANCE"].append({"ts": ts, "close": 100})
    completed = buffer.get_completed_bars("RELIANCE", as_of=ts + timedelta(minutes=5))
    assert completed == [{"ts": ts, "close": 100}]
    assert completed[0]["ts"].tzinfo == IST_TZ

def test_get_completed_bars_duplicate_timestamps_after_normalization():
    buffer = OhlcBuffer()
    from datetime import timezone
    ts_utc = datetime(2023, 10, 10, 3, 58, 0, tzinfo=timezone.utc)
    ts_ist = datetime(2023, 10, 10, 9, 28, 0, tzinfo=IST_TZ)

    # same logical time, duplicate after normalization
    buffer._bars["RELIANCE"].extend([{"ts": ts_utc, "close": 100}, {"ts": ts_ist, "close": 101}])
    completed = buffer.get_completed_bars("RELIANCE", as_of=ts_ist + timedelta(minutes=5))

    # strictly fails closed because last_ts <= ts
    assert completed == []


def test_warm_seed_active_path(monkeypatch):
    import core.market_data
    from core.market_data import fetch_live_market_data, ohlc_buffer, cfg

    monkeypatch.setattr(cfg, "OHLC_MIN_BARS", 5)
    monkeypatch.setattr(cfg, "STARTUP_WARMUP_MIN_BARS", 5, raising=False)
    monkeypatch.setattr(cfg, "SYSTEM_WARMUP_MIN_BARS", 5, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["RELIANCE"])

    original_bars = getattr(ohlc_buffer, "_bars").copy()
    ohlc_buffer._bars.clear()

    now_dt = now_ist().replace(hour=9, minute=29, second=30, microsecond=0)
    forming_ts = now_dt.replace(second=0)

    ohlc_buffer.update_tick("RELIANCE", 2500.0, volume=100, ts=forming_ts)

    def mock_historical_data(*args, **kwargs):
        hist = []
        for m in range(59, 60):
            hist.append({
                "ts": now_dt.replace(hour=8, minute=m, second=0),
                "open": 2400, "high": 2410, "low": 2390, "close": 2405, "volume": 500
            })
        for m in range(0, 30):
            hist.append({
                "ts": now_dt.replace(hour=9, minute=m, second=0),
                "open": 2400, "high": 2410, "low": 2390, "close": 2405, "volume": 500
            })
        return hist

    class MockKite:
        kite = True
        def ensure(self): pass
        def resolve_index_token(self, *args): return "TOKEN"
        def historical_data(self, *args, **kwargs): return mock_historical_data(*args, **kwargs)
        def _is_historical_auth_error(self, *args): return False

    monkeypatch.setattr(core.market_data, "kite_client", MockKite())
    monkeypatch.setattr(core.market_data, "is_open", lambda **kwargs: True)
    monkeypatch.setattr(core.market_data, "now_ist", lambda: now_dt)
    monkeypatch.setattr(core.market_data, "get_ltp", lambda sym: 2500.0)

    class MockDepthStore:
        def get(self, sym): return {}
    monkeypatch.setattr(core.market_data, "depth_store", MockDepthStore())

    captured_compute_bars = []
    def mock_compute_indicators(bars, *args, **kwargs):
        captured_compute_bars.extend(bars)
        return {"rsi": 50, "last_ts": bars[-1]["ts"] if bars else None}

    monkeypatch.setattr(core.market_data, "compute_indicators", mock_compute_indicators)

    try:
        res = fetch_live_market_data(allow_history_seed=True)

        assert [snapshot["symbol"] for snapshot in res] == ["RELIANCE"]
        snapshot = res[0]

        expected_completed_timestamps = []
        for m in range(59, 60):
            expected_completed_timestamps.append(now_dt.replace(hour=8, minute=m, second=0))
        for m in range(0, 29):
            expected_completed_timestamps.append(now_dt.replace(hour=9, minute=m, second=0))

        assert [bar["ts"] for bar in captured_compute_bars] == expected_completed_timestamps

        buffer_bars = ohlc_buffer.get_bars("RELIANCE")
        assert buffer_bars[-1]["ts"] == forming_ts
        assert buffer_bars[-1]["volume"] == 100

        candle_ts = datetime.fromtimestamp(snapshot["candle_ts_epoch"], tz=IST_TZ)
        assert candle_ts == forming_ts - timedelta(minutes=1)
        assert snapshot["timestamp"] == now_dt.timestamp()
    finally:
        ohlc_buffer._bars = original_bars
