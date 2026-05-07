from __future__ import annotations
from core.paths import logs_dir

import json
import logging
import sqlite3
import time
import hashlib
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core import tick_store

logger = logging.getLogger(__name__)

_REJECT_TELEMETRY_LOCK = Lock()
_REJECT_TELEMETRY_ROWS: list[dict[str, Any]] = []
_REJECT_SHADOW_LOCK = Lock()
_REJECT_SHADOW_LAST_EVAL_TS = 0.0


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"none", "nan", "null"}:
                return None
            return float(text)
        return float(value)
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"none", "nan", "null"}:
                return None
            return int(float(text))
        return int(float(value))
    except Exception:
        return None


def _as_epoch_ms(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            val = float(value)
            if val <= 0:
                return None
            if val >= 10_000_000_000:
                return int(val)
            return int(val * 1000.0)
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000.0)
    except Exception:
        return None


def _in_memory_limit() -> int:
    try:
        return max(50, int(getattr(cfg, "REJECT_TELEMETRY_MAX_IN_MEMORY", 500)))
    except Exception:
        return 500


def _shadow_enabled() -> bool:
    try:
        return bool(getattr(cfg, "REJECT_SHADOW_ENABLE", True))
    except Exception:
        return True


def _shadow_table_name() -> str:
    try:
        raw = str(getattr(cfg, "REJECT_SHADOW_TABLE", "reject_shadow") or "").strip()
    except Exception:
        raw = "reject_shadow"
    return raw or "reject_shadow"


def _shadow_horizon_minutes() -> int:
    try:
        return max(1, int(getattr(cfg, "REJECT_SHADOW_HORIZON_MIN", 30)))
    except Exception:
        return 30


def _shadow_eval_interval_sec() -> float:
    try:
        return max(1.0, float(getattr(cfg, "REJECT_SHADOW_EVAL_INTERVAL_SEC", 30.0)))
    except Exception:
        return 30.0


def _shadow_eval_batch_size() -> int:
    try:
        return max(1, int(getattr(cfg, "REJECT_SHADOW_EVAL_BATCH_SIZE", 200)))
    except Exception:
        return 200


def _shadow_db_path() -> Path:
    raw = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
    if raw:
        return ensure_parent_dir(Path(raw))
    return ensure_parent_dir(logs_dir() / "reject_shadow.sqlite")


def _shadow_jsonl_path() -> Path:
    try:
        configured = str(getattr(cfg, "REJECT_SHADOW_JSONL_PATH", "") or "").strip()
    except Exception:
        configured = ""
    if configured:
        return ensure_parent_dir(Path(configured))
    return ensure_parent_dir(logs_dir() / "reject_shadow.jsonl")


def _reject_telemetry_log_dir() -> Path:
    configured = str(getattr(cfg, "REJECT_TELEMETRY_LOG_DIR", "") or "").strip()
    if configured:
        return Path(configured)
    desk_log_dir = str(getattr(cfg, "DESK_LOG_DIR", "") or "").strip()
    if desk_log_dir:
        return Path(desk_log_dir) / "reject_telemetry"
    return logs_dir() / "reject_telemetry"


def _daily_path(ts_epoch_ms: int) -> Path:
    day = datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    return _reject_telemetry_log_dir() / f"rejects_{day}.jsonl"


