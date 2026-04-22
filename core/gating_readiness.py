from __future__ import annotations

from typing import Any


HARD_BLOCKERS = {
    "STALE_OPTION_LTP",
    "NO_WS_MESSAGES",
    "MISSING_EXECUTION_ENTRY",
    "MISSING_OPTION_TOKENS",
    "FEED_DOWN",
}

_READY_ENTRY_STATUSES = {"ready", "candidate", "pending", "queued"}
_EXECUTABLE_ENTRY_STATUSES = {"executable", "ok", "live_ok", "valid"}


def _candidate_value(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _normalized_blocker(candidate: Any) -> str | None:
    blocker = str(_candidate_value(candidate, "primary_blocker") or "").strip().upper()
    return blocker or None


def compute_readiness(candidate: Any) -> dict[str, Any]:
    blocker = _normalized_blocker(candidate)
    execution_entry_status = str(_candidate_value(candidate, "execution_entry_status") or "").strip().lower()
    execution_allowed_raw = _candidate_value(candidate, "execution_allowed")
    execution_allowed = bool(execution_allowed_raw) if execution_allowed_raw is not None else False
    tick_age = _safe_float(_candidate_value(candidate, "latest_option_tick_age_sec"))

    if blocker in HARD_BLOCKERS:
        return {
            "readiness": "ADVISORY_ONLY",
            "candidate_status": "advisory_only",
            "execution_status": "advisory_only",
            "candidate_class": "SIGNAL_ONLY",
            "execution_allowed": False,
            "is_executable": False,
            "reason": blocker,
        }

    if tick_age is not None and tick_age > 5.0:
        return {
            "readiness": "ADVISORY_ONLY",
            "candidate_status": "advisory_only",
            "execution_status": "advisory_only",
            "candidate_class": "SIGNAL_ONLY",
            "execution_allowed": False,
            "is_executable": False,
            "reason": "STALE_OPTION_LTP",
        }

    if execution_allowed and execution_entry_status in _EXECUTABLE_ENTRY_STATUSES:
        return {
            "readiness": "EXECUTABLE",
            "candidate_status": "executable",
            "execution_status": "executable",
            "candidate_class": "EXECUTABLE",
            "execution_allowed": True,
            "is_executable": True,
            "reason": None,
        }

    if execution_entry_status in _READY_ENTRY_STATUSES:
        return {
            "readiness": "READY_NOT_APPROVED",
            "candidate_status": "displayable",
            "execution_status": "queue_only",
            "candidate_class": "NEAR_EXECUTABLE",
            "execution_allowed": False,
            "is_executable": False,
            "reason": blocker or "not_approved",
        }

    return {
        "readiness": "SIGNAL_ONLY",
        "candidate_status": "displayable",
        "execution_status": "advisory_only",
        "candidate_class": "SIGNAL_ONLY",
        "execution_allowed": False,
        "is_executable": False,
        "reason": blocker or "signal_only",
    }
