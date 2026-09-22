"""Tests for DepthStore accounting invariant, decoupled retention pruning, and non-stalling put backpressure."""
from __future__ import annotations

import json
import queue
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import config as cfg
from core.depth_store import DepthStore
from core.trade_store import prune_depth_snapshots, _conn, init_db


def test_depth_accounting_invariant_enqueued_equals_persisted_plus_queued_plus_rejected(tmp_path, monkeypatch):
    """Prove strict accounting invariant: ENQUEUED == PERSISTED + QUEUED + REJECTED with 0 remainder."""
    db_file = tmp_path / "test_depth_accounting.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 25, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    store = DepthStore()
    sample_depth = {
        "buy": [{"price": 100.0, "quantity": 10, "orders": 1}],
        "sell": [{"price": 101.0, "quantity": 10, "orders": 1}],
    }

    # Ingest 100 snapshots across multiple tokens
    for i in range(100):
        store.update(token_int := 1000 + (i % 10), sample_depth)

    # During processing, accounting invariant must hold continuously
    accounting = store.persistence_accounting()
    assert accounting["accounting_invariant_ok"] is True
    assert accounting["unaccounted_remainder"] == 0
    assert accounting["enqueued"] == (
        accounting["persisted"] + accounting["in_flight"] + accounting["queue_depth"] + accounting["rejected"]
    )

    # Allow persistence loop to drain and shut down
    state = store.shutdown_persistence(deadline_seconds=5.0)
    assert state["complete"] is True
    assert state["queue_depth"] == 0
    assert state["enqueued"] == 100
    assert state["persisted"] == 100
    assert state["rejected"] == 0
    assert state["unaccounted_remainder"] == 0
    assert state["accounting_invariant_ok"] is True


def test_depth_accounting_invariant_under_lock_contention(tmp_path, monkeypatch):
    """Under artificial lock failure, unwritten rows are counted as rejected and accounting holds."""
    import core.depth_store as ds_mod
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 10, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    # Force insert_depth_snapshots_batch to simulate partial lock skip (write 4 out of 10)
    monkeypatch.setattr(ds_mod, "insert_depth_snapshots_batch", lambda items: min(4, len(items)))

    store = DepthStore()
    sample_depth = {
        "buy": [{"price": 100.0, "quantity": 10}],
        "sell": [{"price": 101.0, "quantity": 10}],
    }

    for i in range(20):
        store.update(2000 + i, sample_depth)

    state = store.shutdown_persistence(deadline_seconds=5.0)
    assert state["complete"] is True
    assert state["enqueued"] == 20
    assert state["persisted"] == 8  # 4 from each batch of 10
    assert state["rejected"] == 12  # 6 skipped from each batch of 10
    assert state["unaccounted_remainder"] == 0
    assert state["accounting_invariant_ok"] is True


def test_depth_put_timeout_non_stalling(monkeypatch):
    """The WebSocket callback put timeout is bounded (0.05s) to avoid stalling the live feed."""
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 1, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 0.02, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    store = DepthStore()
    # Stop the worker so it doesn't drain the 1 item
    store._persist_stop.set()
    store._persist_thread.join(timeout=1.0)

    sample_depth = {
        "buy": [{"price": 100.0, "quantity": 10}],
        "sell": [{"price": 101.0, "quantity": 10}],
    }

    # First update fills the 1-slot queue cleanly
    store.update(1, sample_depth)

    t0 = time.perf_counter()
    # Second update should timeout in ~0.02s without blocking the thread for 1.0s
    store.update(2, sample_depth)
    duration = time.perf_counter() - t0

    assert duration < 0.2  # Well within non-stalling budget (<200ms)
    state = store.persistence_state()
    assert state["enqueued"] == 1
    assert state["rejected"] == 1
    assert state["durability_degraded"] is True


def test_prune_depth_snapshots_isolated_function(tmp_path, monkeypatch):
    """prune_depth_snapshots cleans up rows older than the limit outside of insert."""
    db_file = tmp_path / "test_prune.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))

    init_db()
    with _conn() as conn:
        rows = [
            (f"2026-09-21T08:00:{i:02d}Z", 100, "{}", f"2026-09-21T08:00:{i:02d}Z", float(1000 + i))
            for i in range(50)
        ]
        conn.executemany("INSERT INTO depth_snapshots VALUES (?,?,?,?,?)", rows)

    # Prune with limit=20
    deleted = prune_depth_snapshots(limit=20)
    assert deleted == 30

    with _conn() as conn:
        remaining = conn.execute("SELECT count(*) FROM depth_snapshots").fetchone()[0]
        assert remaining == 20


def test_depth_accounting_invariant_holds_post_shutdown(tmp_path, monkeypatch):
    """Snapshots arriving after shutdown increment pre_enqueue_rejected without corrupting accounting invariant."""
    db_file = tmp_path / "test_post_shutdown.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    store = DepthStore()
    sample_depth = {
        "buy": [{"price": 100.0, "quantity": 10}],
        "sell": [{"price": 101.0, "quantity": 10}],
    }

    # Ingest 5 normal snapshots
    for i in range(5):
        store.update(5000 + i, sample_depth)

    # Shut down cleanly
    state = store.shutdown_persistence(deadline_seconds=5.0)
    assert state["complete"] is True
    assert state["enqueued"] == 5
    assert state["persisted"] == 5
    assert state["rejected"] == 0
    assert state["unaccounted_remainder"] == 0
    assert state["accounting_invariant_ok"] is True

    # Ingest 3 snapshots AFTER shutdown has set _persist_shutdown=True
    for i in range(3):
        store.update(6000 + i, sample_depth)

    state_after = store.persistence_state()
    assert state_after["enqueued"] == 5
    assert state_after["persisted"] == 5
    assert state_after["pre_enqueue_rejected"] == 3
    assert state_after["queue_rejected"] == 0
    assert state_after["rejected"] == 3
    # Invariant must remain strictly True with 0 remainder
    assert state_after["unaccounted_remainder"] == 0
    assert state_after["accounting_invariant_ok"] is True
