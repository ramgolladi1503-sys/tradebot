import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Iterator
from datetime import datetime, timezone
from config import config as cfg
from pathlib import Path
from core.incidents import trigger_db_write_fail
from core.fs_utils import ensure_parent_dir

logger = logging.getLogger(__name__)

_DB_SCHEMA_INIT_LOCK = threading.Lock()
_DB_SCHEMA_INIT_PATH = None
_LAST_DEPTH_PRUNE_EPOCH = 0.0
_LAST_DEPTH_LOCK_WARN_EPOCH = 0.0


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    db_path = ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH)))
    timeout_sec = max(1.0, float(getattr(cfg, "TRADE_DB_TIMEOUT_SEC", 10.0) or 10.0))
    conn = sqlite3.connect(str(db_path), timeout=timeout_sec)
    try:
        busy_timeout_ms = max(1000, int(getattr(cfg, "TRADE_DB_BUSY_TIMEOUT_MS", 10000) or 10000))
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    except Exception:
        pass
    try:
        if bool(getattr(cfg, "TRADE_DB_ENABLE_WAL", True)):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA synchronous={str(getattr(cfg, 'TRADE_DB_SYNCHRONOUS', 'NORMAL') or 'NORMAL')}")
    except Exception:
        pass
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def classify_outcome_label(realized_pnl: float, epsilon: float = 1e-6) -> str:
    pnl = float(realized_pnl or 0.0)
    if pnl > epsilon:
        return "WIN"
    if pnl < -epsilon:
        return "LOSS"
    return "BREAKEVEN"


def classify_outcome_grade(r_multiple_realized: float) -> str:
    r_val = float(r_multiple_realized or 0.0)
    if r_val >= 1.5:
        return "A"
    if r_val >= 1.0:
        return "B"
    if r_val >= 0.0:
        return "C"
    return "D"


