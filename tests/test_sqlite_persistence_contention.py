from __future__ import annotations

import threading

from config import config as cfg
import core.feed.runtime_store as runtime_store
import core.trade_store as trade_store
from core.depth_store import DepthStore


def test_depth_and_runtime_writers_share_a_bounded_sqlite_drain(tmp_path, monkeypatch):
    db_path = tmp_path / "DEFAULT.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 32, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 2.0, raising=False)

    runtime_store.reset_runtime_persistence_for_tests()
    trade_store.init_db(force=True)
    depth = DepthStore()

    def write_depth() -> None:
        for token in range(10):
            depth.update(token, {"buy": [{"quantity": 1}], "sell": [{"quantity": 1}]})

    def write_runtime() -> None:
        for index in range(2):
            assert runtime_store.write_runtime_snapshot(
                {
                    "ts_epoch": 1_700_000_000.0 + index,
                    "ws_connected": True,
                    "subscribed_tokens_count": 2,
                    "intended_tokens_count": 2,
                    "subscribed_tokens_sample": [1, 2],
                    "source": "contention-test",
                    "runtime_state": "RUNNING",
                }
            )

    depth_thread = threading.Thread(target=write_depth)
    runtime_thread = threading.Thread(target=write_runtime)
    depth_thread.start()
    runtime_thread.start()
    depth_thread.join(timeout=10.0)
    runtime_thread.join(timeout=10.0)

    assert not depth_thread.is_alive()
    assert not runtime_thread.is_alive()
    depth_state = depth.shutdown_persistence(deadline_seconds=10.0)
    runtime_state = runtime_store.shutdown_runtime_persistence(deadline_seconds=30.0)

    assert depth_state["complete"] is True
    assert depth_state["rejected"] == 0
    assert depth_state["persisted"] == 10
    assert runtime_state["complete"] is True
    assert runtime_state["rejected"] == 0
    assert runtime_state["failures"] == 0