def _normalize_reject_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    ts_epoch_ms = _as_epoch_ms(payload.get("timestamp_epoch_ms"))
    if ts_epoch_ms is None:
        ts_epoch_ms = int(time.time() * 1000.0)
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        symbol = "UNKNOWN"
    reject_reason = str(payload.get("reject_reason") or "").strip()
    if not reject_reason:
        reject_reason = "unknown_reject"
    gate_name = str(payload.get("gate_name") or "").strip() or reject_reason
    reason_text = str(payload.get("reason") or payload.get("reason_text") or "").strip() or reject_reason
    trade_side = str(payload.get("trade_side") or payload.get("direction") or "").strip().upper() or None
    feed_state = str(payload.get("feed_state") or "").strip().upper() or None
    strike = _as_float(payload.get("strike"))
    trade_side = str(payload.get("trade_side") or payload.get("direction") or "").strip().upper() or None
    rejection_reasons = payload.get("rejection_reasons")
    if isinstance(rejection_reasons, (list, tuple)):
        reasons = [str(x).strip() for x in rejection_reasons if str(x).strip()]
    else:
        reasons = []
    if not reasons:
        reasons = [reject_reason]
    candidate_key = str(
        payload.get("candidate_key")
        or payload.get("candidate_id")
        or payload.get("trade_key")
        or ""
    ).strip()
    if not candidate_key:
        digest_src = "|".join(
            [
                symbol,
                str(ts_epoch_ms),
                str(strike if strike is not None else ""),
                str(trade_side or ""),
                reject_reason,
            ]
        )
        candidate_key = f"rej_{hashlib.sha256(digest_src.encode('utf-8')).hexdigest()[:18]}"
    horizon_minutes = _as_int(payload.get("horizon_minutes")) or _shadow_horizon_minutes()
    entry_price = (
        _as_float(payload.get("entry_price"))
        or _as_float(payload.get("entry"))
        or _as_float(payload.get("current_ltp"))
    )
    instrument_token = _as_int(payload.get("instrument_token"))
    quote_source = str(payload.get("quote_source") or "").strip() or None
    option_ltp_source = str(payload.get("option_ltp_source") or "").strip() or None
    return {
        "candidate_key": candidate_key,
        "snapshot_id": str(payload.get("snapshot_id") or "").strip() or None,
        "timestamp_epoch_ms": int(ts_epoch_ms),
        "ts_utc": datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).isoformat(),
        "reject_ts_epoch": float(ts_epoch_ms) / 1000.0,
        "symbol": symbol,
        "strike": strike,
        "trade_side": trade_side,
        "gate_name": gate_name,
        "reject_reason": reject_reason,
        "reason": reason_text,
        "rejection_reasons": reasons,
        "quote_age_sec": _as_float(payload.get("quote_age_sec")),
        "spread_pct": _as_float(payload.get("spread_pct")),
        "feed_state": feed_state,
        "entry_price": entry_price,
        "instrument_token": instrument_token,
        "quote_source": quote_source,
        "option_ltp_source": option_ltp_source,
        "horizon_minutes": int(horizon_minutes),
    }


def _append_memory(row: dict[str, Any]) -> None:
    with _REJECT_TELEMETRY_LOCK:
        _REJECT_TELEMETRY_ROWS.append(dict(row))
        limit = _in_memory_limit()
        if len(_REJECT_TELEMETRY_ROWS) > limit:
            del _REJECT_TELEMETRY_ROWS[:-limit]


def _ensure_reject_shadow_table(conn: sqlite3.Connection) -> str:
    table = _shadow_table_name()
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            candidate_key TEXT PRIMARY KEY,
            snapshot_id TEXT,
            symbol TEXT NOT NULL,
            instrument_token INTEGER,
            trade_side TEXT,
            entry_price REAL,
            reject_ts_epoch REAL NOT NULL,
            reject_reason TEXT NOT NULL,
            rejection_reasons_json TEXT NOT NULL,
            horizon_minutes INTEGER NOT NULL,
            eval_due_ts_epoch REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            evaluated_ts_epoch REAL,
            end_price REAL,
            hypothetical_pnl REAL,
            source TEXT NOT NULL DEFAULT 'ticks_db',
            evidence_json TEXT
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_status_due ON {table}(status, eval_due_ts_epoch)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_symbol_rejectts ON {table}(symbol, reject_ts_epoch)"
    )
    return table


def _append_shadow_jsonl(payload: Mapping[str, Any]) -> None:
    try:
        path = _shadow_jsonl_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True) + "\n")
    except Exception:
        logger.warning("reject_shadow_jsonl_write_failed")


