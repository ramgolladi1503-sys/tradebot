from __future__ import annotations

from config import config as cfg
import core.depth_store as depth_store_module
from core.depth_store import DepthStore
import threading
import time


def test_depth_store_rate_limits_snapshot_persistence(monkeypatch):
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 1.0, raising=False)
    calls = {"count": 0}

    def _fake_insert(*_args, **_kwargs):
        calls["count"] += 1
        return True

    monkeypatch.setattr(depth_store_module, "insert_depth_snapshot", _fake_insert)

    seq = {"items": [1000.0, 1000.2, 1001.3]}

    def _fake_time():
        return seq["items"].pop(0)

    monkeypatch.setattr(depth_store_module.time, "time", _fake_time)

    store = DepthStore()
    sample_depth = {
        "buy": [{"quantity": 10}],
        "sell": [{"quantity": 8}],
    }
    store.update(111, sample_depth)
    store.update(111, sample_depth)
    store.update(111, sample_depth)
    result = store.shutdown_persistence()

    assert calls["count"] == 2
    assert result["complete"] is True


def test_depth_persistence_runs_off_callback_thread_and_drains(monkeypatch):
    calls = []

    def _slow_insert(*_args, **_kwargs):
        time.sleep(0.03)
        calls.append(threading.current_thread().name)
        return True

    monkeypatch.setattr(depth_store_module, "insert_depth_snapshot", _slow_insert)
    store = DepthStore()
    store.update(222, {"buy": [{"quantity": 10}], "sell": [{"quantity": 8}]})
    result = store.shutdown_persistence(deadline_seconds=1.0)

    assert result["complete"] is True
    assert calls == ["depth-store-persistence"]
    assert result["persisted"] == 1
