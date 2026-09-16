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