def init_db(force: bool = False):
    global _DB_SCHEMA_INIT_PATH
    target_db_path = str(ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH))))
    with _DB_SCHEMA_INIT_LOCK:
        if (not force) and _DB_SCHEMA_INIT_PATH == target_db_path:
            return
        with _conn() as conn:
            conn.execute(
            """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            underlying TEXT,
            instrument TEXT,
            instrument_type TEXT,
            instrument_token INTEGER,
            strike INTEGER,
            expiry TEXT,
            option_type TEXT,
            right TEXT,
            instrument_id TEXT,
            side TEXT,
            entry REAL,
            stop_loss REAL,
            target REAL,
            qty INTEGER,
            qty_lots INTEGER,
            qty_units INTEGER,
            validity_sec INTEGER,
            tradable INTEGER,
            tradable_reasons_blocking TEXT,
            source_flags_json TEXT,
            confidence REAL,
            strategy TEXT,
            regime TEXT,
            fill_price REAL,
            latency_ms REAL,
            slippage REAL,
            micro_pred REAL,
            execution_quality REAL,
            exit_price REAL,
            exit_time TEXT,
            exit_reason TEXT,
            realized_pnl REAL,
            r_multiple_realized REAL,
            outcome_label TEXT,
            outcome_grade TEXT,
            legs_count INTEGER,
            avg_exit REAL,
            exit_reason_final TEXT,
            trailing_enabled INTEGER,
            trailing_method TEXT,
            trailing_atr_mult REAL,
            trail_stop_init REAL,
            trail_stop_last REAL,
            trail_updates INTEGER,
            timestamp_epoch REAL,
            timestamp_iso TEXT
        )
        """
        )
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN execution_quality REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN strike INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN expiry TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN option_type TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN instrument_id TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN underlying TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN instrument_type TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN right TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN qty_lots INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN qty_units INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN validity_sec INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN tradable INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN tradable_reasons_blocking TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN source_flags_json TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN timestamp_epoch REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN timestamp_iso TEXT")
            except Exception:
                pass
            for col, sql_type in [
                ("exit_price", "REAL"),
                ("exit_time", "TEXT"),
                ("exit_reason", "TEXT"),
                ("realized_pnl", "REAL"),
                ("r_multiple_realized", "REAL"),
                ("outcome_label", "TEXT"),
                ("outcome_grade", "TEXT"),
                ("legs_count", "INTEGER"),
                ("avg_exit", "REAL"),
                ("exit_reason_final", "TEXT"),
                ("trailing_enabled", "INTEGER"),
                ("trailing_method", "TEXT"),
                ("trailing_atr_mult", "REAL"),
                ("trail_stop_init", "REAL"),
                ("trail_stop_last", "REAL"),
                ("trail_updates", "INTEGER"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {sql_type}")
                except Exception:
                    pass
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS outcomes (
                trade_id TEXT,
                exit_price REAL,
                exit_time TEXT,
                actual INTEGER,
                r_multiple REAL,
                r_label INTEGER,
                exit_reason TEXT,
                realized_pnl REAL,
                r_multiple_realized REAL,
                outcome_label TEXT,
                outcome_grade TEXT,
                timestamp_epoch REAL,
                timestamp_iso TEXT
            )
            """
            )
            try:
                conn.execute("ALTER TABLE outcomes ADD COLUMN timestamp_epoch REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE outcomes ADD COLUMN timestamp_iso TEXT")
            except Exception:
                pass
            for col, sql_type in [
                ("exit_reason", "TEXT"),
                ("realized_pnl", "REAL"),
                ("r_multiple_realized", "REAL"),
                ("outcome_label", "TEXT"),
                ("outcome_grade", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE outcomes ADD COLUMN {col} {sql_type}")
                except Exception:
                    pass
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS execution_stats (
                timestamp TEXT,
                instrument TEXT,
                slippage_bps REAL,
                latency_ms REAL,
                fill_ratio REAL,
                timestamp_epoch REAL,
                timestamp_iso TEXT
            )
            """
            )
            try:
                conn.execute("ALTER TABLE execution_stats ADD COLUMN timestamp_epoch REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE execution_stats ADD COLUMN timestamp_iso TEXT")
            except Exception:
                pass
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS depth_snapshots (
                timestamp TEXT,
                instrument_token INTEGER,
                depth_json TEXT,
                timestamp_iso TEXT,
                timestamp_epoch REAL
            )
            """
            )
            try:
                conn.execute("ALTER TABLE depth_snapshots ADD COLUMN timestamp_iso TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE depth_snapshots ADD COLUMN timestamp_epoch REAL")
            except Exception:
                pass
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS broker_fills (
                order_id TEXT,
                trade_id TEXT,
                symbol TEXT,
                underlying TEXT,
                side TEXT,
                qty INTEGER,
                qty_lots INTEGER,
                qty_units INTEGER,
                price REAL,
                timestamp TEXT,
                exchange TEXT,
                instrument_token INTEGER,
                instrument_type TEXT,
                expiry TEXT,
                strike INTEGER,
                right TEXT,
                instrument_id TEXT,
                timestamp_epoch REAL,
                timestamp_iso TEXT
            )
            """
            )
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN timestamp_epoch REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN timestamp_iso TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN underlying TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN qty_lots INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN qty_units INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN instrument_type TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN expiry TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN strike INTEGER")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN right TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE broker_fills ADD COLUMN instrument_id TEXT")
            except Exception:
                pass
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS trail_events (
                trace_id TEXT,
                timestamp_epoch REAL,
                timestamp_iso TEXT,
                trail_stop REAL,
                ltp REAL,
                reason TEXT
            )
            """
            )
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS trade_legs (
                trace_id TEXT,
                leg_id INTEGER,
                qty_units INTEGER,
                price REAL,
                timestamp_epoch REAL,
                timestamp_iso TEXT,
                reason TEXT
            )
            """
            )
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                trades INTEGER,
                pnl REAL,
                win_rate REAL,
                profit_factor REAL,
                sharpe REAL,
                max_drawdown REAL
            )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_depth_snapshots_ts_epoch ON depth_snapshots(timestamp_epoch)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_depth_snapshots_token_ts ON depth_snapshots(instrument_token, timestamp_epoch)"
            )
        _DB_SCHEMA_INIT_PATH = target_db_path


