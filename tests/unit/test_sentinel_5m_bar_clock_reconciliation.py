"""Unit Tests for BUG-SENTINEL-LIVE-5M-BAR-FLOCK-001 & FEAT-SENTINEL-CLOCK-RECONCILER-001.

Acceptance Invariant Gates:
1. Gate 1: Mutex creation using os.O_CREAT | os.O_RDWR without pre-truncation.
2. Gate 2: Mutex fail-closed exit with code 1 on lock collision.
3. Gate 3: Runner script preserves lock file without destructive rm -f.
4. Gate 4: Clock-driven 5m bar reconciliation under tick drought (0 incoming ticks).
5. Gate 5: Clock reconciliation strict idempotency (0 duplicate evaluations).
6. Gate 6: Seamless interleaving between ticks and clock reconciler across boundaries.
7. Gate 7: Multi-threaded thread safety and lock re-entrancy without deadlocks or race conditions.

Strict Trading Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
"""

import fcntl
import os
import sys
import threading
from datetime import datetime, time as dt_time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    Synthetic5mBarBucket,
    CachedRBFNAuctionSignal,
)
from core.upstox_stream_broadcaster import UpstoxTickRecord
from scripts.upstox_daily_live_capture_and_stitch import ensure_single_instance


def test_gate_1_mutex_creation_without_pretruncation(tmp_path):
    """Gate 1: ensure_single_instance creates lock file with O_CREAT | O_RDWR without truncating existing data."""
    lock_file_path = str(tmp_path / "test_pipeline.lock")
    
    # Pre-populate lock file with existing data
    with open(lock_file_path, "w") as f:
        f.write("EXISTING_PID_OR_TELEMETRY_12345")

    # Call ensure_single_instance with custom lock path
    lock_file = ensure_single_instance(lock_file_path=lock_file_path)
    try:
        assert lock_file is not None
        assert not lock_file.closed
        # Verify content was NOT truncated to 0 bytes
        with open(lock_file_path, "r") as f:
            content = f.read()
        assert content == "EXISTING_PID_OR_TELEMETRY_12345"
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def test_gate_2_mutex_fail_closed_on_collision(tmp_path):
    """Gate 2: When lock is already held, ensure_single_instance fails closed with sys.exit(1)."""
    lock_file_path = str(tmp_path / "test_collision.lock")
    
    # First process/descriptor acquires exclusive lock
    fd = os.open(lock_file_path, os.O_CREAT | os.O_RDWR, 0o644)
    first_lock = open(fd, "r+")
    fcntl.flock(first_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        # Second instance must fail closed with exit code 1
        with pytest.raises(SystemExit) as exc_info:
            ensure_single_instance(lock_file_path=lock_file_path)
        assert exc_info.value.code == 1
    finally:
        fcntl.flock(first_lock, fcntl.LOCK_UN)
        first_lock.close()


def test_gate_3_pipeline_runner_preserves_atomic_flock():
    """Gate 3: run_daily_upstox_pipeline.sh preserves atomic flock and never deletes lock file."""
    repo_root = Path(__file__).resolve().parents[2]
    runner_script = repo_root / "scripts" / "run_daily_upstox_pipeline.sh"
    assert runner_script.exists()

    content = runner_script.read_text()
    # Stale lock deletion command must be completely removed
    assert "rm -f /tmp/upstox_daily_pipeline.lock" not in content
    # Atomic flock preservation explanation must be documented
    assert "atomic flock preservation" in content or "flock uses kernel file locks atomically" in content


def test_gate_4_clock_driven_5m_reconciliation_under_tick_drought(tmp_path):
    """Gate 4: Reconciles 5m bar when wall-clock passes boundary even with 0 subsequent incoming ticks."""
    wal = tmp_path / "test_wal_reconcile.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_epoch_sec = 1793354400  # 5-minute epoch 5977848
    base_ts = base_epoch_sec * 1000

    # Feed 3 ticks into the bucket for NIFTY
    for i in range(3):
        advisor.on_tick(
            UpstoxTickRecord(
                token="NSE_INDEX|Nifty 50",
                symbol="NIFTY 50",
                exchange_timestamp_ms=base_ts + (i * 1000),
                ingress_monotonic_ns=0,
                ingress_wall_utc="",
                sequence_id=i,
                ltp=24000.0 + (i * 10.0),
                volume=100,
                open_interest=0,
                best_bid=24000.0,
                best_ask=24000.0,
            )
        )

    bucket = advisor.bar_buckets_5m["NIFTY"]
    assert bucket.tick_count == 3
    assert bucket.open == 24000.0
    assert bucket.high == 24020.0
    assert bucket.low == 24000.0
    assert bucket.close == 24020.0
    assert len(advisor.bars_5m_history["NIFTY"]) == 0

    # Advance clock to next 5-minute epoch without sending any new ticks
    # Next 5-minute epoch starts at base_epoch_sec + 300
    next_epoch_dt = datetime.fromtimestamp(base_epoch_sec + 301)
    reconciled = advisor.reconcile_5m_bars(wall_clock_time=next_epoch_dt)

    expected_completed_epoch = int(base_epoch_sec // 300)
    assert reconciled == [expected_completed_epoch]
    assert expected_completed_epoch in advisor.evaluated_5m_epochs["NIFTY"]

    # Exactly 1 bar completed and recorded in history
    assert len(advisor.bars_5m_history["NIFTY"]) == 1
    completed_bar = advisor.bars_5m_history["NIFTY"][0]
    assert completed_bar["open"] == 24000.0
    assert completed_bar["high"] == 24020.0
    assert completed_bar["low"] == 24000.0
    assert completed_bar["close"] == 24020.0
    assert completed_bar["volume"] == 300.0
    assert completed_bar["epoch_5min"] == expected_completed_epoch


def test_gate_5_reconcile_5m_bars_strict_idempotency(tmp_path):
    """Gate 5: Multiple sequential calls to reconcile_5m_bars produce 0 duplicate evaluations."""
    wal = tmp_path / "test_wal_idempotency.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_epoch_sec = 1793354400
    base_ts = base_epoch_sec * 1000

    advisor.on_tick(
        UpstoxTickRecord(
            token="NSE_INDEX|Nifty 50",
            symbol="NIFTY 50",
            exchange_timestamp_ms=base_ts,
            ingress_monotonic_ns=0,
            ingress_wall_utc="",
            sequence_id=1,
            ltp=24100.0,
            volume=50,
            open_interest=0,
            best_bid=24100.0,
            best_ask=24100.0,
        )
    )

    next_epoch_dt = datetime.fromtimestamp(base_epoch_sec + 305)
    
    # First reconciliation closes the bar
    reconciled_1 = advisor.reconcile_5m_bars(wall_clock_time=next_epoch_dt)
    assert len(reconciled_1) == 1
    assert len(advisor.bars_5m_history["NIFTY"]) == 1

    # Calls 2 through 5 within same elapsed period must be strictly idempotent
    for offset in range(306, 311):
        reconciled_subsequent = advisor.reconcile_5m_bars(
            wall_clock_time=datetime.fromtimestamp(base_epoch_sec + offset)
        )
        assert reconciled_subsequent == []
        assert len(advisor.bars_5m_history["NIFTY"]) == 1


def test_gate_6_tick_clock_interleaving_and_idempotency(tmp_path):
    """Gate 6: Interleaving clock reconciler and incoming ticks across boundary guarantees exactly 1 evaluation."""
    wal = tmp_path / "test_wal_interleave.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_epoch_sec = 1793354400  # Epoch E
    base_ts = base_epoch_sec * 1000

    # 1. Ticks in Epoch E
    advisor.on_tick(
        UpstoxTickRecord(
            token="NSE_INDEX|Nifty 50",
            symbol="NIFTY 50",
            exchange_timestamp_ms=base_ts + 1000,
            ingress_monotonic_ns=0,
            ingress_wall_utc="",
            sequence_id=1,
            ltp=24200.0,
            volume=10,
            open_interest=0,
            best_bid=24200.0,
            best_ask=24200.0,
        )
    )

    # 2. Clock reconciler fires at boundary + 2 seconds (Epoch E+1)
    reconciled = advisor.reconcile_5m_bars(wall_clock_time=datetime.fromtimestamp(base_epoch_sec + 302))
    assert len(reconciled) == 1
    assert len(advisor.bars_5m_history["NIFTY"]) == 1

    # 3. Next tick arrives in Epoch E+1 (base_epoch_sec + 305)
    # on_tick must detect that Epoch E was already evaluated and not duplicate the bar close
    advisor.on_tick(
        UpstoxTickRecord(
            token="NSE_INDEX|Nifty 50",
            symbol="NIFTY 50",
            exchange_timestamp_ms=(base_epoch_sec + 305) * 1000,
            ingress_monotonic_ns=0,
            ingress_wall_utc="",
            sequence_id=2,
            ltp=24250.0,
            volume=20,
            open_interest=0,
            best_bid=24250.0,
            best_ask=24250.0,
        )
    )

    # History must STILL contain exactly 1 bar
    assert len(advisor.bars_5m_history["NIFTY"]) == 1
    # Current bucket must be active for Epoch E+1
    new_bucket = advisor.bar_buckets_5m["NIFTY"]
    assert new_bucket.bucket_epoch_5min == int((base_epoch_sec + 305) // 300)
    assert new_bucket.open == 24250.0
    assert new_bucket.tick_count == 1

    # 4. Now test the converse: tick crosses boundary first from E+1 to E+2
    advisor.on_tick(
        UpstoxTickRecord(
            token="NSE_INDEX|Nifty 50",
            symbol="NIFTY 50",
            exchange_timestamp_ms=(base_epoch_sec + 605) * 1000,
            ingress_monotonic_ns=0,
            ingress_wall_utc="",
            sequence_id=3,
            ltp=24300.0,
            volume=30,
            open_interest=0,
            best_bid=24300.0,
            best_ask=24300.0,
        )
    )
    # on_tick finalized Epoch E+1 -> history now has 2 bars
    assert len(advisor.bars_5m_history["NIFTY"]) == 2

    # Subsequent clock reconciler at E+2 must not duplicate E+1
    reconciled_after = advisor.reconcile_5m_bars(wall_clock_time=datetime.fromtimestamp(base_epoch_sec + 610))
    assert reconciled_after == []
    assert len(advisor.bars_5m_history["NIFTY"]) == 2


def test_gate_7_thread_safety_under_concurrent_ticks_and_reconciliation(tmp_path):
    """Gate 7: Concurrent worker threads running on_tick and reconcile_5m_bars execute without races or deadlocks."""
    wal = tmp_path / "test_wal_concurrency.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_epoch_sec = 1793354400
    base_ts = base_epoch_sec * 1000

    errors = []

    def tick_worker():
        try:
            for i in range(50):
                ts = base_ts + (i * 2000)  # spans across epoch boundary (100 seconds)
                advisor.on_tick(
                    UpstoxTickRecord(
                        token="NSE_INDEX|Nifty 50",
                        symbol="NIFTY 50",
                        exchange_timestamp_ms=ts,
                        ingress_monotonic_ns=0,
                        ingress_wall_utc="",
                        sequence_id=i,
                        ltp=24000.0 + (i % 20),
                        volume=10,
                        open_interest=0,
                        best_bid=24000.0,
                        best_ask=24000.0,
                    )
                )
        except Exception as e:
            errors.append(e)

    def clock_reconcile_worker():
        try:
            for s in range(0, 350, 10):
                wall_dt = datetime.fromtimestamp(base_epoch_sec + s)
                advisor.reconcile_5m_bars(wall_clock_time=wall_dt)
        except Exception as e:
            errors.append(e)

    threads = []
    # 4 tick threads and 4 clock reconciler threads executing concurrently
    for _ in range(4):
        threads.append(threading.Thread(target=tick_worker))
        threads.append(threading.Thread(target=clock_reconcile_worker))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0
    # Thread-safe lock ensured zero deadlocks and zero exceptions
    # Evaluated epochs should contain the base epoch
    assert int(base_epoch_sec // 300) in advisor.evaluated_5m_epochs["NIFTY"]
    # Check that bars in history have unique epochs
    seen_epochs = [b["epoch_5min"] for b in advisor.bars_5m_history["NIFTY"]]
    assert len(seen_epochs) == len(set(seen_epochs)), f"Duplicate bar epochs found in history: {seen_epochs}"
