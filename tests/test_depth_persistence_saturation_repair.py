import queue
import threading
import time

import core.depth_store as depth_store_module
import pytest


def _item(seq):
    return (f"2026-08-05T10:00:{seq % 60:02d}.000000Z", seq, '{"depth": {}}', float(seq))


@pytest.mark.parametrize("multiplier", (1.0, 1.5, 2.0))
def test_depth_worker_batches_and_drains_observed_burst(monkeypatch, multiplier):
    batches = []

    def persist(rows):
        batches.append(len(rows))
        return len(rows)

    monkeypatch.setattr(depth_store_module, "insert_depth_snapshots", persist)
    store = depth_store_module.DepthStore()
    generated = int(4794 * multiplier)
    for seq in range(generated):
        store._persist_queue.put(_item(seq))
        with store._persist_lock:
            store._persist_enqueued += 1

    result = store.shutdown_persistence(deadline_seconds=5.0)
    state = store.persistence_state()
    assert result["complete"] is True
    assert state["queue_depth"] == 0
    assert state["rejected"] == 0
    assert state["failures"] == 0
    assert state["enqueued"] == state["persisted"] == generated
    assert max(batches) > 1


def test_depth_worker_surfaces_batch_write_failure_without_claiming_durability(monkeypatch):
    def fail(_rows):
        raise OSError("synthetic durable write failure")

    monkeypatch.setattr(depth_store_module, "insert_depth_snapshots", fail)
    store = depth_store_module.DepthStore()
    store._persist_queue.put(_item(1))
    store._persist_queue.put(_item(2))
    with store._persist_lock:
        store._persist_enqueued += 2
    result = store.shutdown_persistence(deadline_seconds=1.0)
    state = store.persistence_state()
    assert result["complete"] is True
    assert state["persisted"] == 0
    assert state["failures"] == 2
    assert state["durability_degraded"] is True
