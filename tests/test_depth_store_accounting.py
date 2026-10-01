"""Tests for DepthStore accounting invariant, decoupled retention pruning, and non-stalling put backpressure."""
from __future__ import annotations

import json
import queue
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import config as cfg
import core.depth_store as depth_store_module
from core.depth_store import DepthStore, _retention_prune_allowed
from core.storage_bounds_v37 import DEPTH_QUEUE_MAX_ITEMS
from core.trade_store import prune_depth_snapshots, _conn, init_db


def test_depth_store_rejects_queue_capacity_outside_declared_bound_before_worker(monkeypatch, caplog):
    worker_creations = []
    monkeypatch.setattr(
        depth_store_module.threading,
        "Thread",
        lambda *args, **kwargs: worker_creations.append((args, kwargs)) or object(),
    )

    invalid_values = (
        (0, "DEPTH_PERSIST_QUEUE_MAXSIZE_OUT_OF_BOUNDS"),
        (-1, "DEPTH_PERSIST_QUEUE_MAXSIZE_OUT_OF_BOUNDS"),
        (DEPTH_QUEUE_MAX_ITEMS + 1, "DEPTH_PERSIST_QUEUE_MAXSIZE_OUT_OF_BOUNDS"),
        ("invalid", "DEPTH_PERSIST_QUEUE_MAXSIZE_INVALID"),
    )
    for configured_value, expected_error in invalid_values:
        monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", configured_value, raising=False)
        with pytest.raises(ValueError, match=expected_error):
            DepthStore()

    assert not worker_creations
    assert "depth_persist_queue_maxsize_invalid" in caplog.text
    assert "depth_persist_queue_maxsize_out_of_bounds" in caplog.text


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
    assert state["pre_enqueue_rejected"] == 1
    assert state["queue_rejected"] == 0
    assert state["unaccounted_remainder"] == 0
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


def test_depth_accounting_concurrent_sampling_and_writer_failure(monkeypatch, tmp_path):
    import threading
    import core.depth_store as ds_mod

    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 8, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 1.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    store = DepthStore()
    store.configure_rejection_provenance(tmp_path / "missing" / "rejections.jsonl",
                                         session_id="fixture", producer_sha="fixture-sha")
    monkeypatch.setattr(store._rejection_path.__class__, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("writer unavailable")))
    depths = {"buy": [{"price": 100.0, "quantity": 1}], "sell": [{"price": 101.0, "quantity": 1}]}
    done = threading.Event()

    def producer():
        for i in range(300):
            store.update(i + 1, depths)
        done.set()

    worker = threading.Thread(target=producer)
    worker.start()
    while not done.is_set():
        state = store.persistence_state()
        assert state["unaccounted_remainder"] == 0
        assert state["accounting_invariant_ok"] is True
        assert state["admission_accounting_invariant_ok"] is True
    worker.join()
    state = store.shutdown_persistence(deadline_seconds=5.0)
    assert state["complete"] is True
    assert state["unaccounted_remainder"] == 0
    assert state["enqueued"] == state["persisted"] + state["queue_rejected"]
    assert state["rejected"] >= state["pre_enqueue_rejected"]
    assert state["admission_accounting_invariant_ok"] is True
    assert state["provenance_write_failures"] > 0


def test_depth_worker_exception_is_terminal_and_conserved(monkeypatch):
    import core.depth_store as ds_mod

    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 4, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(ds_mod, "insert_depth_snapshots_batch", lambda items: (_ for _ in ()).throw(RuntimeError("fixture failure")))
    monkeypatch.setattr(ds_mod, "insert_depth_snapshot", lambda *item: (_ for _ in ()).throw(RuntimeError("fixture failure")))
    store = DepthStore()
    sample = {"buy": [{"price": 100.0, "quantity": 1}], "sell": [{"price": 101.0, "quantity": 1}]}
    store.update(71, sample)
    state = store.shutdown_persistence(deadline_seconds=3.0)
    assert state["complete"] is True
    assert state["enqueued"] == 1
    assert state["failures"] == 1
    assert state["persisted"] == 0
    assert state["unaccounted_remainder"] == 0
    assert state["admission_accounting_invariant_ok"] is True


def _stop_worker_without_shutdown(store):
    store._persist_stop.set()
    store._persist_wakeup.set()
    store._persist_thread.join(timeout=1.0)
    assert not store._persist_thread.is_alive()


@pytest.mark.parametrize("invalid_interval", [-0.1, float("nan")])
def test_invalid_sampling_interval_uses_conservative_default_and_is_visible(monkeypatch, invalid_interval):
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 4, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", invalid_interval, raising=False)
    store = DepthStore()
    _stop_worker_without_shutdown(store)
    store._record_rejection = lambda **kwargs: None
    sample = {"buy": [{"price": 100.0, "quantity": 1}], "sell": [{"price": 101.0, "quantity": 1}]}

    store.update(91, sample)
    store.update(91, sample)
    state = store.persistence_accounting()

    assert state["sampling_interval_ms"] == 500
    assert state["sampling_interval_config_valid"] is False
    assert state["durability_degraded"] is True
    assert state["sample_windows"] == 1
    assert state["coalesced_updates"] == 1
    assert state["admission_accounting_invariant_ok"] is True
    store.shutdown_persistence(deadline_seconds=0.0)


