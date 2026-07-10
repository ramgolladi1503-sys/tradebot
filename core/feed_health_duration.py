from __future__ import annotations

from typing import Any


_HEALTHY_RUNTIME_STATES = {"LIVE", "RUNNING"}
_HEALTHY_TRUTH_STATES = {"LIVE", "OK", "HEALTHY"}


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _truth_reason(snapshot: dict[str, Any]) -> str:
    reason = str(snapshot.get("feed_truth_reason_code") or snapshot.get("reason") or "").strip()
    if reason:
        return reason
    reasons = snapshot.get("feed_truth_reasons")
    if isinstance(reasons, list) and reasons:
        return str(reasons[0] or "").strip() or "unknown"
    return "unknown"


def _is_snapshot_healthy(snapshot: dict[str, Any]) -> tuple[bool, str]:
    runtime_state = str(snapshot.get("runtime_state") or "").strip().upper()
    truth_state = str(snapshot.get("feed_truth_state") or "").strip().upper()
    if snapshot.get("ws_connected") is not True:
        return False, "ws_not_connected"
    if snapshot.get("feed_ok") is not True:
        return False, _truth_reason(snapshot)
    if runtime_state not in _HEALTHY_RUNTIME_STATES:
        return False, f"runtime_state:{runtime_state or 'missing'}"
    if truth_state and truth_state not in _HEALTHY_TRUTH_STATES:
        return False, _truth_reason(snapshot)
    return True, "healthy"


def build_feed_health_duration_artifact(
    snapshot: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
    target_window_sec: float = 3600.0,
    observed_epoch: float | None = None,
) -> dict[str, Any]:
    source_snapshot_epoch = _float_or_none(snapshot.get("ts_epoch")) or 0.0
    now_epoch = _float_or_none(observed_epoch)
    if now_epoch is None:
        now_epoch = source_snapshot_epoch
    target_sec = max(1.0, float(target_window_sec or 3600.0))
    previous_payload = dict(previous or {})
    healthy, reason = _is_snapshot_healthy(dict(snapshot or {}))

    previous_since = _float_or_none(previous_payload.get("current_healthy_since_epoch"))
    previous_longest = _float_or_none(previous_payload.get("longest_healthy_duration_sec")) or 0.0
    previous_last_unhealthy_epoch = _float_or_none(previous_payload.get("last_unhealthy_epoch"))
    previous_last_unhealthy_reason = str(previous_payload.get("last_unhealthy_reason") or "").strip() or None

    if healthy:
        since_epoch = previous_since if previous_since is not None and previous_since <= now_epoch else now_epoch
        duration_sec = max(0.0, now_epoch - since_epoch)
        last_unhealthy_epoch = previous_last_unhealthy_epoch
        last_unhealthy_reason = previous_last_unhealthy_reason
    else:
        since_epoch = None
        duration_sec = 0.0
        last_unhealthy_epoch = now_epoch
        last_unhealthy_reason = reason

    longest_sec = max(previous_longest, duration_sec)
    return {
        "schema_version": 1,
        "generated_epoch": now_epoch,
        "source_snapshot_epoch": source_snapshot_epoch,
        "source": "feed_runtime_latest",
        "healthy": bool(healthy),
        "health_reason": reason,
        "current_healthy_since_epoch": since_epoch,
        "current_healthy_duration_sec": round(float(duration_sec), 3),
        "longest_healthy_duration_sec": round(float(longest_sec), 3),
        "target_window_sec": round(float(target_sec), 3),
        "target_met": bool(duration_sec >= target_sec),
        "last_unhealthy_epoch": last_unhealthy_epoch,
        "last_unhealthy_reason": last_unhealthy_reason,
        "runtime_state": str(snapshot.get("runtime_state") or "").strip().upper() or None,
        "feed_truth_state": str(snapshot.get("feed_truth_state") or "").strip().upper() or None,
        "feed_truth_reason_code": str(snapshot.get("feed_truth_reason_code") or "").strip() or None,
        "ws_connected": snapshot.get("ws_connected"),
        "feed_ok": snapshot.get("feed_ok"),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
