from __future__ import annotations

from typing import Any

from .runtime import (
    FeedGroupMetrics,
    FeedHealthMachine,
    FeedHealthState,
    FeedGroupKey,
    classify_group,
    get_runtime_feed_health,
)


def check_execution_allowed(
    symbol: str | None,
    *,
    machine: FeedHealthMachine | None = None,
    metrics_map: dict[FeedGroupKey, FeedGroupMetrics] | None = None,
) -> tuple[bool, str, str, dict[str, Any]]:
    """
    Fail-closed execution gate based on runtime feed health state.
    Returns: (allowed, reject_reason, state_name, details)
    """
    group_key = classify_group(str(symbol or ""))

    if machine is None or metrics_map is None:
        runtime_machine, runtime_metrics = get_runtime_feed_health()
        if machine is None:
            machine = runtime_machine
        if metrics_map is None:
            metrics_map = runtime_metrics

    if "UNKNOWN" in group_key:
        details = {
            "group_key": group_key,
            "state": "UNKNOWN",
            "reason": "unknown_group",
        }
        return False, "feed_state_UNKNOWN", "DOWN", details

    metrics = (metrics_map or {}).get(group_key)
    if metrics is None:
        details = {
            "group_key": group_key,
            "state": "UNKNOWN",
            "reason": "group_metrics_missing",
        }
        return False, "feed_state_UNKNOWN", "DOWN", details

    snapshot = metrics.snapshot()
    result = machine.update_group(group_key, snapshot)
    state = result.get("state")
    if not isinstance(state, FeedHealthState):
        details = {
            "group_key": group_key,
            "state": "UNKNOWN",
            "reason": "invalid_state",
            "snapshot": snapshot,
        }
        return False, "feed_state_UNKNOWN", "DOWN", details

    state_name = state.name
    reason = str(result.get("reason") or "")
    details = {
        "group_key": group_key,
        "state": state_name,
        "reason": reason,
        "snapshot": snapshot,
    }
    if state is FeedHealthState.OK:
        return True, "ok", state_name, details
    return False, f"feed_state_{state_name}", state_name, details
