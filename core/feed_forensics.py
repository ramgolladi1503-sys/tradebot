"""Bounded, append-only read-only feed forensic evidence."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
_LOCK = threading.Lock()
_LAST_WRITE: dict[str, float] = {}


def _root() -> Path | None:
    if os.getenv("FEED_FORENSICS_ENABLED", "false").lower() != "true":
        return None
    value = str(os.getenv("TRADEBOT_FEED_FORENSICS_ROOT", "") or "").strip()
    return Path(value) if value else None


def append_event(event_type: str, *, status: str = "UNKNOWN", reason: str | None = None,
                interval_seconds: float = 5.0, **fields: Any) -> bool:
    """Append one bounded factual event; disabled instrumentation is a no-op."""
    root = _root()
    if root is None:
        return False
    now = float(fields.pop("receipt_epoch", None) or time.time())
    key = f"{event_type}:{fields.get('instrument_token', '')}"
    with _LOCK:
        if interval_seconds > 0 and now - _LAST_WRITE.get(key, 0.0) < interval_seconds:
            return False
        payload = {
            "schema_version": SCHEMA_VERSION,
            "session_id": os.getenv("RUN_ID") or None,
            "producer_sha": os.getenv("TRADEBOT_COMMIT_SHA") or None,
            "event_type": event_type,
            "receipt_epoch": now,
            "feed_session_id": fields.pop("feed_session_id", None),
            "reconnect_generation": fields.pop("reconnect_generation", None),
            "thread_name": fields.pop("thread_name", threading.current_thread().name),
            "status": status,
            "reason": reason,
            **fields,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        payload["row_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        root.mkdir(parents=True, exist_ok=True)
        with (root / "feed_forensics.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        _LAST_WRITE[key] = now
        return True


def classify_session(root: Path) -> dict[str, Any]:
    """Classify persisted progress without treating missing evidence as zero."""
    path = root / "feed_forensics.jsonl"
    if not path.is_file():
        return {"classification": "UNKNOWN", "reason": "forensic_ledger_missing", "event_count": 0}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    def last(event: str) -> dict[str, Any] | None:
        values = [row for row in rows if row.get("event_type") == event]
        return values[-1] if values else None
    callback = last("WS_CALLBACK")
    tick = last("TICK_PERSISTENCE_PROGRESS")
    depth = last("DEPTH_PERSISTENCE_PROGRESS")
    runtime = last("RUNTIME_PERSISTENCE_PROGRESS")
    watchdog = last("FEED_WATCHDOG")
    recovery_success = last("RECOVERY_SUCCEEDED")
    recovery_failed = last("RECOVERY_FAILED")
    if recovery_success:
        classification = "RECONNECT_TRIGGERED_AND_RECOVERED"
    elif recovery_failed:
        classification = "RECONNECT_TRIGGERED_AND_FAILED"
    elif not callback:
        classification = "UNKNOWN"
    elif tick and tick.get("status") == "STALLED":
        classification = "CALLBACKS_CONTINUED_BUT_TICK_WRITER_STALLED"
    elif depth and depth.get("status") == "STALLED":
        classification = "DEPTH_WRITER_STALLED"
    elif runtime and runtime.get("status") == "STALLED":
        classification = "RUNTIME_SNAPSHOT_WRITER_STALLED"
    elif watchdog and watchdog.get("status") == "STALLED":
        classification = "WATCHDOG_ONLY_STALLED"
    elif watchdog and watchdog.get("feed_ok") is False and callback.get("receipt_epoch") == watchdog.get("latest_callback_epoch"):
        classification = "BROKER_FEED_STOPPED_DELIVERING"
    elif all(row is not None for row in (callback, tick, runtime)):
        classification = "SESSION_HEALTHY"
    else:
        classification = "UNKNOWN"
    return {"classification": classification, "event_count": len(rows), "last_events": {
        "WS_CALLBACK": callback, "TICK_PERSISTENCE_PROGRESS": tick,
        "DEPTH_PERSISTENCE_PROGRESS": depth, "RUNTIME_SNAPSHOT_PROGRESS": runtime,
        "FEED_WATCHDOG": watchdog,
    }}
