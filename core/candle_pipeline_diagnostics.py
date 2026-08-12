"""Bounded, read-only diagnostics for the live candle pipeline.

This module is intentionally observational: failures to write diagnostics are
swallowed and the caller's business result is never changed.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import ensure_dir, runtime_dir


TRACE_PATH = runtime_dir() / "diagnostics" / "candle_pipeline_trace.jsonl"
_LOCK = threading.Lock()
_EMITTED: set[tuple[str, str, str, str]] = set()
_MAX_KEYS = 4096


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def emit_candle_pipeline_event(
    *,
    symbol: str,
    timeframe: str,
    stage: str,
    reason: str = "",
    source_event_ts: Any = None,
    bucket_start: Any = None,
    bucket_end: Any = None,
    bar_ts: Any = None,
    bar_state: str = "",
    bar_count: int | None = None,
    run_id: str | None = None,
    feed_session_id: str | None = None,
    instrument_token: int | str | None = None,
    producer: str = "",
    consumer: str = "",
) -> bool:
    """Append one compact transition event, at most once per material key."""
    key = (str(symbol), str(timeframe), str(stage), str(bar_ts or bucket_start or ""))
    with _LOCK:
        if key in _EMITTED or len(_EMITTED) >= _MAX_KEYS:
            return False
        _EMITTED.add(key)
    try:
        now = time.time()
        payload = {
            "ts_epoch": now,
            "ts_ist": datetime.now().astimezone().isoformat(),
            "run_id": run_id,
            "feed_session_id": feed_session_id,
            "symbol": str(symbol),
            "instrument_token": instrument_token,
            "timeframe": str(timeframe),
            "stage": str(stage),
            "source_event_ts": _json_value(source_event_ts),
            "bucket_start": _json_value(bucket_start),
            "bucket_end": _json_value(bucket_end),
            "bar_ts": _json_value(bar_ts),
            "bar_state": str(bar_state),
            "bar_count": bar_count,
            "producer": str(producer),
            "consumer": str(consumer),
            "reason": str(reason),
            "read_only": True,
            "is_order_action": False,
        }
        target = Path(TRACE_PATH)
        ensure_dir(target.parent)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str) + "\n")
        return True
    except Exception:
        return False


def reset_diagnostic_dedupe_for_tests() -> None:
    with _LOCK:
        _EMITTED.clear()