def test_depth_capture_is_explicitly_sampled_and_coalescing_is_accounted(monkeypatch):
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 8, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 60.0, raising=False)
    store = DepthStore()
    _stop_worker_without_shutdown(store)
    store._record_rejection = lambda **kwargs: None
    sample = {"buy": [{"price": 100.0, "quantity": 10}], "sell": [{"price": 101.0, "quantity": 10}]}

    store.update(101, sample)
    store.update(101, sample)
    store.update(101, sample)

    state = store.persistence_accounting()
    assert state["capture_mode"] == "SAMPLED_DEPTH"
    assert state["depth_input_count"] == 3
    assert state["depth_accepted_count"] == 1
    assert state["depth_persisted_count"] == 0
    assert state["depth_rejected_count"] == 0
    assert state["depth_duplicate_count"] is None
    assert state["depth_duplicate_count_status"] == "UNAVAILABLE_NO_STABLE_EVENT_ID"
    assert state["sample_windows"] == 1
    assert state["coalesced_updates"] == 2
    assert state["accounting_invariant_ok"] is True
    store.shutdown_persistence(deadline_seconds=0.0)


def test_forced_depth_queue_saturation_is_rejected_and_degraded(monkeypatch):
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 1, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    store = DepthStore()
    _stop_worker_without_shutdown(store)
    store._record_rejection = lambda **kwargs: None
    sample = {"buy": [{"price": 100.0, "quantity": 10}], "sell": [{"price": 101.0, "quantity": 10}]}

    store.update(101, sample)
    store.update(102, sample)

    state = store.persistence_accounting()
    assert state["capture_mode"] == "SAMPLED_DEPTH"
    assert state["depth_input_count"] == 2
    assert state["depth_accepted_count"] == 1
    assert state["depth_rejected_count"] == 1
    assert state["durability_degraded"] is True
    assert state["admission_accounting_invariant_ok"] is True
    store.shutdown_persistence(deadline_seconds=0.0)


def test_855_token_depth_burst_accounts_sampled_updates_without_queue_rejection(monkeypatch):
    token_count = 855
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", token_count, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.5, raising=False)
    store = DepthStore()
    _stop_worker_without_shutdown(store)
    store._record_rejection = lambda **kwargs: None
    sample = {"buy": [{"price": 100.0, "quantity": 10}], "sell": [{"price": 101.0, "quantity": 10}]}

    for token in range(1, token_count + 1):
        store.update(token, sample)
    for token in range(1, token_count + 1):
        store.update(token, sample)

    state = store.persistence_accounting()
    assert state["capture_mode"] == "SAMPLED_DEPTH"
    assert state["raw_updates_seen"] == token_count * 2
    assert state["sample_windows"] == token_count
    assert state["enqueued"] == token_count
    assert state["coalesced_updates"] == token_count
    assert state["queue_rejected"] == 0
    assert state["pre_enqueue_rejected"] == 0
    assert state["accounting_invariant_ok"] is True
    assert state["admission_accounting_invariant_ok"] is True
    store.shutdown_persistence(deadline_seconds=0.0)


def test_855_token_sampled_depth_burst_persists_to_temporary_sqlite_sink(tmp_path, monkeypatch):
    token_count = 855
    db_file = tmp_path / "depth-855-drain.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_file), raising=False)
    monkeypatch.setenv("TRADE_DB_PATH", str(db_file))
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 1024, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", 100, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 0.05, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC", 3600.0, raising=False)
    store = DepthStore()
    sample = {
        "buy": [{"price": 100.0, "quantity": 10, "orders": 1}],
        "sell": [{"price": 101.0, "quantity": 10, "orders": 1}],
    }

    for token in range(800_000, 800_000 + token_count):
        store.update(token, sample)

    state = store.shutdown_persistence(deadline_seconds=10.0)
    with _conn() as conn:
        persisted_rows = conn.execute(
            "SELECT COUNT(*) FROM depth_snapshots WHERE instrument_token BETWEEN ? AND ?",
            (800_000, 800_000 + token_count - 1),
        ).fetchone()[0]

    assert state["capture_mode"] == "SAMPLED_DEPTH"
    assert state["sampling_interval_ms"] == 0
    assert state["raw_updates_seen"] == token_count
    assert state["sample_windows"] == token_count
    assert state["enqueued"] == token_count
    assert state["persisted"] == token_count
    assert persisted_rows == token_count
    assert state["queue_rejected"] == 0
    assert state["pre_enqueue_rejected"] == 0
    assert state["failures"] == 0
    assert state["complete"] is True
    assert state["accounting_invariant_ok"] is True
    assert state["admission_accounting_invariant_ok"] is True


def test_depth_retention_prune_requires_fully_idle_persistence():
    assert _retention_prune_allowed(queue_depth=0, in_flight=0) is True
    assert _retention_prune_allowed(queue_depth=1, in_flight=0) is False
    assert _retention_prune_allowed(queue_depth=0, in_flight=1) is False
    assert _retention_prune_allowed(queue_depth=1, in_flight=1) is False
