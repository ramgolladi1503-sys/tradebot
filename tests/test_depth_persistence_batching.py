"""Tests for depth persistence batching, transaction atomicity, and throughput."""
import time
import json
import sqlite3
from pathlib import Path
import pytest

from core.trade_store import insert_depth_snapshots_batch, insert_depth_snapshot, _conn
from core.depth_store import DepthStore
from config import config as cfg


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
