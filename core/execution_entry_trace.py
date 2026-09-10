from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.paths import logs_dir
from core.log_writer import get_jsonl_writer

try:
    from config import config as cfg
except Exception:  # pragma: no cover - config import guard
    cfg = None


def _trace_enabled() -> bool:
    try:
        return bool(getattr(cfg, "EXECUTION_ENTRY_TRACE_ENABLE", True))
    except Exception:
        return True


def _trace_path() -> Path:
    try:
        raw = str(getattr(cfg, "EXECUTION_ENTRY_TRACE_PATH", "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw)
    return logs_dir() / "execution_entry_trace.jsonl"


def append_execution_entry_trace(
    *,
    module: str,
    stage: str,
    row: Mapping[str, Any] | None,
    execution_entry_before: Any = None,
    execution_entry_after: Any = None,
    execution_entry_status_before: Any = None,
    execution_entry_status_after: Any = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    if not _trace_enabled():
        return
    payload = dict(row or {})
    record = {
        "ts_epoch": datetime.now(timezone.utc).timestamp(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "module": str(module or ""),
        "stage": str(stage or ""),
        "trade_id": payload.get("trade_id"),
        "symbol": payload.get("symbol"),
        "strategy": payload.get("strategy") or payload.get("strategy_name"),
        "entry": payload.get("entry"),
        "display_entry": payload.get("display_entry"),
        "expected_entry": payload.get("expected_entry"),
        "current_ltp": payload.get("current_ltp"),
        "option_ltp_source": payload.get("option_ltp_source"),
        "quote_source": payload.get("quote_source"),
        "quote_validation_status": payload.get("quote_validation_status"),
        "permission": payload.get("permission"),
        "final_action": payload.get("final_action"),
        "execution_entry_before": execution_entry_before,
        "execution_entry_after": execution_entry_after if execution_entry_after is not None else payload.get("execution_entry"),
        "execution_entry_status_before": execution_entry_status_before,
        "execution_entry_status_after": (
            execution_entry_status_after
            if execution_entry_status_after is not None
            else payload.get("execution_entry_status")
        ),
        "execution_allowed": payload.get("execution_allowed"),
        "tradable": payload.get("tradable"),
    }
    if extra:
        record["extra"] = dict(extra)
    path = _trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    get_jsonl_writer(path).write(record)