def insert_trade(entry):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    tradable_reasons_val = entry.get("tradable_reasons_blocking")
    if tradable_reasons_val is not None and not isinstance(tradable_reasons_val, str):
        tradable_reasons_val = json.dumps(tradable_reasons_val)
    source_flags_val = entry.get("source_flags_json")
    if source_flags_val is None and entry.get("source_flags") is not None:
        source_flags_val = entry.get("source_flags")
    if source_flags_val is not None and not isinstance(source_flags_val, str):
        source_flags_val = json.dumps(source_flags_val)
    instrument_type = entry.get("instrument_type") or entry.get("instrument")
    right = entry.get("right") or entry.get("option_type")
    from core.trade_schema import validate_trade_identity
    ok, reason = validate_trade_identity(
        entry.get("underlying") or entry.get("symbol"),
        instrument_type,
        entry.get("expiry"),
        entry.get("strike"),
        right,
    )
    if instrument_type in ("OPT", "FUT") and not ok:
        raise ValueError(f"invalid_trade_identity:{reason}")
    if instrument_type in ("OPT", "FUT") and not entry.get("instrument_id"):
        raise ValueError("invalid_trade_identity:missing_instrument_id")
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT OR REPLACE INTO trades
            (trade_id, timestamp, symbol, underlying, instrument, instrument_type, instrument_token, strike, expiry, option_type, right, instrument_id, side, entry, stop_loss, target, qty, qty_lots, qty_units, validity_sec, tradable, tradable_reasons_blocking, source_flags_json,
             confidence, strategy, regime, fill_price, latency_ms, slippage, micro_pred, execution_quality,
             exit_price, exit_time, exit_reason, realized_pnl, r_multiple_realized, outcome_label, outcome_grade, legs_count, avg_exit, exit_reason_final,
             trailing_enabled, trailing_method, trailing_atr_mult, trail_stop_init, trail_stop_last, trail_updates,
             timestamp_epoch, timestamp_iso)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    entry.get("trade_id"),
                    entry.get("timestamp") or now_iso,
                    entry.get("symbol"),
                    entry.get("underlying") or entry.get("symbol"),
                    entry.get("instrument"),
                    instrument_type,
                    entry.get("instrument_token"),
                    entry.get("strike"),
                    entry.get("expiry"),
                    entry.get("option_type"),
                    right,
                    entry.get("instrument_id"),
                    entry.get("side"),
                    entry.get("entry"),
                    entry.get("stop_loss"),
                    entry.get("target"),
                    entry.get("qty"),
                    entry.get("qty_lots"),
                    entry.get("qty_units"),
                    entry.get("validity_sec"),
                    int(bool(entry.get("tradable"))) if entry.get("tradable") is not None else None,
                    tradable_reasons_val,
                    source_flags_val,
                    entry.get("confidence"),
                    entry.get("strategy"),
                    entry.get("regime"),
                    entry.get("fill_price"),
                    entry.get("latency_ms"),
                    entry.get("slippage"),
                    entry.get("micro_pred"),
                    entry.get("execution_quality_score") or entry.get("execution_quality"),
                    entry.get("exit_price"),
                    entry.get("exit_time"),
                    entry.get("exit_reason"),
                    entry.get("realized_pnl"),
                    entry.get("r_multiple_realized"),
                    entry.get("outcome_label"),
                    entry.get("outcome_grade"),
                    entry.get("legs_count"),
                    entry.get("avg_exit"),
                    entry.get("exit_reason_final"),
                    int(bool(entry.get("trailing_enabled"))) if entry.get("trailing_enabled") is not None else None,
                    entry.get("trailing_method"),
                    entry.get("trailing_atr_mult"),
                    entry.get("trail_stop_init"),
                    entry.get("trail_stop_last"),
                    entry.get("trail_updates"),
                    entry.get("timestamp_epoch") or now_epoch,
                    entry.get("timestamp_iso") or now_iso,
                ),
            )
        try:
            from core.storage import emit_trade_accepted_event

            emit_trade_accepted_event(entry)
        except Exception:
            pass
    except Exception as exc:
        trigger_db_write_fail({"table": "trades", "error": str(exc)})
        raise


