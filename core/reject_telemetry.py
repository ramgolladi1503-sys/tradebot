from __future__ import annotations
from core.paths import logs_dir

import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from config import config as cfg

logger = logging.getLogger(__name__)

_REJECT_TELEMETRY_LOCK = Lock()
_REJECT_TELEMETRY_ROWS: list[dict[str, Any]] = []


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
    trade_side = str(payload.get("trade_side") or payload.get("direction") or "").strip().upper() or None
    feed_state = str(payload.get("feed_state") or "").strip().upper() or None
    strike = _as_float(payload.get("strike"))
    return {
        "timestamp_epoch_ms": int(ts_epoch_ms),
        "ts_utc": datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).isoformat(),
        "symbol": symbol,
        "strike": strike,
        "trade_side": trade_side,
        "reject_reason": reject_reason,
        "quote_age_sec": _as_float(payload.get("quote_age_sec")),
        "spread_pct": _as_float(payload.get("spread_pct")),
        "feed_state": feed_state,
    }


def _append_memory(row: dict[str, Any]) -> None:
    with _REJECT_TELEMETRY_LOCK:
        _REJECT_TELEMETRY_ROWS.append(dict(row))
        limit = _in_memory_limit()
        if len(_REJECT_TELEMETRY_ROWS) > limit:
            del _REJECT_TELEMETRY_ROWS[:-limit]


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

