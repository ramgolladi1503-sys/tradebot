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
    checkpoint_sql = []
    real_conn_context = tick_store._conn

    class CheckpointBusyConnection:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            if sql.strip().upper().startswith("PRAGMA WAL_CHECKPOINT"):
                checkpoint_sql.append(sql.strip())
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
    assert event["checkpoint_mode"] == "PASSIVE"
    assert checkpoint_sql == ["PRAGMA wal_checkpoint(PASSIVE)"]


def test_passive_checkpoint_does_not_block_behind_reader_and_keeps_degradation_visible(tmp_path, monkeypatch):
    db_path = tmp_path / "ticks_reader.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True, raising=False)
    tick_store.reset_audit_counters()
    tick_store._INIT_DONE = False
    tick_store._INIT_DB_PATH = None
    tick_store.init_ticks()

    def _row(token, epoch):
        timestamp = f"2026-10-05T09:15:{token:02d}Z"
        return (
            timestamp, token, 250.5, 10, 2, epoch, timestamp, "RECEIPT",
            "exchange_timestamp", epoch, epoch, False,
        )

    degraded = []
    events = []
    monkeypatch.setattr(tick_store, "record_degradation", lambda *args, **kwargs: degraded.append((args, kwargs)))
    monkeypatch.setattr(tick_store._ERROR_LOGGER, "write", lambda payload: events.append(payload))

    # Establish a durable baseline before an external reader pins its WAL snapshot.
    assert tick_store._write_rows([_row(1, 1_791_185_700.0)]) is True
    reader = sqlite3.connect(db_path, timeout=30.0)
    reader.execute("PRAGMA journal_mode=WAL")
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM ticks").fetchone()
    try:
        started = tick_store.time.monotonic()
        assert tick_store._write_rows([_row(2, 1_791_185_701.0)]) is True
        elapsed = tick_store.time.monotonic() - started
    finally:
        reader.rollback()
        reader.close()

    assert elapsed < 2.0
    assert tick_store.get_audit_counters()["wal_checkpoint_attempts"] == 2
    assert tick_store.get_audit_counters()["wal_checkpoint_incomplete"] == 1
    worker_state = tick_store.get_persistence_worker_state()
    assert worker_state["wal_checkpoint_mode"] == "PASSIVE"
    assert worker_state["wal_checkpoint_incomplete"] == 1
    assert worker_state["wal_checkpoint_pending_frames_max"] > 0
    assert degraded == [(('tick', 'SQLITE_WAL_CHECKPOINT_BUSY'), {})]
    event = next(item for item in events if item["event"] == "TICK_STORE_CHECKPOINT_DEGRADED")
    assert event["committed"] is True
    assert event["checkpoint_mode"] == "PASSIVE"
    assert event["wal_pending_frames"] > 0

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] == 2


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