def _lookup_trade_for_outcome(trade_id: str | None) -> dict:
    if not trade_id:
        return {}
    try:
        with _conn() as conn:
            row = conn.execute(
                """
                SELECT symbol, underlying, instrument_token, instrument_id, option_type, right, strike, expiry
                FROM trades
                WHERE trade_id=?
                ORDER BY timestamp_epoch DESC
                LIMIT 1
                """,
                (trade_id,),
            ).fetchone()
    except Exception:
        return {}
    if not row:
        return {}
    return {
        "symbol": row[0] or row[1],
        "underlying": row[1],
        "instrument_token": row[2],
        "instrument_id": row[3],
        "option_type": row[4] or row[5],
        "strike": row[6],
        "expiry": row[7],
    }


def insert_outcome(outcome):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT INTO outcomes (
                trade_id, exit_price, exit_time, actual, r_multiple, r_label,
                exit_reason, realized_pnl, r_multiple_realized, outcome_label, outcome_grade,
                timestamp_epoch, timestamp_iso
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    outcome.get("trade_id"),
                    outcome.get("exit_price"),
                    outcome.get("exit_time") or now_iso,
                    outcome.get("actual"),
                    outcome.get("r_multiple"),
                    outcome.get("r_label"),
                    outcome.get("exit_reason"),
                    outcome.get("realized_pnl"),
                    outcome.get("r_multiple_realized"),
                    outcome.get("outcome_label"),
                    outcome.get("outcome_grade"),
                    outcome.get("timestamp_epoch") or now_epoch,
                    outcome.get("timestamp_iso") or now_iso,
                ),
            )
        try:
            from core.storage import emit_trade_exited_event

            enriched = dict(_lookup_trade_for_outcome(outcome.get("trade_id")))
            enriched.update(dict(outcome or {}))
            emit_trade_exited_event(enriched)
        except Exception:
            pass
    except Exception as exc:
        trigger_db_write_fail({"table": "outcomes", "error": str(exc)})
        raise


