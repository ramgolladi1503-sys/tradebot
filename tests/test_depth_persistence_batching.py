"""Tests for depth persistence batching, transaction atomicity, and throughput."""
import time
import json
import sqlite3
import threading
from pathlib import Path
import pytest

from core.trade_store import insert_depth_snapshots_batch, insert_depth_snapshot, _conn
from core.depth_store import DepthStore
from config import config as cfg
from core import tick_store


def test_insert_depth_snapshots_batch(tmp_path, monkeypatch):
    """Batch insert writes multiple rows atomically in single transaction."""
    db_file = tmp_path / "test_batch.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))

    items = [
        (f"2026-09-16T10:00:0{i}Z", 1000 + i, json.dumps({"buy": [{"price": 100.0, "quantity": 10}], "sell": []}), 1789500000.0 + i)
        for i in range(10)
    ]

    count = insert_depth_snapshots_batch(items)
    assert count == 10

    with _conn() as conn:
        rows = conn.execute("SELECT instrument_token, timestamp_epoch FROM depth_snapshots ORDER BY timestamp_epoch ASC").fetchall()
        assert len(rows) == 10
        assert rows[0][0] == 1000
        assert rows[-1][0] == 1009


def test_depth_store_persist_loop_batches(tmp_path, monkeypatch):
    """DepthStore persistence worker drains queue in batches without drops."""
    db_file = tmp_path / "test_depth_store.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 20, raising=False)

    store = DepthStore()
    sample_depth = {
        "buy": [{"price": 100.0 + i, "quantity": 10 * i, "orders": 1} for i in range(1, 6)],
        "sell": [{"price": 101.0 + i, "quantity": 10 * i, "orders": 1} for i in range(1, 6)],
    }

    # Ingest 50 snapshots
    for i in range(50):
        store.update(token_int := 2000 + (i % 5), sample_depth)

    # Allow persistence loop to drain
    state = store.shutdown_persistence(deadline_seconds=5.0)
    assert state["complete"] is True
    assert state["rejected"] == 0
    assert state["failures"] == 0
    assert state["persisted"] >= 5  # At least 1 per unique token due to 0.5s interval filter


def test_insert_depth_snapshots_batch_lock_skip(tmp_path, monkeypatch):
    """When SQLite is locked and skip_on_lock=True, batch insert returns 0 without raising."""
    import core.trade_store as ts_mod
    db_file = tmp_path / "test_locked.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    ts_mod.init_db()

    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS", 1, raising=False)

    class _LockedConn:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def executemany(self, *args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ts_mod, "_conn", lambda: _LockedConn())

    items = [
        ("2026-09-16T10:00:00Z", 1001, "{}", 1789500000.0),
        ("2026-09-16T10:00:01Z", 1002, "{}", 1789500001.0),
    ]
    persisted = insert_depth_snapshots_batch(items)
    assert persisted == 0


def test_depth_store_persist_loop_lock_skip_records_rejections_fail_closed(tmp_path, monkeypatch):
    """When batch persistence returns 0 due to lock skip, counters are not inflated and rejections are recorded."""
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 10, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    import core.depth_store as ds_mod
    monkeypatch.setattr(ds_mod, "insert_depth_snapshots_batch", lambda items: 0)

    store = DepthStore()
    rejection_file = tmp_path / "logs" / "depth_rejections.jsonl"
    store.configure_rejection_provenance(rejection_file, session_id="test_sess", producer_sha="test_sha")

    sample_depth = {
        "buy": [{"price": 100.0, "quantity": 10, "orders": 1}],
        "sell": [{"price": 101.0, "quantity": 10, "orders": 1}],
    }

    for i in range(5):
        store.update(3000 + i, sample_depth)

    state = store.shutdown_persistence(deadline_seconds=5.0)
    assert state["complete"] is True
    # FAIL-CLOSED TRUTH LAW: Zero rows persisted; unwritten rows counted as rejected, NOT persisted!
    assert state["persisted"] == 0
    assert state["rejected"] == 5
    assert state["durability_degraded"] is True

    # Rejections are recorded with LOCK_SKIPPED provenance
    assert rejection_file.exists()
    rejections = [json.loads(line) for line in rejection_file.read_text().splitlines() if line.strip()]
    assert len(rejections) == 5
    assert all(r["reason_code"] == "LOCK_SKIPPED" for r in rejections)


def test_depth_store_incident_sized_backlog_drains_with_exact_accounting(tmp_path, monkeypatch):
    """Synthetic books at the reported 37,936-item backlog scale drain exactly."""
    db_file = tmp_path / "test_burst.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 65536, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC", 3600.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 250, raising=False)

    import core.depth_store as ds_mod
    original_batch_insert = ds_mod.insert_depth_snapshots_batch
    first_batch_started = threading.Event()
    release_first_batch = threading.Event()
    batch_calls = []

    def slow_first_batch(items):
        batch_calls.append(len(items))
        if len(batch_calls) == 1:
            first_batch_started.set()
            assert release_first_batch.wait(timeout=15.0)
        return original_batch_insert(items)

    monkeypatch.setattr(ds_mod, "insert_depth_snapshots_batch", slow_first_batch)
    store = DepthStore()
    sample_depth = {
        "buy": [{"price": 100.0, "quantity": 10, "orders": 1}],
        "sell": [{"price": 101.0, "quantity": 10, "orders": 1}],
    }

    burst_count = 37936
    for i in range(burst_count):
        store.update(10000 + i, sample_depth)

    assert first_batch_started.wait(timeout=5.0)
    during_backlog = store.persistence_state()
    assert during_backlog["queue_depth"] <= 65536
    assert during_backlog["queue_rejected"] == 0
    release_first_batch.set()
    state = store.shutdown_persistence(deadline_seconds=60.0)
    assert state["complete"] is True
    assert state["queue_rejected"] == 0
    assert state["pre_enqueue_rejected"] == 0
    assert state["rejected"] == 0
    assert state["failures"] == 0
    assert state["enqueued"] == burst_count
    assert state["persisted"] == burst_count
    assert state["unaccounted_remainder"] == 0
    assert state["accounting_invariant_ok"] is True
    assert batch_calls
    assert max(batch_calls) <= 250
    assert max(batch_calls) > 1
    with _conn() as conn:
        persisted_rows = conn.execute("SELECT COUNT(*) FROM depth_snapshots").fetchone()[0]
    assert persisted_rows == burst_count


