from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir
from core.runtime_boot_identity import classify_runtime_payload_freshness, stamp_runtime_payload
from core.log_writer import get_jsonl_writer

LATEST_NAME = "feed_startup_lifecycle_latest.json"
EVENTS_NAME = "feed_startup_lifecycle.jsonl"
MAX_EVENTS = 100


def feed_startup_lifecycle_path() -> Path:
    return logs_dir() / LATEST_NAME


def feed_startup_lifecycle_events_path() -> Path:
    return logs_dir() / EVENTS_NAME


def _now_epoch() -> float:
    return time.time()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _current_run_events(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    freshness = classify_runtime_payload_freshness(payload)
    if not freshness.get("is_current_run"):
        return []
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    return [dict(event) for event in events if isinstance(event, dict)]


def _is_safe_token_metadata_key(key_lower: str) -> bool:
    return (
        key_lower.endswith("tail4")
        or key_lower.endswith("len")
        or key_lower.endswith("present")
        or key_lower.endswith("token_count")
        or key_lower.endswith("tokens_count")
        or key_lower in {"token_count", "tokens"}
    )


def _safe_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, value in dict(details or {}).items():
        key = str(raw_key)
        key_lower = key.lower()
        if "token" in key_lower and not _is_safe_token_metadata_key(key_lower):
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def read_feed_startup_lifecycle(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else feed_startup_lifecycle_path()
    return _read_json(target)


def record_feed_startup_event(
    event: str,
    *,
    source: str,
    details: Mapping[str, Any] | None = None,
    error: str | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    event_name = str(event or "").strip().upper()
    source_name = str(source or "unknown").strip() or "unknown"
    ts_epoch = float(now_epoch if now_epoch is not None else _now_epoch())

    latest_path = feed_startup_lifecycle_path()
    events_path = feed_startup_lifecycle_events_path()
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    event_payload = stamp_runtime_payload(
        {
            "event": event_name,
            "source": source_name,
            "ts_epoch": ts_epoch,
            "details": _safe_details(details),
            "error": str(error or ""),
        },
        writer="feed_startup_lifecycle.event",
    )

    get_jsonl_writer(events_path).write(event_payload)

    previous = _read_json(latest_path)
    events = _current_run_events(previous)
    compact_event = {
        "event": event_name,
        "source": source_name,
        "ts_epoch": ts_epoch,
        "details": _safe_details(details),
        "error": str(error or ""),
    }
    events.append(compact_event)

    feed_runtime_snapshot_written = bool(previous.get("feed_runtime_snapshot_written")) if previous else False
    feed_runtime_snapshot_written = feed_runtime_snapshot_written or event_name == "FEED_RUNTIME_SNAPSHOT_WRITTEN"

    latest = stamp_runtime_payload(
        {
            "ts_epoch": ts_epoch,
            "state": event_name,
            "last_event": event_name,
            "last_error": str(error or ""),
            "feed_runtime_snapshot_written": feed_runtime_snapshot_written,
            "events_count": len(events),
            "events": events[-MAX_EVENTS:],
        },
        writer="feed_startup_lifecycle",
    )
    write_json_atomic(latest_path, latest)
    return latest
