import threading
import time
import pytest
from core.threadsafe_tape_buffer import (
    ThreadSafeTapeBuffer,
    IngestionTick,
    SynchronizedTapeSlice,
)

def test_exchange_clock_bucketing():
    """Verifies ticks are bucketed strictly by Exchange epoch, immune to arrival order."""
    buffer = ThreadSafeTapeBuffer(bucket_duration_ms=60_000)
    
    t_open = 1791278100000 # 09:15:00.000 ms
    
    # Ingest Spot ticks for Minute 1
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 500, token=1, symbol="NIFTY 50", price=22500.0, volume=10.0
    ))
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 25000, token=1, symbol="NIFTY 50", price=22525.0, volume=50.0
    ))
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 59000, token=1, symbol="NIFTY 50", price=22510.0, volume=40.0
    ))

    # Ingest Option tick
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 30000, token=100, symbol="NIFTY 22500 CE", price=120.0, open_interest=1000000.0
    ))
    
    # First tick of Minute 2 rolls over the bucket
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 60050, token=1, symbol="NIFTY 50", price=22515.0, volume=5.0
    ))

    snap = buffer.get_latest_snapshot()
    assert snap is not None
    assert snap.bucket_start_epoch_ms == t_open
    assert snap.bucket_end_epoch_ms == t_open + 60000
    assert snap.spot_open == 22500.0
    assert snap.spot_high == 22525.0
    assert snap.spot_low == 22500.0
    assert snap.spot_close == 22510.0
    assert snap.active_strikes_oi[22500.0][0] == 1000000.0


def test_constituent_dropout_stale_detection():
    """Verifies Section 1 Q1: RELIANCE dropping for > 3.0s flags STATE_DEGRADED fail-closed."""
    buffer = ThreadSafeTapeBuffer(bucket_duration_ms=60_000, max_stale_tolerance_ms=3_000)
    t_open = 1791278100000

    # Reliance ticks early at 09:15:10, but drops out for the rest of the minute!
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 10_000, token=2885, symbol="RELIANCE", price=2950.0, is_constituent=True, weight=0.095
    ))
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 10_000, token=1, symbol="NIFTY 50", price=22500.0, volume=10.0
    ))

    # Roll over to next minute
    buffer.ingest_tick_async(IngestionTick(
        exchange_ts_ms=t_open + 60_050, token=1, symbol="NIFTY 50", price=22505.0, volume=10.0
    ))

    snap = buffer.get_latest_snapshot()
    assert snap is not None
    # Stale by 50,000ms (> 3,000ms threshold) MUST trigger degradation
    assert snap.is_degraded is True
    assert "RELIANCE stale" in snap.degradation_reason


def test_concurrent_ingestion_and_lockfree_reading():
    """Verifies Section 1 Q8: Heavy background ingestion never deadlocks or blocks execution reader."""
    buffer = ThreadSafeTapeBuffer(bucket_duration_ms=10_000)
    stop_event = threading.Event()
    read_snapshots = []

    def writer_worker():
        t = 1791278100000
        for _ in range(500):
            buffer.ingest_tick_async(IngestionTick(
                exchange_ts_ms=t, token=1, symbol="NIFTY 50", price=22500.0 + (_ % 10), volume=1.0
            ))
            t += 100
            time.sleep(0.001)
        stop_event.set()

    def reader_worker():
        while not stop_event.is_set():
            snap = buffer.get_latest_snapshot()
            if snap:
                read_snapshots.append(snap)
            time.sleep(0.002)

    t1 = threading.Thread(target=writer_worker)
    t2 = threading.Thread(target=reader_worker)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert len(read_snapshots) > 0