def test_depth_store_overload_rejects_visibly_and_preserves_accounting(tmp_path, monkeypatch):
    """A stalled persistence consumer causes bounded, visible rejection, never false persistence."""
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "stalled.sqlite"), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 4, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 1, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 0.01, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    import core.depth_store as ds_mod
    entered = threading.Event()
    release = threading.Event()

    def blocked_insert(*_args):
        entered.set()
        assert release.wait(timeout=10.0)
        return True

    monkeypatch.setattr(ds_mod, "insert_depth_snapshot", blocked_insert)
    store = DepthStore()
    rejection_file = tmp_path / "logs" / "depth_rejections.jsonl"
    store.configure_rejection_provenance(rejection_file, session_id="overload-test", producer_sha="test")
    sample_depth = {"buy": [{"price": 100.0, "quantity": 1}], "sell": [{"price": 101.0, "quantity": 1}]}

    store.update(1, sample_depth)
    assert entered.wait(timeout=2.0)
    for token in range(2, 6):
        store.update(token, sample_depth)
    store.update(6, sample_depth)
    saturated = store.persistence_state()
    assert saturated["queue_depth"] == 4
    assert saturated["pre_enqueue_rejected"] == 1
    assert saturated["rejected"] == 1
    assert saturated["persisted"] == 0
    assert saturated["unaccounted_remainder"] == 0

    release.set()
    final = store.shutdown_persistence(deadline_seconds=5.0)
    assert final["complete"] is True
    assert final["persisted"] == 5
    assert final["pre_enqueue_rejected"] == 1
    assert final["rejected"] == 1
    assert final["unaccounted_remainder"] == 0
    rejection_rows = [json.loads(line) for line in rejection_file.read_text().splitlines() if line.strip()]
    assert len(rejection_rows) == 1
    assert rejection_rows[0]["reason_code"] == "QUEUE_REJECTED"


def test_tick_passive_checkpoint_and_depth_writer_progress_with_pinned_reader(tmp_path, monkeypatch):
    """A pinned WAL reader degrades checkpoint progress without starving depth writes."""
    db_file = tmp_path / "shared_tick_depth.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 25, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC", 3600.0, raising=False)

    tick_store.reset_audit_counters()
    tick_store._INIT_DONE = False
    tick_store._INIT_DB_PATH = None
    tick_store.init_ticks()
    tick_row = (
        "2026-10-05T09:15:00Z", 7654321, 250.5, 10, 2, 1_791_185_700.0,
        "2026-10-05T09:15:00Z", "RECEIPT", "exchange_timestamp",
        1_791_185_700.0, 1_791_185_700.0, False,
    )
    degraded = []
    monkeypatch.setattr(tick_store, "record_degradation", lambda *args, **kwargs: degraded.append((args, kwargs)))
    monkeypatch.setattr(tick_store._ERROR_LOGGER, "write", lambda _payload: True)

    assert tick_store._write_rows([tick_row]) is True
    reader = sqlite3.connect(db_file, timeout=2.0)
    reader.execute("PRAGMA journal_mode=WAL")
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM ticks").fetchone()

    tick_result = []
    tick_done = threading.Event()

    def write_tick():
        try:
            tick_result.append(tick_store._write_rows([tuple([*tick_row[:5], tick_row[5] + 1.0, *tick_row[6:]])]))
        finally:
            tick_done.set()

    depth_store = DepthStore()
    sample_depth = {"buy": [{"price": 100.0, "quantity": 10}], "sell": [{"price": 101.0, "quantity": 9}]}
    try:
        tick_thread = threading.Thread(target=write_tick, name="test-tick-writer")
        tick_thread.start()
        assert tick_done.wait(timeout=3.0), "PASSIVE tick writer blocked behind pinned reader"
        assert tick_result == [True]

        for i in range(100):
            depth_store.update(800000 + i, sample_depth)
        depth_state = depth_store.shutdown_persistence(deadline_seconds=5.0)
        assert depth_state["complete"] is True
        assert depth_state["enqueued"] == 100
        assert depth_state["persisted"] == 100
        assert depth_state["rejected"] == 0
        assert depth_state["failures"] == 0
        assert depth_state["accounting_invariant_ok"] is True
        assert depth_state["unaccounted_remainder"] == 0

        tick_state = tick_store.get_persistence_worker_state()
        assert tick_state["wal_checkpoint_mode"] == "PASSIVE"
        assert tick_state["wal_checkpoint_incomplete"] == 1
        assert tick_state["wal_checkpoint_pending_frames_max"] > 0
        assert degraded == [(('tick', 'SQLITE_WAL_CHECKPOINT_BUSY'), {})]
    finally:
        reader.rollback()
        reader.close()
        # Ensure background resources are released even if an assertion fails.
        if 'tick_thread' in locals():
            tick_thread.join(timeout=3.0)
        if not depth_store.persistence_state()["shutdown"]:
            depth_store.shutdown_persistence(deadline_seconds=5.0)
