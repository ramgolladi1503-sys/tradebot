from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import write_json_atomic
from core.paths import ensure_dir, runtime_dir


logger = logging.getLogger(__name__)


def _observability_enabled() -> bool:
    return bool(getattr(cfg, "PIPELINE_OBSERVABILITY_ENABLE", True))


def _schema_version() -> int:
    try:
        return int(getattr(cfg, "PIPELINE_OBSERVABILITY_SCHEMA_VERSION", 1))
    except Exception:
        return 1


def observability_dir() -> Path:
    return ensure_dir(runtime_dir() / "observability")


def pipeline_funnel_path() -> Path:
    return observability_dir() / "pipeline_funnel.json"


def trade_lifecycle_path() -> Path:
    return observability_dir() / "trade_lifecycle.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def write_pipeline_funnel(payload: dict[str, Any]) -> None:
    if not _observability_enabled():
        return
    try:
        record = dict(payload or {})
        record.setdefault("schema_version", _schema_version())
        record.setdefault("timestamp", _now_iso())
        for key in ("universe", "candidates", "scored", "ready", "executable", "emitted"):
            record[key] = _safe_int(record.get(key), default=0)
        path = pipeline_funnel_path()
        write_json_atomic(path, record)
    except Exception as exc:
        logger.warning("pipeline_funnel_write_failed err=%s:%s", type(exc).__name__, exc)


def append_trade_lifecycle_event(
    *,
    trade_id: str | None,
    symbol: str | None,
    strategy: str | None,
    stage: str,
    status: str,
    reason: str | None,
    timestamp: str | None = None,
    schema_version: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if not _observability_enabled():
        return
    if not trade_id:
        trade_id = "UNKNOWN"
    event = {
        "schema_version": int(schema_version or _schema_version()),
        "timestamp": timestamp or _now_iso(),
        "trade_id": str(trade_id),
        "symbol": str(symbol or ""),
        "strategy": str(strategy or ""),
        "stage": str(stage or "").strip().lower(),
        "status": str(status or "").strip().lower(),
        "reason": str(reason or "").strip() or None,
    }
    if isinstance(extra, dict) and extra:
        event.update(extra)
    try:
        path = trade_lifecycle_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception as exc:
        logger.warning("trade_lifecycle_append_failed err=%s:%s", type(exc).__name__, exc)


def build_lifecycle_event(
    *,
    trade_id: str | None,
    symbol: str | None,
    strategy: str | None,
    stage: str,
    status: str,
    reason: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": int(_schema_version()),
        "timestamp": _now_iso(),
        "trade_id": str(trade_id or "UNKNOWN"),
        "symbol": str(symbol or ""),
        "strategy": str(strategy or ""),
        "stage": str(stage or "").strip().lower(),
        "status": str(status or "").strip().lower(),
        "reason": str(reason or "").strip() or None,
        **(extra or {}),
    }


def append_trade_lifecycle_events(events: list[dict[str, Any]]) -> None:
    if not _observability_enabled():
        return
    if not events:
        return
    try:
        path = trade_lifecycle_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                payload = dict(event or {})
                payload.setdefault("schema_version", _schema_version())
                payload.setdefault("timestamp", _now_iso())
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception as exc:
        logger.warning("trade_lifecycle_append_batch_failed err=%s:%s", type(exc).__name__, exc)
