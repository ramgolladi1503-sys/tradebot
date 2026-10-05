from contextlib import contextmanager
import sqlite3

from config import config as cfg
from core import tick_store


def test_checkpoint_busy_after_commit_consumes_batch_once(tmp_path, monkeypatch):
    db_path = tmp_path / "ticks.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True, raising=False)
    tick_store.reset_audit_counters()
    tick_store._INIT_DONE = False
    tick_store._INIT_DB_PATH = None
    tick_store.init_ticks()

    row = (
        "2026-10-05T09:15:00Z", 7654321, 250.5, 10, 2, 1_791_185_700.0,
        "2026-10-05T09:15:00Z", "RECEIPT", "exchange_timestamp",
        1_791_185_700.0, 1_791_185_700.0, False,
    )
    with tick_store._WRITE_QUEUE_LOCK:
        tick_store._WRITE_QUEUE.append(row)
        tick_store._WRITE_ENQUEUE_COUNT = 1
    tick_store._AUDIT_COUNTERS["rows_enqueued"] = 1

    checkpoint_errors = []
    degraded = []
    real_conn_context = tick_store._conn

    class CheckpointBusyConnection:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            if sql.strip().upper().startswith("PRAGMA WAL_CHECKPOINT"):
                class BusyResult:
                    @staticmethod
                    def fetchone():
                        return (1, 1, 0)

                return BusyResult()
            return self._conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    @contextmanager
    def conn_with_busy_checkpoint():
        with real_conn_context() as conn:
            yield CheckpointBusyConnection(conn)

    monkeypatch.setattr(tick_store, "_conn", conn_with_busy_checkpoint)
    monkeypatch.setattr(tick_store, "record_degradation", lambda *args, **kwargs: degraded.append((args, kwargs)))
    monkeypatch.setattr(tick_store._ERROR_LOGGER, "write", lambda payload: checkpoint_errors.append(payload))

    assert tick_store._flush_pending_ticks(worker_owned=True) == 1
    assert tick_store._flush_pending_ticks(worker_owned=True) == 0
    assert tick_store.pending_tick_count() == 0
    assert tick_store._WRITE_FLUSH_COUNT == 1
    counters = tick_store.get_audit_counters()
    assert counters["rows_dequeued"] == 1
    assert counters["committed_batches"] == 1
    assert counters["worker_failures"] == 0
    state = tick_store.get_persistence_worker_state()
    assert state["pending_unique_rows_at_shutdown"] == 0
    assert state["in_flight_rows_at_shutdown"] == 0
    assert state["accounting_invariant_ok"] is True

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] == 1

    assert len(degraded) == 1
    assert degraded[0][0] == ("tick", "SQLITE_WAL_CHECKPOINT_BUSY")
    event = next(item for item in checkpoint_errors if item["event"] == "TICK_STORE_CHECKPOINT_DEGRADED")
    assert event["committed"] is True
    assert event["wal_limit_bytes"] == tick_store.MAX_SQLITE_WAL_BYTES


def test_precommit_failure_is_categorized_without_exception_payload(monkeypatch):
    tick_store.reset_audit_counters()
    tick_store._INIT_DONE = False
    monkeypatch.setattr(tick_store, "init_ticks", lambda: None)
    monkeypatch.setattr(
        tick_store,
        "_conn",
        lambda: (_ for _ in ()).throw(RuntimeError("secret-row-value-do-not-log")),
    )
    events = []
    monkeypatch.setattr(tick_store._ERROR_LOGGER, "write", events.append)
    monkeypatch.setattr(tick_store, "record_degradation", lambda *args, **kwargs: None)

    valid_bounded_row = (
        "2026-10-05T09:15:00Z", 7654321, 250.5, 10, 2, 1_791_185_700.0,
        "2026-10-05T09:15:00Z", "RECEIPT", "exchange_timestamp",
        1_791_185_700.0, 1_791_185_700.0, False,
    )
    assert tick_store._write_rows([valid_bounded_row]) is False
    event = next(row for row in events if row["event"] == "TICK_STORE_ERROR")
    assert event["failure_category"] == "PERSISTENCE_EXCEPTION"
    assert event["exception_type"] == "RuntimeError"
    assert "secret-row-value-do-not-log" not in repr(event)
    assert "7654321" not in repr(event)
