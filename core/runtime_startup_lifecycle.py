from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir
from core.runtime_boot_identity import classify_runtime_payload_freshness, stamp_runtime_payload

LATEST_NAME = "runtime_startup_lifecycle_latest.json"
EVENTS_NAME = "runtime_startup_lifecycle.jsonl"
MAX_EVENTS = 200


def runtime_startup_lifecycle_path() -> Path:
    return logs_dir() / LATEST_NAME


def runtime_startup_lifecycle_events_path() -> Path:
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


def _is_safe_secret_metadata_key(key_lower: str) -> bool:
    return (
        key_lower.endswith("tail4")
        or key_lower.endswith("len")
        or key_lower.endswith("present")
        or key_lower.endswith("count")
        or key_lower.endswith("counts")
    )


def _safe_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    sensitive_markers = ("token", "secret", "password", "authorization", "api_key")
    for raw_key, value in dict(details or {}).items():
        key = str(raw_key)
        key_lower = key.lower()
        if any(marker in key_lower for marker in sensitive_markers) and not _is_safe_secret_metadata_key(key_lower):
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def read_runtime_startup_lifecycle(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else runtime_startup_lifecycle_path()
    return _read_json(target)


def record_runtime_startup_event(
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

    latest_path = runtime_startup_lifecycle_path()
    events_path = runtime_startup_lifecycle_events_path()
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    safe_details = _safe_details(details)
    event_payload = stamp_runtime_payload(
        {
            "event": event_name,
            "source": source_name,
            "ts_epoch": ts_epoch,
            "details": safe_details,
            "error": str(error or ""),
            "is_order_action": False,
        },
        writer="runtime_startup_lifecycle.event",
    )

    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, sort_keys=True, default=str) + "\n")

    previous = _read_json(latest_path)
    events = _current_run_events(previous)
    compact_event = {
        "event": event_name,
        "source": source_name,
        "ts_epoch": ts_epoch,
        "details": safe_details,
        "error": str(error or ""),
        "is_order_action": False,
    }
    events.append(compact_event)

    previous_flags = dict(previous.get("proof_flags") or {}) if isinstance(previous, dict) else {}
    proof_flags = {
        **previous_flags,
        "main_boot_started": previous_flags.get("main_boot_started", False) or event_name == "MAIN_BOOT_STARTED",
        "main_safety_validated": previous_flags.get("main_safety_validated", False) or event_name == "MAIN_SAFETY_VALIDATED",
        "main_auth_validated": previous_flags.get("main_auth_validated", False) or event_name == "MAIN_AUTH_VALIDATED",
        "orchestrator_init_started": previous_flags.get("orchestrator_init_started", False) or event_name == "ORCHESTRATOR_INIT_STARTED",
        "orchestrator_init_completed": previous_flags.get("orchestrator_init_completed", False) or event_name == "ORCHESTRATOR_INIT_COMPLETED",
        "live_monitoring_calling": previous_flags.get("live_monitoring_calling", False) or event_name == "LIVE_MONITORING_CALLING",
        "live_monitoring_returned": previous_flags.get("live_monitoring_returned", False) or event_name == "LIVE_MONITORING_RETURNED",
        "feed_start_request_boundary_reached": previous_flags.get("feed_start_request_boundary_reached", False) or event_name == "FEED_START_REQUEST_BOUNDARY_REACHED",
        "runtime_status_write_attempted": previous_flags.get("runtime_status_write_attempted", False) or event_name == "RUNTIME_STATUS_WRITE_ATTEMPTED",
        "runtime_status_write_completed": previous_flags.get("runtime_status_write_completed", False) or event_name == "RUNTIME_STATUS_WRITE_COMPLETED",
        "failure_seen": previous_flags.get("failure_seen", False) or event_name.endswith("_FAILED"),
    }

    latest = stamp_runtime_payload(
        {
            "ts_epoch": ts_epoch,
            "state": event_name,
            "last_event": event_name,
            "last_error": str(error or ""),
            "events_count": len(events),
            "events": events[-MAX_EVENTS:],
            "proof_flags": proof_flags,
            "is_order_action": False,
        },
        writer="runtime_startup_lifecycle",
    )
    write_json_atomic(latest_path, latest)
    return latest