def fetch_recent_trades(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def fetch_recent_outcomes(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM outcomes ORDER BY exit_time DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def fetch_pnl_series(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT exit_time, exit_price, actual FROM outcomes ORDER BY exit_time DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def fetch_execution_stats(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM execution_stats ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def insert_execution_stat(row):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT INTO execution_stats (timestamp, instrument, slippage_bps, latency_ms, fill_ratio, timestamp_epoch, timestamp_iso)
            VALUES (?,?,?,?,?,?,?)
            """,
                (
                    row.get("timestamp") or now_iso,
                    row.get("instrument"),
                    row.get("slippage_bps"),
                    row.get("latency_ms"),
                    row.get("fill_ratio"),
                    row.get("timestamp_epoch") or now_epoch,
                    row.get("timestamp_iso") or now_iso,
                ),
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "execution_stats", "error": str(exc)})
        raise


def fetch_depth_snapshots(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def fetch_depth_imbalance(limit=1000):
    init_db()
    with _conn() as conn:
        cur = conn.execute(
            "SELECT timestamp, instrument_token, depth_json, timestamp_epoch FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def _is_database_locked_error(exc: Exception) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc or "").strip().lower()
    return "database is locked" in message or "database table is locked" in message


def _should_prune_depth_snapshots(now_epoch: float) -> bool:
    global _LAST_DEPTH_PRUNE_EPOCH
    interval_sec = max(
        0.0,
        float(getattr(cfg, "DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC", 10.0) or 10.0),
    )
    if interval_sec <= 0.0:
        _LAST_DEPTH_PRUNE_EPOCH = now_epoch
        return True
    if (now_epoch - float(_LAST_DEPTH_PRUNE_EPOCH or 0.0)) >= interval_sec:
        _LAST_DEPTH_PRUNE_EPOCH = now_epoch
        return True
    return False


def _warn_depth_db_lock_once(err: Exception) -> None:
    global _LAST_DEPTH_LOCK_WARN_EPOCH
    now_epoch = time.time()
    warn_every_sec = max(
        1.0,
        float(getattr(cfg, "DEPTH_SNAPSHOT_DB_LOCK_MAX_WARN_EVERY_SEC", 30.0) or 30.0),
    )
    if (now_epoch - float(_LAST_DEPTH_LOCK_WARN_EPOCH or 0.0)) < warn_every_sec:
        return
    _LAST_DEPTH_LOCK_WARN_EPOCH = now_epoch
    logger.warning(
        "depth_snapshot_db_lock_skip retry_exhausted=true err=%s",
        f"{type(err).__name__}:{err}",
    )


def insert_depth_snapshot(ts_iso, instrument_token, depth_json, ts_epoch=None):
    init_db()
    # Ensure timestamp fields are always present and normalized
    if ts_epoch is None:
        try:
            ts_epoch = float(ts_iso)
        except Exception:
            ts_epoch = None
    if ts_epoch is None:
        ts_epoch = time.time()
    if not ts_iso:
        try:
            from datetime import datetime, timezone
            ts_iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            ts_iso = None
    retry_attempts = max(
        1,
        int(getattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS", 3) or 3),
    )
    retry_backoff_sec = max(
        0.0,
        float(getattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_BACKOFF_SEC", 0.05) or 0.05),
    )
    skip_on_lock = bool(getattr(cfg, "DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE", True))
    should_prune = _should_prune_depth_snapshots(float(ts_epoch or time.time()))
    for attempt in range(1, retry_attempts + 1):
        try:
            with _conn() as conn:
                conn.execute(
                    """
                INSERT INTO depth_snapshots (timestamp, instrument_token, depth_json, timestamp_iso, timestamp_epoch)
                VALUES (?,?,?,?,?)
                """,
                    (ts_iso, instrument_token, depth_json, ts_iso, ts_epoch),
                )
                if should_prune:
                    limit = int(getattr(cfg, "DEPTH_SNAPSHOT_LIMIT", 10000) or 10000)
                    conn.execute(
                        """
                    DELETE FROM depth_snapshots
                    WHERE rowid NOT IN (
                        SELECT rowid FROM depth_snapshots ORDER BY timestamp_epoch DESC LIMIT ?
                    )
                    """,
                        (limit,),
                    )
            return True
        except Exception as exc:
            if _is_database_locked_error(exc) and attempt < retry_attempts:
                sleep_sec = retry_backoff_sec * (2 ** (attempt - 1))
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                continue
            if _is_database_locked_error(exc) and skip_on_lock:
                _warn_depth_db_lock_once(exc)
                return False
            trigger_db_write_fail({"table": "depth_snapshots", "error": str(exc)})
            raise
    return False


def insert_depth_snapshots(rows):
    """Persist an ordered depth batch in one transaction.

    The caller owns failure accounting.  Returning the number of durable rows
    keeps the persistence worker from treating a lock-skip as a successful
    write, which would otherwise hide data loss.
    """
    rows = list(rows)
    if not rows:
        return 0
    init_db()
    now_epoch = max(float(row[3] or time.time()) for row in rows)
    should_prune = _should_prune_depth_snapshots(now_epoch)
    retry_attempts = max(1, int(getattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS", 3) or 3))
    retry_backoff_sec = max(0.0, float(getattr(cfg, "DEPTH_SNAPSHOT_DB_WRITE_RETRY_BACKOFF_SEC", 0.05) or 0.05))
    for attempt in range(1, retry_attempts + 1):
        try:
            with _conn() as conn:
                conn.executemany(
                    """
                    INSERT INTO depth_snapshots
                    (timestamp, instrument_token, depth_json, timestamp_iso, timestamp_epoch)
                    VALUES (?,?,?,?,?)
                    """,
                    [(row[0], row[1], row[2], row[0], row[3]) for row in rows],
                )
                if should_prune:
                    limit = int(getattr(cfg, "DEPTH_SNAPSHOT_LIMIT", 10000) or 10000)
                    conn.execute(
                        """
                        DELETE FROM depth_snapshots
                        WHERE rowid NOT IN (
                            SELECT rowid FROM depth_snapshots ORDER BY timestamp_epoch DESC LIMIT ?
                        )
                        """,
                        (limit,),
                    )
            return len(rows)
        except Exception as exc:
            if _is_database_locked_error(exc) and attempt < retry_attempts:
                time.sleep(retry_backoff_sec * (2 ** (attempt - 1)))
                continue
            if _is_database_locked_error(exc) and bool(getattr(cfg, "DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE", True)):
                _warn_depth_db_lock_once(exc)
                return 0
            trigger_db_write_fail({"table": "depth_snapshots", "error": str(exc)})
            raise
    return 0


def insert_broker_fill(row):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT INTO broker_fills
            (order_id, trade_id, symbol, underlying, side, qty, qty_lots, qty_units, price, timestamp, exchange, instrument_token, instrument_type, expiry, strike, right, instrument_id, timestamp_epoch, timestamp_iso)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    row.get("order_id"),
                    row.get("trade_id"),
                    row.get("symbol"),
                    row.get("underlying") or row.get("symbol"),
                    row.get("side"),
                    row.get("qty"),
                    row.get("qty_lots"),
                    row.get("qty_units"),
                    row.get("price"),
                    row.get("timestamp") or now_iso,
                    row.get("exchange"),
                    row.get("instrument_token"),
                    row.get("instrument_type") or row.get("instrument"),
                    row.get("expiry"),
                    row.get("strike"),
                    row.get("right") or row.get("option_type"),
                    row.get("instrument_id"),
                    row.get("timestamp_epoch") or now_epoch,
                    row.get("timestamp_iso") or now_iso,
                ),
            )
        try:
            from core.reconciliation import emit_execution_fill_event

            qty_value = row.get("qty_units")
            if qty_value is None:
                qty_value = row.get("qty")
            emit_execution_fill_event(
                order_id=row.get("order_id"),
                broker_order_id=row.get("broker_order_id"),
                trade_id=row.get("trade_id"),
                symbol=row.get("symbol"),
                side=row.get("side"),
                qty=qty_value,
                price=row.get("price"),
                ts_utc=row.get("timestamp_iso") or row.get("timestamp") or now_iso,
                run_id=row.get("run_id"),
                desk_id=row.get("desk_id") or getattr(cfg, "DESK_ID", "DEFAULT"),
                mode=row.get("mode") or getattr(cfg, "EXECUTION_MODE", "PAPER"),
            )
        except Exception as exc:
            # Reconciliation telemetry must never block broker fill persistence.
            logger.warning("execution_fill_event_warn err=%s", exc)
    except Exception as exc:
        trigger_db_write_fail({"table": "broker_fills", "error": str(exc)})
        raise


def update_trade_fill_db(trade_id, fill_price=None, latency_ms=None, slippage=None):
    init_db()
    fields = []
    values = []
    if fill_price is not None:
        fields.append("fill_price=?")
        values.append(fill_price)
    if latency_ms is not None:
        fields.append("latency_ms=?")
        values.append(latency_ms)
    if slippage is not None:
        fields.append("slippage=?")
        values.append(slippage)
    if not fields:
        return
    values.append(trade_id)
    try:
        with _conn() as conn:
            conn.execute(
                f"UPDATE trades SET {', '.join(fields)} WHERE trade_id=?",
                values,
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "trades", "error": str(exc)})
        raise


def update_trade_close(
    trade_id: str,
    *,
    exit_price: float,
    exit_time: str,
    exit_reason: str,
    realized_pnl: float,
    r_multiple_realized: float,
    outcome_label: str,
    outcome_grade: str,
    legs_count: int | None = None,
    avg_exit: float | None = None,
    exit_reason_final: str | None = None,
):
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """
            UPDATE trades
            SET exit_price=?,
                exit_time=?,
                exit_reason=?,
                realized_pnl=?,
                r_multiple_realized=?,
                outcome_label=?,
                outcome_grade=?,
                legs_count=COALESCE(?, legs_count),
                avg_exit=COALESCE(?, avg_exit),
                exit_reason_final=COALESCE(?, exit_reason_final)
            WHERE trade_id=?
            """,
                (
                    exit_price,
                    exit_time,
                    exit_reason,
                    realized_pnl,
                    r_multiple_realized,
                    outcome_label,
                    outcome_grade,
                    legs_count,
                    avg_exit,
                    exit_reason_final,
                    trade_id,
                ),
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "trades", "error": str(exc)})
        raise


def update_trailing_state(
    trade_id: str,
    *,
    trailing_enabled: bool,
    trailing_method: str,
    trailing_atr_mult: float | None,
    trail_stop_init: float | None,
    trail_stop_last: float | None,
    trail_updates: int,
):
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """
            UPDATE trades
            SET trailing_enabled=?,
                trailing_method=?,
                trailing_atr_mult=?,
                trail_stop_init=COALESCE(?, trail_stop_init),
                trail_stop_last=?,
                trail_updates=?
            WHERE trade_id=?
            """,
                (
                    int(bool(trailing_enabled)),
                    trailing_method,
                    trailing_atr_mult,
                    trail_stop_init,
                    trail_stop_last,
                    trail_updates,
                    trade_id,
                ),
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "trades", "error": str(exc)})
        raise


def insert_trail_event(trace_id: str, trail_stop: float, ltp: float, reason: str):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT INTO trail_events (trace_id, timestamp_epoch, timestamp_iso, trail_stop, ltp, reason)
            VALUES (?,?,?,?,?,?)
            """,
                (trace_id, now_epoch, now_iso, trail_stop, ltp, reason),
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "trail_events", "error": str(exc)})
        raise


def insert_trade_leg(trace_id: str, leg_id: int, qty_units: int, price: float, reason: str):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT INTO trade_legs (trace_id, leg_id, qty_units, price, timestamp_epoch, timestamp_iso, reason)
            VALUES (?,?,?,?,?,?,?)
            """,
                (trace_id, leg_id, qty_units, price, now_epoch, now_iso, reason),
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "trade_legs", "error": str(exc)})
        raise


def insert_daily_stats(row):
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """
            INSERT OR REPLACE INTO daily_stats
            (date, trades, pnl, win_rate, profit_factor, sharpe, max_drawdown)
            VALUES (?,?,?,?,?,?,?)
            """,
                (
                    row.get("date"),
                    row.get("trades"),
                    row.get("pnl"),
                    row.get("win_rate"),
                    row.get("profit_factor"),
                    row.get("sharpe"),
                    row.get("max_drawdown"),
                ),
            )
    except Exception as exc:
        trigger_db_write_fail({"table": "daily_stats", "error": str(exc)})
        raise


def fetch_open_positions(limit=2000):
    init_db()
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT *
            FROM trades
            WHERE COALESCE(exit_time, '') = ''
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows


def fetch_open_positions_dict(limit=2000):
    cols, rows = fetch_open_positions(limit=limit)
    out = []
    for row in rows:
        out.append(dict(zip(cols, row)))
    return out
