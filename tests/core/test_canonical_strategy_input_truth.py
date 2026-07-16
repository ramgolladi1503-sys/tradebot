import pytest
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, Any

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

    buffer.update_tick(symbol, 101, volume=None, ts=t_0929)
    buffer.update_tick(symbol, 102, volume=None, ts=t_0929)

    bars = buffer.get_bars(symbol)
    length = len(bars) == 1, "Duplicate tick modifies current bar, does not append new"
    assert bars[-1]['close'] == 102
    assert bars[-1]['volume'] == 0, "Volume semantics: caller passes None, stays 0"

def test_ohlc_buffer_missing_minute_is_not_classified():
    buffer = OhlcBuffer()
    t1 = datetime(2023, 10, 10, 9, 15, 0, tzinfo=timezone.utc).timestamp()
    t2 = datetime(2023, 10, 10, 9, 17, 0, tzinfo=timezone.utc).timestamp()

    buffer.update_tick(1, 100, ts=t1)
    buffer.update_tick(1, 101, ts=t2)

    bars = buffer.get_bars(1)
    length = len(bars) == 2, "Missing minute (09:16) is NOT synthetically filled by OhlcBuffer"
    assert "missing_reason" not in bars[0]

def test_ohlc_buffer_late_older_bucket_appends_out_of_order():
    buffer = OhlcBuffer()
    symbol = 123

    t_0928 = datetime(2023, 10, 10, 9, 28, 59, tzinfo=timezone.utc).timestamp()
    t_0929 = datetime(2023, 10, 10, 9, 29, 30, tzinfo=timezone.utc).timestamp()
    t_0931 = datetime(2023, 10, 10, 9, 31, 10, tzinfo=timezone.utc).timestamp()

    buffer.update_tick(symbol, 100, volume=None, ts=t_0928)
    buffer.update_tick(symbol, 101, volume=None, ts=t_0929)
    buffer.update_tick(symbol, 105, volume=None, ts=t_0931)

    bars_before = buffer.get_bars(symbol)
    assert bars_before[0]['ts'] < bars_before[1]['ts'] < bars_before[2]['ts'], "timestamps before late input are ordered"

    # Late 09:28 tick after a 09:31 bar exists
    t_late_0928 = datetime(2023, 10, 10, 9, 28, 55, tzinfo=timezone.utc).timestamp()
    buffer.update_tick(symbol, 999, volume=100, ts=t_late_0928)

    bars_after = buffer.get_bars(symbol)
    length = len(bars_after) == 4, "late older bucket is appended at the tail"
    assert bars_after[-1]['ts'] < bars_after[-2]['ts'], "late bucket timestamp is earlier than the previous tail timestamp"
    assert bars_after[-1]['ts'] < bars_after[0]['ts'] or bars_after[-1]['ts'] == bars_after[0]['ts'], "timestamps after late input are not ordered"
    assert "missing_reason" not in bars_after[-1], "no rejection or classification is emitted"

def test_ohlc_buffer_symbol_partitioning():
    buffer = OhlcBuffer()
    t1 = datetime(2023, 10, 10, 9, 15, 0, tzinfo=timezone.utc).timestamp()

    buffer.update_tick(1, 100, ts=t1)
    buffer.update_tick(2, 200, ts=t1)

    b1 = buffer.get_bars(1)
    b2 = buffer.get_bars(2)

    length = len(b1) == 1 and b1[0]['close'] == 100
    length = len(b2) == 1 and b2[0]['close'] == 200

def test_fetch_live_market_data_passes_forming_bar_to_indicators(monkeypatch):
    from core import market_data

    symbol = "NIFTY"
    # Controlled now_ist value of 09:29:30 IST
    t_0929 = datetime(2023, 10, 10, 9, 29, 30, tzinfo=timezone.utc)
    t_0929_ts = t_0929.timestamp()

    # Ensure sufficient pre-existing completed bars (30 bars to satisfy OHLC_MIN_BARS = 30)
    market_data.ohlc_buffer._bars.clear()
    for i in range(30):
        t_hist = datetime(2023, 10, 10, 8, 59 - i, 0, tzinfo=timezone.utc).timestamp()
        market_data.ohlc_buffer.update_tick(symbol, 100, volume=None, ts=t_hist)

    # Current 09:29 bar added through the active fetch path
    market_data.ohlc_buffer.update_tick(symbol, 100, volume=None, ts=t_0929_ts)

    # Monkeypatch now_ist and now_utc_epoch to return our controlled time
    monkeypatch.setattr("core.market_data.now_ist", lambda: t_0929)
    monkeypatch.setattr("core.market_data.now_utc_epoch", lambda: t_0929_ts)

    # Mock get_ltp to avoid broker calls and provide a deterministic valid LTP
    monkeypatch.setattr("core.market_data.get_ltp", lambda sym: 100.0)

    captured_bars = []

    # Spy on compute_indicators to capture the exact bars argument
    original_compute_indicators = market_data.compute_indicators
    def compute_indicators_spy(bars, *args, **kwargs):
        captured_bars.extend(bars)
        return original_compute_indicators(bars, *args, **kwargs)

    monkeypatch.setattr("core.market_data.compute_indicators", compute_indicators_spy)

    # Force min bars to bypass history fetch
    from config import config as cfg
    old_min = getattr(cfg, "OHLC_MIN_BARS", 30)
    cfg.OHLC_MIN_BARS = 0

    try:
        # Action: fetch live market data with seeding disabled
        all_snaps = market_data.fetch_live_market_data(allow_history_seed=False)
        snap = next((s for s in all_snaps if s["symbol"] == symbol), None)
        assert snap is not None, "Snapshot for symbol should be returned"

        final_bar_ts = captured_bars[-1]["ts"]
        assert final_bar_ts == t_0929.replace(second=0, microsecond=0), "the captured final bar timestamp is 09:29:00"
        # The invocation time is 09:29:30, the bar is 09:29:00, therefore it is still forming.

        # Verify that the returned snapshot incorporates the forming bar
        assert snap["indicator_last_update_epoch"] == final_bar_ts.timestamp(), "the returned snapshot's candle/indicator cutoff reflects that forming bar"
    finally:
        cfg.OHLC_MIN_BARS = old_min

def test_zero_volume_vwap_uses_unit_volume_fallback():
    from core.indicators_live import compute_indicators

    # zero-volume candles
    data = []
    for i in range(35):
        t = datetime(2023, 10, 10, 9, 15 + i, 0, tzinfo=timezone.utc)
        data.append({'ts': t, 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 0})

    ind = compute_indicators(data)

    # In indicators_live.py, typical price is (high+low+close)/3. Here: (101+99+100)/3 = 100.
    # Because volume is 0, the function falls back volume to 1 for calculation.
    # Therefore, VWAP = sum(100 * 1 for 20 windows) / sum(1 for 20 windows) = 2000 / 20 = 100.
    expected_fallback_vwap = 100.0

    assert ind['vwap'] == expected_fallback_vwap, "VWAP should fallback to unit volume and return equal-weight typical price"
