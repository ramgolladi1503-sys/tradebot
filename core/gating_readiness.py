from typing import Dict, Any

HARD_BLOCKERS = {
    "STALE_OPTION_LTP",
    "no_ws_messages",
    "missing_execution_entry",
    "missing_option_tokens",
}


def compute_readiness(candidate: Dict[str, Any]) -> Dict[str, Any]:
    blocker = str(candidate.get("primary_blocker") or "").strip()

    execution_entry_status = str(candidate.get("execution_entry_status") or "").lower()
    execution_allowed = bool(candidate.get("execution_allowed"))

    # Feed evidence
    tick_age = candidate.get("latest_option_tick_age_sec")

    if blocker in HARD_BLOCKERS:
        return {
            "readiness": "ADVISORY_ONLY",
            "execution_allowed": False,
            "reason": blocker,
        }

    if tick_age is not None and tick_age > 5:
        return {
            "readiness": "ADVISORY_ONLY",
            "execution_allowed": False,
            "reason": "STALE_OPTION_LTP",
        }

    if execution_allowed and execution_entry_status == "executable":
        return {
            "readiness": "EXECUTABLE",
            "execution_allowed": True,
            "reason": None,
        }

    if execution_entry_status in {"ready", "candidate"}:
        return {
            "readiness": "READY_NOT_APPROVED",
            "execution_allowed": False,
            "reason": "not_approved",
        }

    return {
        "readiness": "SIGNAL_ONLY",
        "execution_allowed": False,
        "reason": "signal_only",
    }
