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


def _flag(previous_flags: Mapping[str, Any], name: str, event_name: str, *events: str) -> bool:
    return bool(previous_flags.get(name, False)) or event_name in set(events)


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
        "main_boot_started": _flag(previous_flags, "main_boot_started", event_name, "MAIN_BOOT_STARTED"),
        "main_safety_validated": _flag(previous_flags, "main_safety_validated", event_name, "MAIN_SAFETY_VALIDATED"),
        "main_auth_validation_calling": _flag(previous_flags, "main_auth_validation_calling", event_name, "MAIN_AUTH_VALIDATION_CALLING"),
        "main_auth_validation_completed": _flag(previous_flags, "main_auth_validation_completed", event_name, "MAIN_AUTH_VALIDATION_COMPLETED"),
        "main_auth_validated": _flag(previous_flags, "main_auth_validated", event_name, "MAIN_AUTH_VALIDATED", "MAIN_AUTH_VALIDATION_COMPLETED"),
        "instance_lock_calling": _flag(previous_flags, "instance_lock_calling", event_name, "INSTANCE_LOCK_CALLING"),
        "instance_lock_acquired": _flag(previous_flags, "instance_lock_acquired", event_name, "INSTANCE_LOCK_ACQUIRED"),
        "db_ready_calling": _flag(previous_flags, "db_ready_calling", event_name, "DB_READY_CALLING"),
        "db_ready_completed": _flag(previous_flags, "db_ready_completed", event_name, "DB_READY_COMPLETED"),
        "startup_security_calling": _flag(previous_flags, "startup_security_calling", event_name, "STARTUP_SECURITY_CALLING"),
        "startup_security_completed": _flag(previous_flags, "startup_security_completed", event_name, "STARTUP_SECURITY_COMPLETED"),
        "session_guard_calling": _flag(previous_flags, "session_guard_calling", event_name, "SESSION_GUARD_CALLING"),
        "session_guard_completed": _flag(previous_flags, "session_guard_completed", event_name, "SESSION_GUARD_COMPLETED"),
        "orchestrator_init_started": _flag(previous_flags, "orchestrator_init_started", event_name, "ORCHESTRATOR_INIT_STARTED", "ORCHESTRATOR_INIT_ENTERED"),
        "orchestrator_init_completed": _flag(previous_flags, "orchestrator_init_completed", event_name, "ORCHESTRATOR_INIT_COMPLETED"),
        "predictor_init_started": _flag(previous_flags, "predictor_init_started", event_name, "ORCHESTRATOR_PREDICTOR_INIT_STARTED"),
        "predictor_init_completed": _flag(previous_flags, "predictor_init_completed", event_name, "ORCHESTRATOR_PREDICTOR_INIT_COMPLETED"),
        "execution_engine_init_started": _flag(previous_flags, "execution_engine_init_started", event_name, "ORCHESTRATOR_EXECUTION_ENGINE_INIT_STARTED"),
        "execution_engine_init_completed": _flag(previous_flags, "execution_engine_init_completed", event_name, "ORCHESTRATOR_EXECUTION_ENGINE_INIT_COMPLETED"),
        "execution_router_init_started": _flag(previous_flags, "execution_router_init_started", event_name, "ORCHESTRATOR_EXECUTION_ROUTER_INIT_STARTED"),
        "execution_router_init_completed": _flag(previous_flags, "execution_router_init_completed", event_name, "ORCHESTRATOR_EXECUTION_ROUTER_INIT_COMPLETED"),
        "live_monitoring_calling": _flag(previous_flags, "live_monitoring_calling", event_name, "LIVE_MONITORING_CALLING"),
        "live_monitoring_returned": _flag(previous_flags, "live_monitoring_returned", event_name, "LIVE_MONITORING_RETURNED"),
        "feed_start_request_boundary_reached": _flag(previous_flags, "feed_start_request_boundary_reached", event_name, "FEED_START_REQUEST_BOUNDARY_REACHED"),
        "runtime_status_write_attempted": _flag(previous_flags, "runtime_status_write_attempted", event_name, "RUNTIME_STATUS_WRITE_ATTEMPTED"),
        "runtime_status_write_completed": _flag(previous_flags, "runtime_status_write_completed", event_name, "RUNTIME_STATUS_WRITE_COMPLETED"),
        "failure_seen": bool(previous_flags.get("failure_seen", False)) or event_name.endswith("_FAILED"),
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