def _seed_reject_shadow(row: Mapping[str, Any]) -> None:
    if not _shadow_enabled():
        return
    candidate_key = str(row.get("candidate_key") or "").strip()
    if not candidate_key:
        return
    reject_ts_epoch = _as_float(row.get("reject_ts_epoch"))
    if reject_ts_epoch is None:
        return
    horizon_minutes = _as_int(row.get("horizon_minutes")) or _shadow_horizon_minutes()
    eval_due = float(reject_ts_epoch) + (float(horizon_minutes) * 60.0)
    reasons = row.get("rejection_reasons")
    if isinstance(reasons, (list, tuple)):
        reason_list = [str(x).strip() for x in reasons if str(x).strip()]
    else:
        reason_list = [str(row.get("reject_reason") or "unknown_reject")]
    db_path = _shadow_db_path()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            table = _ensure_reject_shadow_table(conn)
            conn.execute(
                f"""
                INSERT INTO {table} (
                    candidate_key, snapshot_id, symbol, instrument_token, trade_side,
                    entry_price, reject_ts_epoch, reject_reason, rejection_reasons_json,
                    horizon_minutes, eval_due_ts_epoch, status, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 'ticks_db')
                ON CONFLICT(candidate_key) DO UPDATE SET
                    snapshot_id=excluded.snapshot_id,
                    symbol=excluded.symbol,
                    instrument_token=excluded.instrument_token,
                    trade_side=excluded.trade_side,
                    entry_price=excluded.entry_price,
                    reject_ts_epoch=excluded.reject_ts_epoch,
                    reject_reason=excluded.reject_reason,
                    rejection_reasons_json=excluded.rejection_reasons_json,
                    horizon_minutes=excluded.horizon_minutes,
                    eval_due_ts_epoch=excluded.eval_due_ts_epoch,
                    status='PENDING',
                    evaluated_ts_epoch=NULL,
                    end_price=NULL,
                    hypothetical_pnl=NULL,
                    evidence_json=NULL
                """,
                (
                    candidate_key,
                    row.get("snapshot_id"),
                    row.get("symbol"),
                    _as_int(row.get("instrument_token")),
                    row.get("trade_side"),
                    _as_float(row.get("entry_price")),
                    float(reject_ts_epoch),
                    str(row.get("reject_reason") or "unknown_reject"),
                    json.dumps(reason_list, ensure_ascii=True),
                    int(horizon_minutes),
                    float(eval_due),
                ),
            )
        _append_shadow_jsonl(
            {
                "event": "seed",
                "ts_epoch": float(time.time()),
                "candidate_key": candidate_key,
                "snapshot_id": row.get("snapshot_id"),
                "symbol": row.get("symbol"),
                "instrument_token": _as_int(row.get("instrument_token")),
                "reject_reason": row.get("reject_reason"),
                "horizon_minutes": int(horizon_minutes),
                "eval_due_ts_epoch": float(eval_due),
            }
        )
    except Exception as exc:
        logger.warning("reject_shadow_seed_failed err=%s", f"{type(exc).__name__}:{exc}")


