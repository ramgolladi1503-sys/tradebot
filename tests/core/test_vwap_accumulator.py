import pytest
from datetime import datetime, timezone, timedelta
from core.time_utils import IST_TZ
from core.vwap_accumulator import SessionVwapAccumulator



def test_vwap_tick_accumulation():
    acc = SessionVwapAccumulator()
    ts1 = datetime(2026, 7, 12, 9, 15, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()

    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=10.0)
    snap1 = acc.get_snapshot()
    assert snap1["value"] == 100.0

    ts2 = ts1 + 1
    acc.observe_tick(ts2, ltp=110.0, cumulative_volume=30.0)
    snap2 = acc.get_snapshot()
    assert abs(snap2["value"] - 106.666666) < 1e-5

def test_vwap_session_reset():
    acc = SessionVwapAccumulator()
    # Day 1
    ts1 = datetime(2026, 7, 12, 9, 15, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()
    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=10.0)

    assert acc.get_snapshot()["value"] == 100.0
    assert acc.get_snapshot()["session_date"] == "2026-07-12"

    # Day 2
    ts2 = datetime(2026, 7, 13, 9, 15, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()
    acc.observe_tick(ts2, ltp=200.0, cumulative_volume=5.0)

    snap2 = acc.get_snapshot()
    assert snap2["value"] == 200.0
    assert snap2["session_date"] == "2026-07-13"
    assert snap2["sample_count"] == 1
    assert snap2["cumulative_volume"] == 5.0

def test_vwap_zero_volume_handling():
    acc = SessionVwapAccumulator()
    ts1 = datetime(2026, 7, 12, 9, 15, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()

    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=0.0)
    snap = acc.get_snapshot()
    assert snap["value"] is None
    assert snap["source"] == "UNAVAILABLE"
    assert snap["sample_count"] == 1
    assert snap["cumulative_volume"] == 0.0

def test_vwap_out_of_order_rejection():
    acc = SessionVwapAccumulator()
    ts1 = datetime(2026, 7, 12, 9, 15, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()

    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=10.0)

    ts0 = ts1 - 60
    acc.observe_tick(ts0, ltp=90.0, cumulative_volume=20.0)

    snap = acc.get_snapshot()
    assert snap["value"] == 100.0
    assert snap["sample_count"] == 1

def test_vwap_duplicate_tick():
    acc = SessionVwapAccumulator()
    ts1 = datetime(2026, 7, 12, 9, 15, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()

    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=10.0)

    # Duplicate tick (same timestamp, same volume)
    acc.observe_tick(ts1, ltp=105.0, cumulative_volume=10.0)

    snap = acc.get_snapshot()
    # Volume delta is 0, so VWAP should remain exactly 100.0
    assert snap["value"] == 100.0
    assert snap["cumulative_volume"] == 10.0
    assert snap["sample_count"] == 2 # We observed it, but ignored delta

def test_vwap_session_midnight_boundary():
    acc = SessionVwapAccumulator()
    # Midnight UTC is 5:30 AM IST (same day)
    # Midnight IST is 6:30 PM UTC (previous day)

    # 23:59:59 IST on July 12
    ts1 = datetime(2026, 7, 12, 23, 59, 59, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()
    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=10.0)
    assert acc.get_snapshot()["session_date"] == "2026-07-12"

    # 00:00:01 IST on July 13 (next session)
    ts2 = datetime(2026, 7, 13, 0, 0, 1, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()
    acc.observe_tick(ts2, ltp=200.0, cumulative_volume=5.0)

    snap2 = acc.get_snapshot()
    assert snap2["value"] == 200.0
    assert snap2["session_date"] == "2026-07-13"
    assert snap2["cumulative_volume"] == 5.0

def test_vwap_restart_behavior():
    acc = SessionVwapAccumulator()

    # Immediately after restart, snapshot should be UNAVAILABLE
    snap1 = acc.get_snapshot()
    assert snap1["value"] is None
    assert snap1["source"] == "UNAVAILABLE"

    # Only after seeing a tick does it become available
    ts1 = datetime(2026, 7, 12, 11, 30, tzinfo=IST_TZ).astimezone(timezone.utc).timestamp()
    acc.observe_tick(ts1, ltp=100.0, cumulative_volume=10.0)

    snap2 = acc.get_snapshot()
    assert snap2["value"] == 100.0
    assert snap2["source"] != "UNAVAILABLE"
