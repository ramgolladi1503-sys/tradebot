import atexit
import sqlite3
import time
import json
import threading
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from typing import Callable, Any
from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer
from core.time_utils import compute_age_sec, normalize_epoch_seconds, now_utc_epoch
from core.persistence_durability import record_degradation

_tick_window = deque(maxlen=200000)
_LAST_TICK_EPOCH = None
_LAST_TICK_BY_TOKEN: dict[int, dict] = {}
_ERROR_LOG_PATH = logs_dir() / "tick_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)
_SCHEMA_LOGGED = False
_INIT_DONE = False
_INIT_DB_PATH = None
_INIT_LOCK = threading.Lock()
_WRITE_QUEUE: deque[tuple[str, int | None, float | None, float | None, float | None, float, str]] = deque()
_WRITE_QUEUE_CAPACITY = 10000
_WRITE_QUEUE_LOCK = threading.Lock()
_WRITE_SERIAL_LOCK = threading.Lock()
_SQLITE_RETRY_COUNT = 0
_SQLITE_RETRY_EXHAUSTED_COUNT = 0
_FLUSH_THREAD: threading.Thread | None = None
_FLUSH_THREAD_STOP = threading.Event()
_FLUSH_LOCK = threading.Lock()
_FLUSH_THREAD_IDENT: int | None = None
_FLUSH_THREAD_NAME: str | None = None
_FLUSH_THREAD_JOIN_COMPLETED = False
_FLUSH_THREAD_TERMINATED = False
_QUEUE_HIGH_WATER = 0
_FLUSH_COUNT = 0
_ACCEPTING_WRITES = True
_SHUTDOWN_STARTED_MONOTONIC_NS: int | None = None
_SHUTDOWN_FINISHED_MONOTONIC_NS: int | None = None
_SHUTDOWN_STATE: str | None = None
_SHUTDOWN_RESULT: dict[str, Any] | None = None
_INITIAL_SHUTDOWN_RESULT: dict[str, Any] | None = None
_CLEANUP_SHUTDOWN_RESULT: dict[str, Any] | None = None
_LAST_ACCEPTED_ENQUEUE_MONOTONIC_NS: int | None = None
_REPLAY_PRESSURE_HOOK: Callable[[dict[str, Any]], None] | None = None
_REPLAY_PRESSURE_POST_COMMIT_HOOK: Callable[[dict[str, Any]], None] | None = None
_REPLAY_PRESSURE_SUPPRESS_IMMEDIATE_FLUSH = False
_REPLAY_PRESSURE_SUPPRESS_READ_FLUSHES = False
_AUDIT_COUNTERS = {
    "worker_started": 0,
    "rows_enqueued": 0,
    "rows_dequeued": 0,
    "committed_batches": 0,
    "worker_failures": 0,
    "writes_rejected_after_shutdown": 0,
    "writes_rejected_queue_full": 0,
}
_WRITE_ENQUEUE_COUNT = 0
_WRITE_FLUSH_COUNT = 0


@dataclass(frozen=True)
class ShutdownResult:
    status: str
    deadline_seconds: float | None
    deadline_expired: bool
    shutdown_started_monotonic_ns: int | None
    shutdown_finished_monotonic_ns: int | None
    drain_duration_ns: int | None
    join_duration_ns: int | None
    rows_enqueued: int
    rows_dequeued: int
    rows_committed: int
    committed_batches: int
    queue_depth: int
    in_flight_rows: int
    pending_writes: int
    writes_rejected_after_shutdown: int
    worker_alive: bool
    worker_daemon: bool
    worker_join_completed: bool
    worker_terminated: bool
    worker_failures: int
    final_flush_attempted: bool
    final_flush_completed: bool
    shutdown_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_token(token: int | str | None) -> int | None:
    if token is None:
        return None
    try:
        return int(token)
    except Exception:
        return None


def _db_writes_enabled() -> bool:
    value = getattr(cfg, "TICK_STORE_ENABLE_DB_WRITES", True)
    if value is None:
        return True
    return bool(value)


def _async_db_writes_enabled() -> bool:
    value = getattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True)
    if value is None:
        return True
    return bool(value)


def _flush_interval_sec() -> float:
    try:
        return max(0.05, float(getattr(cfg, "TICK_STORE_ASYNC_FLUSH_INTERVAL_SEC", 0.5) or 0.5))
    except Exception:
        return 0.5


def set_replay_pressure_hook(hook: Callable[[dict[str, Any]], None] | None) -> None:
    global _REPLAY_PRESSURE_HOOK
    _REPLAY_PRESSURE_HOOK = hook


def set_replay_pressure_post_commit_hook(hook: Callable[[dict[str, Any]], None] | None) -> None:
    global _REPLAY_PRESSURE_POST_COMMIT_HOOK
    _REPLAY_PRESSURE_POST_COMMIT_HOOK = hook


def clear_replay_pressure_hook() -> None:
    set_replay_pressure_hook(None)
    set_replay_pressure_post_commit_hook(None)


def set_replay_pressure_immediate_flush_enabled(enabled: bool) -> None:
    global _REPLAY_PRESSURE_SUPPRESS_IMMEDIATE_FLUSH
    _REPLAY_PRESSURE_SUPPRESS_IMMEDIATE_FLUSH = not bool(enabled)


def set_replay_pressure_read_flush_enabled(enabled: bool) -> None:
    global _REPLAY_PRESSURE_SUPPRESS_READ_FLUSHES
    _REPLAY_PRESSURE_SUPPRESS_READ_FLUSHES = not bool(enabled)