def evaluate_reject_shadow_once(
    *,
    now_epoch: float | None = None,
    force: bool = False,
    batch_size: int | None = None,
) -> dict[str, Any]:
    if not _shadow_enabled():
        return {"status": "disabled", "processed": 0}
    global _REJECT_SHADOW_LAST_EVAL_TS
    now_val = float(now_epoch if now_epoch is not None else time.time())
    if not force:
        interval = _shadow_eval_interval_sec()
        if (now_val - float(_REJECT_SHADOW_LAST_EVAL_TS)) < interval:
            return {"status": "skipped", "processed": 0, "reason": "interval_guard"}
    if not _REJECT_SHADOW_LOCK.acquire(blocking=False):
        return {"status": "skipped", "processed": 0, "reason": "busy"}
    processed = 0
    evaluated = 0
    no_data = 0
    table = _shadow_table_name()
    try:
        # Reject-shadow evaluation is analytics-only. In SIM/PAPER/OFFHOURS we can safely
        # flush the async tick-store queue to make outcomes deterministic. In LIVE we
        # avoid forcing a flush boundary because it can stall under SQLite contention.
        mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).strip().upper()
        if mode != "LIVE":
            try:
                tick_store.flush_pending_ticks()
            except Exception:
                pass
        db_path = _shadow_db_path()
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            table = _ensure_reject_shadow_table(conn)
            limit = int(batch_size or _shadow_eval_batch_size())
            rows = conn.execute(
                f"""
                SELECT candidate_key, instrument_token, trade_side, entry_price, reject_ts_epoch, eval_due_ts_epoch
                FROM {table}
                WHERE status='PENDING' AND eval_due_ts_epoch <= ?
                ORDER BY eval_due_ts_epoch ASC
                LIMIT ?
                """,
                (float(now_val), int(limit)),
            ).fetchall()
            for row in rows:
                processed += 1
                candidate_key = str(row["candidate_key"])
                token = _as_int(row["instrument_token"])
                entry_price = _as_float(row["entry_price"])
                reject_ts = _as_float(row["reject_ts_epoch"])
                eval_due = _as_float(row["eval_due_ts_epoch"])
                side = str(row["trade_side"] or "BUY").upper()
                direction = -1.0 if side.startswith("SELL") else 1.0
                status = "NO_DATA"
                end_price = None
                pnl = None
                evidence: dict[str, Any] = {"reason": "missing_tick_data"}
                if token is not None and entry_price is not None and reject_ts is not None and eval_due is not None:
                    tick_row = conn.execute(
                        """
                        SELECT last_price, timestamp_epoch
                        FROM ticks
                        WHERE instrument_token = ?
                          AND timestamp_epoch IS NOT NULL
                          AND timestamp_epoch >= ?
                          AND timestamp_epoch <= ?
                          AND last_price IS NOT NULL
                        ORDER BY timestamp_epoch DESC
                        LIMIT 1
                        """,
                        (int(token), float(reject_ts), float(eval_due)),
                    ).fetchone()
                    if tick_row:
                        end_price = _as_float(tick_row[0])
                        if end_price is not None:
                            pnl = (float(end_price) - float(entry_price)) * float(direction)
                            status = "EVALUATED"
                            evidence = {
                                "tick_ts_epoch": _as_float(tick_row[1]),
                                "direction": side,
                                "entry_price": float(entry_price),
                                "end_price": float(end_price),
                            }
                if status == "EVALUATED":
                    evaluated += 1
                else:
                    no_data += 1
                conn.execute(
                    f"""
                    UPDATE {table}
                    SET status=?,
                        evaluated_ts_epoch=?,
                        end_price=?,
                        hypothetical_pnl=?,
                        evidence_json=?
                    WHERE candidate_key=?
                    """,
                    (
                        status,
                        float(now_val),
                        end_price,
                        pnl,
                        json.dumps(evidence, ensure_ascii=True),
                        candidate_key,
                    ),
                )
                _append_shadow_jsonl(
                    {
                        "event": "evaluate",
                        "ts_epoch": float(now_val),
                        "candidate_key": candidate_key,
                        "status": status,
                        "end_price": end_price,
                        "hypothetical_pnl": pnl,
                        "evidence": evidence,
                    }
                )
        _REJECT_SHADOW_LAST_EVAL_TS = float(now_val)
        return {
            "status": "ok",
            "processed": int(processed),
            "evaluated": int(evaluated),
            "no_data": int(no_data),
            "table": table,
            "db_path": str(_shadow_db_path()),
        }
    except Exception as exc:
        logger.warning("reject_shadow_eval_failed err=%s", f"{type(exc).__name__}:{exc}")
        return {"status": "error", "processed": int(processed), "error": f"{type(exc).__name__}:{exc}"}
    finally:
        _REJECT_SHADOW_LOCK.release()


def append_reject_telemetry(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if not bool(getattr(cfg, "REJECT_TELEMETRY_ENABLE", True)):
        return None
    row = _normalize_reject_row(payload)
    _append_memory(row)
    path = _daily_path(int(row["timestamp_epoch_ms"]))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    except Exception as exc:
        logger.warning("reject_telemetry_write_failed err=%s", f"{type(exc).__name__}:{exc}")
    try:
        _seed_reject_shadow(row)
    except Exception:
        pass
    try:
        evaluate_reject_shadow_once()
    except Exception:
        pass
    return row


def _read_recent_from_daily_files(limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    log_dir = _reject_telemetry_log_dir()
    files = sorted(log_dir.glob("rejects_*.jsonl"))[-3:]
    tail: deque[dict[str, Any]] = deque(maxlen=limit)
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        tail.append(_normalize_reject_row(payload))
        except Exception:
            continue
    return list(tail)


def clear_reject_telemetry_memory() -> None:
    with _REJECT_TELEMETRY_LOCK:
        _REJECT_TELEMETRY_ROWS.clear()


def get_recent_reject_telemetry(limit: int = 50) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, int(limit))
    except Exception:
        safe_limit = 50
    with _REJECT_TELEMETRY_LOCK:
        mem_rows = [dict(x) for x in _REJECT_TELEMETRY_ROWS[-safe_limit:]]
    file_rows = _read_recent_from_daily_files(safe_limit)
    merged = file_rows + mem_rows
    deduped: list[dict[str, Any]] = []
    seen = set()
    for row in sorted(merged, key=lambda x: float(x.get("timestamp_epoch_ms") or 0.0), reverse=True):
        key = (
            int(row.get("timestamp_epoch_ms") or 0),
            str(row.get("symbol") or ""),
            str(row.get("strike") or ""),
            str(row.get("trade_side") or ""),
            str(row.get("reject_reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= safe_limit:
            break
    return deduped