def _flush_batch_size() -> int:
    try:
        return max(1, int(getattr(cfg, "TICK_STORE_ASYNC_BATCH_SIZE", 1000) or 1000))
    except Exception:
        return 1000


@contextmanager
def _conn():
    db_path = ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH)))
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        with conn:
            yield conn
    finally:
        conn.close()


def _tick_columns(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute("PRAGMA table_info(ticks)").fetchall()
    except Exception:
        return set()
    cols = set()
    for row in rows:
        try:
            cols.add(str(row[1]))
        except Exception:
            continue
    return cols


def _log_schema_event(event: str, **extra) -> None:
    global _SCHEMA_LOGGED
    if _SCHEMA_LOGGED and event == "TICK_SCHEMA_OK":
        return
    payload = {
        "ts_epoch": float(time.time()),
        "event": event,
        "db_path": str(getattr(cfg, "TRADE_DB_PATH", "")),
    }
    payload.update(extra or {})
    try:
        _ERROR_LOGGER.write(payload)
    except Exception:
        pass
    if event == "TICK_SCHEMA_OK":
        _SCHEMA_LOGGED = True


def _migrate_ticks_epoch_column(conn: sqlite3.Connection) -> None:
    cols = _tick_columns(conn)
    if "timestamp_epoch" in cols:
        return
    if "ts_epoch" in cols:
        try:
            conn.execute("ALTER TABLE ticks RENAME COLUMN ts_epoch TO timestamp_epoch")
            conn.commit()
            _log_schema_event("TICK_SCHEMA_MIGRATE_RENAME_OK")
        except Exception as exc:
            _log_schema_event("TICK_SCHEMA_MIGRATE_RENAME_FAIL", error=f"{type(exc).__name__}:{exc}")
            try:
                conn.execute("ALTER TABLE ticks ADD COLUMN timestamp_epoch REAL")
                conn.execute(
                    "UPDATE ticks SET timestamp_epoch = ts_epoch WHERE timestamp_epoch IS NULL AND ts_epoch IS NOT NULL"
                )
                conn.commit()
                _log_schema_event("TICK_SCHEMA_MIGRATE_COPY_OK")
            except Exception as copy_exc:
                _log_schema_event(
                    "TICK_SCHEMA_MIGRATE_COPY_FAIL",
                    error=f"{type(copy_exc).__name__}:{copy_exc}",
                )
    else:
        try:
            conn.execute("ALTER TABLE ticks ADD COLUMN timestamp_epoch REAL")
            conn.commit()
            _log_schema_event("TICK_SCHEMA_ADD_TIMESTAMP_EPOCH_OK")
        except Exception as exc:
            _log_schema_event("TICK_SCHEMA_ADD_TIMESTAMP_EPOCH_FAIL", error=f"{type(exc).__name__}:{exc}")


def init_ticks() -> None:
    global _INIT_DONE, _INIT_DB_PATH
    current_db_path = str(getattr(cfg, "TRADE_DB_PATH", "") or "")
    if _INIT_DONE and _INIT_DB_PATH == current_db_path:
        return
    with _INIT_LOCK:
        current_db_path = str(getattr(cfg, "TRADE_DB_PATH", "") or "")
        if _INIT_DONE and _INIT_DB_PATH == current_db_path:
            return
        with _conn() as conn:
            conn.execute(
                """
        CREATE TABLE IF NOT EXISTS ticks (
            timestamp TEXT,
            instrument_token INTEGER,
            last_price REAL,
            volume INTEGER,
            oi INTEGER,
            timestamp_epoch REAL,
            timestamp_iso TEXT
        )
        """
            )
            _migrate_ticks_epoch_column(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_token_epoch ON ticks(instrument_token, timestamp_epoch)")
            try:
                conn.execute("ALTER TABLE ticks ADD COLUMN timestamp_iso TEXT")
            except Exception:
                pass
            cols = _tick_columns(conn)
            if "timestamp_epoch" not in cols:
                _log_schema_event("TICK_SCHEMA_INVALID", columns=sorted(cols))
                raise RuntimeError("ticks schema invalid: missing timestamp_epoch")
            _log_schema_event("TICK_SCHEMA_OK", columns=sorted(cols))
        _INIT_DONE = True
        _INIT_DB_PATH = current_db_path


def _to_epoch(ts):
    return normalize_epoch_seconds(ts)


def _parse_ts_epoch(ts):
    return normalize_epoch_seconds(ts)


def get_max_tick_epoch(conn: sqlite3.Connection) -> float | None:
    try:
        if not _REPLAY_PRESSURE_SUPPRESS_READ_FLUSHES:
            _flush_pending_ticks()
    except Exception:
        pass
    try:
        row = conn.execute("SELECT MAX(timestamp_epoch) FROM ticks").fetchone()
    except Exception:
        return None
    if not row:
        return None
    return _to_epoch(row[0])


def get_max_tick_epoch_db(tokens: list[int] | None = None) -> float | None:
    try:
        init_ticks()
        with _conn() as conn:
            if not tokens:
                return get_max_tick_epoch(conn)
            token_list = [t for t in (_normalize_token(v) for v in list(tokens)) if t is not None]
            if not token_list:
                return None
            latest = None
            chunk_size = 900
            for idx in range(0, len(token_list), chunk_size):
                chunk = token_list[idx : idx + chunk_size]
                q_marks = ",".join(["?"] * len(chunk))
                row = conn.execute(
                    f"SELECT MAX(timestamp_epoch) FROM ticks WHERE instrument_token IN ({q_marks})",
                    tuple(chunk),
                ).fetchone()
                val = _to_epoch(row[0] if row else None)
                if val is None:
                    continue
                if latest is None or val > latest:
                    latest = val
            return latest
    except Exception:
        return None


def get_max_tick_epoch_db_no_flush(tokens: list[int] | None = None) -> float | None:
    try:
        init_ticks()
        with _conn() as conn:
            cols = _tick_columns(conn)
            if "timestamp_epoch" not in cols:
                return None
            if not tokens:
                row = conn.execute("SELECT MAX(timestamp_epoch) FROM ticks").fetchone()
                return _to_epoch(row[0] if row else None)
            token_list = [t for t in (_normalize_token(v) for v in list(tokens)) if t is not None]
            if not token_list:
                return None
            latest = None
            chunk_size = 900
            for idx in range(0, len(token_list), chunk_size):
                chunk = token_list[idx : idx + chunk_size]
                q_marks = ",".join(["?"] * len(chunk))
                row = conn.execute(
                    f"SELECT MAX(timestamp_epoch) FROM ticks WHERE instrument_token IN ({q_marks})",
                    tuple(chunk),
                ).fetchone()
                val = _to_epoch(row[0] if row else None)
                if val is None:
                    continue
                if latest is None or val > latest:
                    latest = val
            return latest
    except Exception:
        return None


def get_last_tick_for_token(
    conn: sqlite3.Connection, token: int | str | None
) -> tuple[float | None, float | None] | None:
    if token is None:
        return None
    try:
        token_int = int(token)
    except Exception:
        return None
    cols = _tick_columns(conn)
    if "timestamp_epoch" not in cols or "instrument_token" not in cols:
        return None
    last_price_expr = "last_price" if "last_price" in cols else "NULL"
    try:
        row = conn.execute(
            f"SELECT {last_price_expr} AS last_price, timestamp_epoch FROM ticks "
            "WHERE instrument_token=? ORDER BY timestamp_epoch DESC LIMIT 1",
            (token_int,),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    ltp = None
    ts_epoch = _to_epoch(row[1])
    try:
        if row[0] is not None:
            ltp = float(row[0])
    except Exception:
        ltp = None
    return ltp, ts_epoch


def get_latest_tick_db(token: int) -> dict | None:
    token_int = _normalize_token(token)
    if token_int is None:
        return None
    try:
        if not _REPLAY_PRESSURE_SUPPRESS_READ_FLUSHES:
            _flush_pending_ticks()
    except Exception:
        pass
    try:
        init_ticks()
        with _conn() as conn:
            cols = _tick_columns(conn)
            if "timestamp_epoch" not in cols or "instrument_token" not in cols:
                return None
            last_price_expr = "last_price" if "last_price" in cols else "NULL"
            volume_expr = "volume" if "volume" in cols else "NULL"
            oi_expr = "oi" if "oi" in cols else "NULL"
            row = conn.execute(
                f"""
                SELECT {last_price_expr} AS last_price, timestamp_epoch, {volume_expr} AS volume, {oi_expr} AS oi
                FROM ticks
                WHERE instrument_token=?
                ORDER BY timestamp_epoch DESC
                LIMIT 1
                """,
                (token_int,),
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    ltp = None
    try:
        if row[0] is not None:
            ltp = float(row[0])
    except Exception:
        ltp = None
    volume = None
    oi = None
    try:
        if row[2] is not None:
            volume = float(row[2])
    except Exception:
        volume = None
    try:
        if row[3] is not None:
            oi = float(row[3])
    except Exception:
        oi = None
    return {
        "instrument_token": token_int,
        "ltp": ltp,
        "ts_epoch": _to_epoch(row[1]),
        "volume": volume,
        "oi": oi,
        "source": "sqlite",
    }


def get_latest_tick_rows_db(tokens: list[int]) -> dict[int, dict]:
    token_list = [t for t in (_normalize_token(v) for v in list(tokens or [])) if t is not None]
    if not token_list:
        return {}
    out: dict[int, dict] = {}
    try:
        if not _REPLAY_PRESSURE_SUPPRESS_READ_FLUSHES:
            _flush_pending_ticks()
    except Exception:
        pass
    try:
        init_ticks()
        with _conn() as conn:
            cols = _tick_columns(conn)
            if "timestamp_epoch" not in cols or "instrument_token" not in cols:
                return out
            last_price_expr = "last_price" if "last_price" in cols else "NULL"
            volume_expr = "volume" if "volume" in cols else "NULL"
            oi_expr = "oi" if "oi" in cols else "NULL"
            chunk_size = 900
            for idx in range(0, len(token_list), chunk_size):
                chunk = token_list[idx : idx + chunk_size]
                q_marks = ",".join(["?"] * len(chunk))
                rows = conn.execute(
                    f"""
                    SELECT instrument_token, {last_price_expr} AS last_price, MAX(timestamp_epoch) AS timestamp_epoch, {volume_expr} AS volume, {oi_expr} AS oi
                    FROM ticks
                    WHERE instrument_token IN ({q_marks})
                    GROUP BY instrument_token
                    """,
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    token_int = _normalize_token(row[0])
                    if token_int is None or token_int in out:
                        continue
                    ltp = None
                    try:
                        if row[1] is not None:
                            ltp = float(row[1])
                    except Exception:
                        ltp = None
                    volume = None
                    oi = None
                    try:
                        if row[3] is not None:
                            volume = float(row[3])
                    except Exception:
                        volume = None
                    try:
                        if row[4] is not None:
                            oi = float(row[4])
                    except Exception:
                        oi = None
                    out[token_int] = {
                        "instrument_token": token_int,
                        "ltp": ltp,
                        "ts_epoch": _to_epoch(row[2]),
                        "volume": volume,
                        "oi": oi,
                        "source": "sqlite",
                    }
    except Exception:
        return out
    return out


def get_latest_tick_rows_db_no_flush(tokens: list[int]) -> dict[int, dict]:
    token_list = [t for t in (_normalize_token(v) for v in list(tokens or [])) if t is not None]
    if not token_list:
        return {}
    out: dict[int, dict] = {}
    try:
        init_ticks()
        with _conn() as conn:
            cols = _tick_columns(conn)
            if "timestamp_epoch" not in cols or "instrument_token" not in cols:
                return out
            last_price_expr = "last_price" if "last_price" in cols else "NULL"
            volume_expr = "volume" if "volume" in cols else "NULL"
            oi_expr = "oi" if "oi" in cols else "NULL"
            for token in token_list:
                rows = conn.execute(
                    f"""
                    SELECT instrument_token, {last_price_expr} AS last_price, timestamp_epoch, {volume_expr} AS volume, {oi_expr} AS oi
                    FROM ticks
                    WHERE instrument_token = ?
                    ORDER BY timestamp_epoch DESC
                    LIMIT 1
                    """,
                    (token,),
                ).fetchall()
                for row in rows:
                    token_int = _normalize_token(row[0])
                    if token_int is None or token_int in out:
                        continue
                    ltp = None
                    try:
                        if row[1] is not None:
                            ltp = float(row[1])
                    except Exception:
                        ltp = None
                    volume = None
                    oi = None
                    try:
                        if row[3] is not None:
                            volume = float(row[3])
                    except Exception:
                        volume = None
                    try:
                        if row[4] is not None:
                            oi = float(row[4])
                    except Exception:
                        oi = None
                    out[token_int] = {
                        "instrument_token": token_int,
                        "ltp": ltp,
                        "ts_epoch": _to_epoch(row[2]),
                        "volume": volume,
                        "oi": oi,
                        "source": "sqlite",
                    }
    except Exception:
        return out
    return out


def record_tick_epoch(ts_epoch):
    if ts_epoch is None:
        return
    global _LAST_TICK_EPOCH
    try:
        ts_val = float(ts_epoch)
    except Exception:
        return
    _LAST_TICK_EPOCH = ts_val
    _tick_window.append(ts_val)


def _write_rows(
    rows: list[tuple[str, int | None, float | None, float | None, float | None, float, str]],
    *,
    worker_owned: bool = False,
) -> bool:
    global _WRITE_FLUSH_COUNT, _SQLITE_RETRY_COUNT, _SQLITE_RETRY_EXHAUSTED_COUNT
    if not rows:
        return True
    try:
        if worker_owned and _async_db_writes_enabled() and _REPLAY_PRESSURE_HOOK is not None:
            try:
                _REPLAY_PRESSURE_HOOK(
                    {
                        "batch_rows": len(rows),
                        "batch_size": len(rows),
                        "queue_depth": write_queue_depth(),
                        "pending_writes": max(0, _WRITE_ENQUEUE_COUNT - _WRITE_FLUSH_COUNT),
                        "rows_enqueued": _AUDIT_COUNTERS["rows_enqueued"],
                        "rows_dequeued": _AUDIT_COUNTERS["rows_dequeued"],
                        "committed_rows": _WRITE_FLUSH_COUNT,
                        "committed_batches": _AUDIT_COUNTERS["committed_batches"],
                        "worker_started": _AUDIT_COUNTERS["worker_started"],
                        "worker_thread_name": _FLUSH_THREAD_NAME,
                        "stage": "before_commit",
                        "monotonic_ns": time.monotonic_ns(),
                    }
                )
            except Exception:
                pass
        init_ticks()
        with _WRITE_SERIAL_LOCK:
            for attempt in range(3):
                try:
                    with _conn() as conn:
                        conn.executemany(
                            """
                        INSERT INTO ticks (timestamp, instrument_token, last_price, volume, oi, timestamp_epoch, timestamp_iso)
                        VALUES (?,?,?,?,?,?,?)
                        """,
                            rows,
                        )
                        conn.commit()
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == 2:
                        _SQLITE_RETRY_EXHAUSTED_COUNT += 1
                        raise
                    _SQLITE_RETRY_COUNT += 1
                    time.sleep(0.02 * (attempt + 1))
        _AUDIT_COUNTERS["committed_batches"] += 1
        if worker_owned and _async_db_writes_enabled() and _REPLAY_PRESSURE_POST_COMMIT_HOOK is not None:
            try:
                _REPLAY_PRESSURE_POST_COMMIT_HOOK(
                    {
                        "batch_rows": len(rows),
                        "batch_size": len(rows),
                        "queue_depth": write_queue_depth(),
                        "pending_writes": max(0, _WRITE_ENQUEUE_COUNT - _WRITE_FLUSH_COUNT),
                        "rows_enqueued": _AUDIT_COUNTERS["rows_enqueued"],
                        "rows_dequeued": _AUDIT_COUNTERS["rows_dequeued"],
                        "committed_rows": _WRITE_FLUSH_COUNT,
                        "committed_batches": _AUDIT_COUNTERS["committed_batches"],
                        "worker_started": _AUDIT_COUNTERS["worker_started"],
                        "worker_thread_name": _FLUSH_THREAD_NAME,
                        "stage": "after_commit",
                        "monotonic_ns": time.monotonic_ns(),
                    }
                )
            except Exception:
                pass
        try:
            from core.feed_robustness_evidence import collector
            for row in rows:
                collector.persisted_row(row[1], row[5], row[2], row[3], row[4])
        except Exception:
            pass
        _WRITE_FLUSH_COUNT += len(rows)
        return True
    except Exception as exc:
        _AUDIT_COUNTERS["worker_failures"] += 1
        try:
            _ERROR_LOGGER.write(
                {
                    "ts_epoch": time.time(),
                    "event": "TICK_STORE_ERROR",
                    "row_count": len(rows),
                    "error": str(exc),
                }
            )
        except Exception:
            pass
        return False


def _flush_pending_ticks(max_rows: int | None = None, *, worker_owned: bool = False) -> int:
    global _FLUSH_COUNT, _QUEUE_HIGH_WATER
    batch_limit = max_rows if max_rows is not None else _flush_batch_size()
    rows: list[tuple[str, int | None, float | None, float | None, float | None, float, str]] = []
    with _WRITE_QUEUE_LOCK:
        while _WRITE_QUEUE and len(rows) < batch_limit:
            rows.append(_WRITE_QUEUE.popleft())
        _QUEUE_HIGH_WATER = max(_QUEUE_HIGH_WATER, len(_WRITE_QUEUE))
    if not rows:
        return 0
    _FLUSH_COUNT += 1
    _AUDIT_COUNTERS["rows_dequeued"] += len(rows)
    if _write_rows(rows, worker_owned=worker_owned):
        return len(rows)
    with _WRITE_QUEUE_LOCK:
        for row in reversed(rows):
            _WRITE_QUEUE.appendleft(row)
    return 0


def flush_pending_ticks(max_rows: int | None = None) -> int:
    return _flush_pending_ticks(max_rows=max_rows)


def pending_tick_count() -> int:
    with _WRITE_QUEUE_LOCK:
        return len(_WRITE_QUEUE)


def get_audit_counters() -> dict[str, int]:
    payload = dict(_AUDIT_COUNTERS)
    payload.update({
        "sqlite_retry_count": int(_SQLITE_RETRY_COUNT),
        "sqlite_retry_exhausted_count": int(_SQLITE_RETRY_EXHAUSTED_COUNT),
        "sqlite_busy_timeout_ms": 30000,
    })
    return payload


def reset_audit_counters() -> None:
    global _ACCEPTING_WRITES, _SHUTDOWN_STARTED_MONOTONIC_NS, _SHUTDOWN_FINISHED_MONOTONIC_NS
    global _SHUTDOWN_STATE, _SHUTDOWN_RESULT, _INITIAL_SHUTDOWN_RESULT, _CLEANUP_SHUTDOWN_RESULT
    global _LAST_ACCEPTED_ENQUEUE_MONOTONIC_NS
    global _WRITE_ENQUEUE_COUNT, _WRITE_FLUSH_COUNT, _QUEUE_HIGH_WATER, _FLUSH_COUNT
    global _INIT_DONE, _INIT_DB_PATH
    global _FLUSH_THREAD_JOIN_COMPLETED, _FLUSH_THREAD_TERMINATED
    for key in _AUDIT_COUNTERS:
        _AUDIT_COUNTERS[key] = 0
    _ACCEPTING_WRITES = True
    _SHUTDOWN_STARTED_MONOTONIC_NS = None
    _SHUTDOWN_FINISHED_MONOTONIC_NS = None
    _SHUTDOWN_STATE = None
    _SHUTDOWN_RESULT = None
    _INITIAL_SHUTDOWN_RESULT = None
    _CLEANUP_SHUTDOWN_RESULT = None
    _LAST_ACCEPTED_ENQUEUE_MONOTONIC_NS = None
    _WRITE_ENQUEUE_COUNT = 0
    _WRITE_FLUSH_COUNT = 0
    _QUEUE_HIGH_WATER = 0
    _FLUSH_COUNT = 0
    _INIT_DONE = False
    _INIT_DB_PATH = None
    _FLUSH_THREAD_JOIN_COMPLETED = False
    _FLUSH_THREAD_TERMINATED = False
    with _WRITE_QUEUE_LOCK:
        _WRITE_QUEUE.clear()


def reset_runtime_state_for_tests() -> None:
    """Reset the process-wide tick persistence singleton between tests.

    Tests that exercise shutdown intentionally close write acceptance. Cache-only
    cleanup is insufficient because the next test then inherits a terminal worker
    lifecycle. This helper is deliberately explicit and must not be called by live
    runtime code.
    """
    global _FLUSH_THREAD, _FLUSH_THREAD_IDENT, _FLUSH_THREAD_NAME, _LAST_TICK_EPOCH
    shutdown_persistence_worker(deadline_seconds=1.0)
    reset_audit_counters()
    clear_replay_pressure_hook()
    set_replay_pressure_immediate_flush_enabled(True)
    set_replay_pressure_read_flush_enabled(True)
    _LAST_TICK_EPOCH = None
    _LAST_TICK_BY_TOKEN.clear()
    _tick_window.clear()
    _FLUSH_THREAD = None
    _FLUSH_THREAD_IDENT = None
    _FLUSH_THREAD_NAME = None


def _flush_loop() -> None:
    global _FLUSH_THREAD_TERMINATED
    while not _FLUSH_THREAD_STOP.is_set():
        _FLUSH_THREAD_STOP.wait(_flush_interval_sec())
        if _FLUSH_LOCK.acquire(blocking=False):
            try:
                while _flush_pending_ticks(worker_owned=True) > 0:
                    pass
            finally:
                _FLUSH_LOCK.release()
    if _FLUSH_LOCK.acquire(blocking=False):
        try:
                while _flush_pending_ticks() > 0:
                    pass
        finally:
            _FLUSH_LOCK.release()
    _FLUSH_THREAD_TERMINATED = True


def _ensure_flush_thread() -> None:
    global _FLUSH_THREAD, _FLUSH_THREAD_IDENT, _FLUSH_THREAD_NAME, _FLUSH_THREAD_TERMINATED, _FLUSH_THREAD_JOIN_COMPLETED
    if _FLUSH_THREAD is not None and _FLUSH_THREAD.is_alive():
        return
    with _INIT_LOCK:
        if _FLUSH_THREAD is not None and _FLUSH_THREAD.is_alive():
            return
        _FLUSH_THREAD_TERMINATED = False
        _FLUSH_THREAD_JOIN_COMPLETED = False
        _FLUSH_THREAD_STOP.clear()
        _FLUSH_THREAD = threading.Thread(target=_flush_loop, name="tick-store-flush", daemon=True)
        _FLUSH_THREAD.start()
        _FLUSH_THREAD_IDENT = _FLUSH_THREAD.ident
        _FLUSH_THREAD_NAME = _FLUSH_THREAD.name
        _AUDIT_COUNTERS["worker_started"] += 1


def _enqueue_row(row: tuple[str, int | None, float | None, float | None, float | None, float, str]) -> bool:
    global _WRITE_ENQUEUE_COUNT, _QUEUE_HIGH_WATER, _LAST_ACCEPTED_ENQUEUE_MONOTONIC_NS
    with _WRITE_QUEUE_LOCK:
        if not _ACCEPTING_WRITES:
            _AUDIT_COUNTERS["writes_rejected_after_shutdown"] += 1
            return False
        if len(_WRITE_QUEUE) >= _WRITE_QUEUE_CAPACITY:
            _AUDIT_COUNTERS["writes_rejected_queue_full"] += 1
            record_degradation("tick", "TICK_QUEUE_FULL")
            return False
        _WRITE_QUEUE.append(row)
        _AUDIT_COUNTERS["rows_enqueued"] += 1
        _WRITE_ENQUEUE_COUNT += 1
        _QUEUE_HIGH_WATER = max(_QUEUE_HIGH_WATER, len(_WRITE_QUEUE))
        _LAST_ACCEPTED_ENQUEUE_MONOTONIC_NS = time.monotonic_ns()
    _ensure_flush_thread()
    return True


def _snapshot_shutdown_result(
    *,
    status: str,
    shutdown_state: str | None,
    deadline_seconds: float | None,
    deadline_expired: bool,
    shutdown_started_monotonic_ns: int | None,
    shutdown_finished_monotonic_ns: int | None,
    drain_duration_ns: int | None,
    join_duration_ns: int | None,
    final_flush_attempted: bool,
    final_flush_completed: bool,
    thread: threading.Thread | None,
) -> dict[str, Any]:
    worker_alive = bool(thread is not None and thread.is_alive())
    result = ShutdownResult(
        status=status,
        deadline_seconds=deadline_seconds,
        deadline_expired=deadline_expired,
        shutdown_started_monotonic_ns=shutdown_started_monotonic_ns,
        shutdown_finished_monotonic_ns=shutdown_finished_monotonic_ns,
        drain_duration_ns=drain_duration_ns,
        join_duration_ns=join_duration_ns,
        rows_enqueued=_AUDIT_COUNTERS["rows_enqueued"],
        rows_dequeued=_AUDIT_COUNTERS["rows_dequeued"],
        rows_committed=_WRITE_FLUSH_COUNT,
        committed_batches=_AUDIT_COUNTERS["committed_batches"],
        queue_depth=write_queue_depth(),
        in_flight_rows=max(0, _AUDIT_COUNTERS["rows_dequeued"] - _WRITE_FLUSH_COUNT),
        pending_writes=max(0, _WRITE_ENQUEUE_COUNT - _WRITE_FLUSH_COUNT),
        writes_rejected_after_shutdown=_AUDIT_COUNTERS["writes_rejected_after_shutdown"],
        worker_alive=worker_alive,
        worker_daemon=bool(thread.daemon) if thread is not None else False,
        worker_join_completed=not worker_alive,
        worker_terminated=not worker_alive,
        worker_failures=_AUDIT_COUNTERS["worker_failures"],
        final_flush_attempted=final_flush_attempted,
        final_flush_completed=final_flush_completed,
        shutdown_state=shutdown_state or status,
    ).to_dict()
    return result


def _shutdown_flush_thread(*, deadline_seconds: float | None = None) -> dict[str, Any]:
    global _FLUSH_THREAD_JOIN_COMPLETED, _ACCEPTING_WRITES, _SHUTDOWN_STARTED_MONOTONIC_NS
    global _SHUTDOWN_FINISHED_MONOTONIC_NS, _SHUTDOWN_STATE, _SHUTDOWN_RESULT
    global _INITIAL_SHUTDOWN_RESULT, _CLEANUP_SHUTDOWN_RESULT
    thread = _FLUSH_THREAD
    if (
        _SHUTDOWN_RESULT is not None
        and _SHUTDOWN_RESULT.get("status") in {"COMPLETE_DRAIN", "WORKER_FAILURE"}
        and (thread is None or not thread.is_alive())
    ):
        return dict(_SHUTDOWN_RESULT)

    shutdown_started_monotonic_ns = time.monotonic_ns()
    _SHUTDOWN_STARTED_MONOTONIC_NS = shutdown_started_monotonic_ns
    _SHUTDOWN_STATE = "STOP_ACCEPTING_WRITES"
    with _WRITE_QUEUE_LOCK:
        _ACCEPTING_WRITES = False
    _SHUTDOWN_STATE = "DRAINING"
    _FLUSH_THREAD_STOP.set()

    deadline_seconds = 2.0 if deadline_seconds is None else float(deadline_seconds)
    deadline_ns = None if deadline_seconds is None else shutdown_started_monotonic_ns + max(0, int(deadline_seconds * 1_000_000_000))

    join_started_ns = time.monotonic_ns()
    join_duration_ns: int | None = None
    if thread is not None and thread.is_alive():
        try:
            remaining_ns = None if deadline_ns is None else max(0, deadline_ns - join_started_ns)
            timeout = None if remaining_ns is None else remaining_ns / 1_000_000_000
            thread.join(timeout=timeout)
        finally:
            join_duration_ns = time.monotonic_ns() - join_started_ns
    else:
        join_duration_ns = 0

    worker_alive_after_join = bool(thread is not None and thread.is_alive())
    deadline_expired = bool(deadline_ns is not None and time.monotonic_ns() >= deadline_ns and worker_alive_after_join)
    final_flush_attempted = False
    final_flush_completed = False
    status = "COMPLETE_DRAIN"
    if _AUDIT_COUNTERS["worker_failures"] > 0:
        status = "WORKER_FAILURE"
        _SHUTDOWN_STATE = status
    elif worker_alive_after_join and deadline_expired:
        status = "INCOMPLETE_DRAIN_TIMEOUT"
        _SHUTDOWN_STATE = status
    else:
        if not worker_alive_after_join and pending_tick_count() > 0:
            final_flush_attempted = True
            if _FLUSH_LOCK.acquire(blocking=False):
                try:
                    while _flush_pending_ticks(worker_owned=True) > 0:
                        pass
                    final_flush_completed = pending_tick_count() == 0
                finally:
                    _FLUSH_LOCK.release()
        queue_depth = pending_tick_count()
        in_flight_rows = max(0, _AUDIT_COUNTERS["rows_dequeued"] - _WRITE_FLUSH_COUNT)
        pending_writes = max(0, _WRITE_ENQUEUE_COUNT - _WRITE_FLUSH_COUNT)
        if (
            _AUDIT_COUNTERS["worker_failures"] > 0
            or queue_depth > 0
            or in_flight_rows > 0
            or pending_writes > 0
            or worker_alive_after_join
        ):
            status = "WORKER_FAILURE" if _AUDIT_COUNTERS["worker_failures"] > 0 else "INCOMPLETE_DRAIN_TIMEOUT"
            if status == "INCOMPLETE_DRAIN_TIMEOUT":
                deadline_expired = True
        _SHUTDOWN_STATE = status

    shutdown_finished_monotonic_ns = time.monotonic_ns()
    _SHUTDOWN_FINISHED_MONOTONIC_NS = shutdown_finished_monotonic_ns
    if thread is None:
        _FLUSH_THREAD_JOIN_COMPLETED = True
    else:
        _FLUSH_THREAD_JOIN_COMPLETED = not thread.is_alive()

    if status == "COMPLETE_DRAIN":
        _SHUTDOWN_STATE = "DRAIN_COMPLETE"
    result = _snapshot_shutdown_result(
        status=status,
        shutdown_state=_SHUTDOWN_STATE,
        deadline_seconds=deadline_seconds,
        deadline_expired=deadline_expired,
        shutdown_started_monotonic_ns=shutdown_started_monotonic_ns,
        shutdown_finished_monotonic_ns=shutdown_finished_monotonic_ns,
        drain_duration_ns=shutdown_finished_monotonic_ns - shutdown_started_monotonic_ns,
        join_duration_ns=join_duration_ns,
        final_flush_attempted=final_flush_attempted,
        final_flush_completed=final_flush_completed,
        thread=thread,
    )
    _SHUTDOWN_RESULT = result
    if status == "INCOMPLETE_DRAIN_TIMEOUT" and _INITIAL_SHUTDOWN_RESULT is None:
        _INITIAL_SHUTDOWN_RESULT = dict(result)
    if status == "COMPLETE_DRAIN" and _INITIAL_SHUTDOWN_RESULT is not None:
        _CLEANUP_SHUTDOWN_RESULT = dict(result)
    return dict(result)


def write_queue_depth() -> int:
    with _WRITE_QUEUE_LOCK:
        return len(_WRITE_QUEUE)


def write_enqueue_count() -> int:
    return _WRITE_ENQUEUE_COUNT


def write_flush_count() -> int:
    return _WRITE_FLUSH_COUNT


def get_persistence_worker_state() -> dict[str, Any]:
    return {
        "worker_started": _AUDIT_COUNTERS["worker_started"],
        "worker_start_count": _AUDIT_COUNTERS["worker_started"],
        "worker_thread_id": _FLUSH_THREAD_IDENT,
        "worker_thread_name": _FLUSH_THREAD_NAME,
        "worker_daemon": bool(_FLUSH_THREAD.daemon) if _FLUSH_THREAD is not None else None,
        "worker_terminated": _FLUSH_THREAD_TERMINATED,
        "worker_join_completed": _FLUSH_THREAD_JOIN_COMPLETED,
        "worker_failures": _AUDIT_COUNTERS["worker_failures"],
        "shutdown_state": _SHUTDOWN_STATE,
        "shutdown_started_monotonic_ns": _SHUTDOWN_STARTED_MONOTONIC_NS,
        "shutdown_finished_monotonic_ns": _SHUTDOWN_FINISHED_MONOTONIC_NS,
        "initial_shutdown_result": _INITIAL_SHUTDOWN_RESULT,
        "cleanup_shutdown_result": _CLEANUP_SHUTDOWN_RESULT,
        "writes_rejected_after_shutdown": _AUDIT_COUNTERS["writes_rejected_after_shutdown"],
        "last_accepted_enqueue_monotonic_ns": _LAST_ACCEPTED_ENQUEUE_MONOTONIC_NS,
        "rows_enqueued": _AUDIT_COUNTERS["rows_enqueued"],
        "rows_dequeued": _AUDIT_COUNTERS["rows_dequeued"],
        "committed_batches": _AUDIT_COUNTERS["committed_batches"],
        "committed_rows": _WRITE_FLUSH_COUNT,
        "queue_depth_initial": 0,
        "queue_depth_high_water": _QUEUE_HIGH_WATER,
        "queue_depth_at_shutdown": write_queue_depth(),
        "pending_writes_at_shutdown": max(0, _WRITE_ENQUEUE_COUNT - _WRITE_FLUSH_COUNT),
        "flush_count": _FLUSH_COUNT,
        "batch_size": _flush_batch_size(),
        "flush_interval": _flush_interval_sec(),
    }


def shutdown_persistence_worker(*, deadline_seconds: float | None = None) -> dict[str, Any]:
    return _shutdown_flush_thread(deadline_seconds=deadline_seconds)


aexit_registered = False
if not aexit_registered:
    atexit.register(_shutdown_flush_thread)
    aexit_registered = True


def insert_tick(ts=None, token=None, last_price=None, volume=None, oi=None, **kwargs):
    allowed_aliases = {"ts_epoch", "instrument_token"}
    unexpected = sorted(set(kwargs.keys()) - allowed_aliases)
    if unexpected:
        allowed = "ts, token, last_price, volume, oi, ts_epoch, instrument_token"
        label = "argument" if len(unexpected) == 1 else "arguments"
        raise TypeError(
            f"insert_tick() got unexpected keyword {label}: {', '.join(unexpected)}. "
            f"Allowed kwargs: {allowed}"
        )

    ts_alias = kwargs.pop("ts_epoch", None)
    token_alias = kwargs.pop("instrument_token", None)

    if ts_alias is not None:
        if ts is not None and ts != ts_alias:
            raise TypeError("insert_tick() received both ts and ts_epoch with different values")
        ts = ts_alias
    if token_alias is not None:
        if token is not None and token != token_alias:
            raise TypeError("insert_tick() received both token and instrument_token with different values")
        token = token_alias

    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    ts_epoch = _parse_ts_epoch(ts)
    if ts_epoch is None:
        ts_epoch = now_epoch
        ts_iso = now_iso
        fallback_reason = "missing_ts" if ts in (None, "", "None") else "invalid_ts"
        try:
            log_path = logs_dir() / "clock_skew.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": now_iso,
                            "event": "CLOCK_SKEW",
                            "stream": "ticks",
                            "skew_sec": None,
                            "instrument_token": token,
                            "reason": fallback_reason,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
    else:
        ts_iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    record_tick_epoch(ts_epoch)
    try:
        from core.market_data_monitor import record_tick

        record_tick(
            token=token,
            symbol=None,
            ts_epoch=ts_epoch,
            has_depth=False,
            is_index=False,
            now_epoch=now_epoch,
        )
    except Exception:
        pass
    try:
        if token is not None:
            _LAST_TICK_BY_TOKEN[int(token)] = {
                "ltp": float(last_price) if last_price is not None else None,
                "ts_epoch": ts_epoch,
            }
    except Exception:
        pass

    if not _db_writes_enabled():
        return True

    row = (ts_iso, token, last_price, volume, oi, ts_epoch, ts_iso)
    if _async_db_writes_enabled():
        # The reactor only enqueues. SQLite connections and flushes belong to the
        # single persistence worker; waiting for read-after-write here stalls Twisted.
        return _enqueue_row(row)

    return _write_rows([row])


def msgs_last_min() -> int:
    now = time.time()
    while _tick_window and now - _tick_window[0] > 60:
        _tick_window.popleft()
    return len(_tick_window)


def last_tick_epoch():
    return _LAST_TICK_EPOCH


def get_last_tick(
    token: int | str | None,
    allow_db: bool = True,
    *,
    decision_path: bool = False,
) -> dict | None:
    token_int = _normalize_token(token)
    if token_int is None:
        return None

    force_sqlite = bool(
        decision_path and bool(getattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", False))
    )
    if not force_sqlite:
        cached = _LAST_TICK_BY_TOKEN.get(token_int)
        if cached and cached.get("ts_epoch") is not None:
            return {"ltp": cached.get("ltp"), "ts_epoch": cached.get("ts_epoch"), "source": "memory"}
    if not allow_db:
        return None
    row = get_latest_tick_db(token_int)
    if not isinstance(row, dict):
        return None
    return {"ltp": row.get("ltp"), "ts_epoch": row.get("ts_epoch"), "source": "sqlite"}


def get_ltp(
    token: int | str | None,
    *,
    decision_path: bool = False,
    allow_db: bool | None = None,
) -> tuple[float | None, float | None]:
    """Return latest LTP while keeping decision-path reads non-blocking by default.

    Live/advisory decision paths must not fall through to SQLite when the in-memory
    WebSocket tick is missing. SQLite reads can flush pending writes, initialize the
    DB, and block behind locks; callers that explicitly need historical DB fallback
    can still pass allow_db=True.
    """

    if allow_db is None:
        allow_db = not bool(decision_path)
    tick = get_last_tick(token, allow_db=bool(allow_db), decision_path=decision_path)
    if not isinstance(tick, dict):
        return None, None
    return tick.get("ltp"), tick.get("ts_epoch")


def get_age_sec(
    token: int | str | None,
    now_epoch: float | None = None,
    *,
    decision_path: bool = False,
) -> float | None:
    now_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    _ltp, ts_epoch = get_ltp(token, decision_path=decision_path)
    if ts_epoch is None:
        return None
    return compute_age_sec(ts_epoch, now_epoch)
