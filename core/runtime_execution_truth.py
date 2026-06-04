from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_BLOCKED_RUNTIME_STATES = {"RECOVERY_BLOCKED", "AUTH_BLOCKED", "STOPPED"}
_HARD_FEED_BLOCKERS = {
    "WS_DISCONNECTED",
    "GLOBAL_FEED_UNHEALTHY",
    "MARKET_CLOSED",
    "NO_LIVE_OPTION_FEED",
    "STALE_OPTION_LTP",
    "LTP_STALE",
    "DEPTH_STALE",
    "WS1006_PROCESS_RESTART_REQUIRED",
    "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED",
    "RECOVERY_BLOCKED",
}
_ADVISORY_LATENCY_ACTIONS = {"DEGRADE_EXIT_ONLY", "COOLDOWN"}


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalized_reason_text(value: Any) -> str:
    return _upper(value)


def build_execution_truth_context(
    *,
    market_data: Mapping[str, Any] | None = None,
    feed_truth: Mapping[str, Any] | None = None,
    latency_guard: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    market = _as_mapping(market_data)
    feed = _as_mapping(feed_truth)
    latency = _as_mapping(latency_guard)
    quote_health = _as_mapping(market.get("quote_health"))
    return {
        "runtime_state": _upper(market.get("runtime_state")),
        "ws_connected": market.get("ws_connected", market.get("effective_ws_connected")),
        "feed_truth_state": _upper(market.get("feed_truth_state")),
        "feed_truth_reason_code": _upper(market.get("feed_truth_reason_code")),
        "feed_ok": feed.get("feed_ok"),
        "feed_truth_strict_live": feed.get("feed_truth_strict_live"),
        "feed_ws_connected": feed.get("ws_connected"),
        "feed_truth_state_snapshot": _upper(feed.get("feed_truth_state")),
        "option_feed_block_reason": _upper(market.get("option_feed_block_reason")),
        "option_feed_block_reason_by_symbol": _as_mapping(market.get("option_feed_block_reason_by_symbol")),
        "quote_health_state": _upper(quote_health.get("state")),
        "quote_health_stale_reasons": [
            _normalized_reason_text(reason) for reason in _as_list(quote_health.get("stale_reasons")) if _normalized_reason_text(reason)
        ],
        "latency_guard_triggered": latency.get("latency_guard_triggered"),
        "latency_guard_mode": _upper(latency.get("latency_guard_mode")),
        "latency_guard_action": _upper(latency.get("latency_guard_action")),
        "latency_guard_source": latency.get("latency_guard_source"),
        "latency_guard_reason": _upper(latency.get("latency_guard_reason")),
        "latency_guard_metric": latency.get("latency_guard_metric"),
        "latency_guard_value": latency.get("latency_guard_value"),
        "latency_guard_threshold": latency.get("latency_guard_threshold"),
        "latency_guard_age_sec": latency.get("latency_guard_age_sec"),
        "latency_guard_last_ok_at": latency.get("latency_guard_last_ok_at"),
        "latency_guard_last_bad_at": latency.get("latency_guard_last_bad_at"),
        "latency_guard_recovery_required": latency.get("latency_guard_recovery_required"),
        "recovery_action": _upper(market.get("recovery_action")),
        "reconnect_blocked_reason": _upper(market.get("reconnect_blocked_reason")),
    }


def execution_truth_decision(context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ctx = _as_mapping(context)
    blockers: list[str] = []
    mode = "executable"

    runtime_state = _upper(ctx.get("runtime_state"))
    ws_connected = ctx.get("ws_connected")
    feed_truth_state = _upper(ctx.get("feed_truth_state"))
    feed_truth_reason_code = _upper(ctx.get("feed_truth_reason_code"))
    feed_ok = ctx.get("feed_ok")
    feed_truth_strict_live = ctx.get("feed_truth_strict_live")
    feed_ws_connected = ctx.get("feed_ws_connected")
    feed_truth_state_snapshot = _upper(ctx.get("feed_truth_state_snapshot"))
    option_feed_block_reason = _upper(ctx.get("option_feed_block_reason"))
    quote_health_state = _upper(ctx.get("quote_health_state"))
    quote_health_stale_reasons = [_normalized_reason_text(reason) for reason in _as_list(ctx.get("quote_health_stale_reasons")) if _normalized_reason_text(reason)]
    latency_action = _upper(ctx.get("latency_guard_action"))
    latency_reason = _upper(ctx.get("latency_guard_reason"))
    recovery_action = _upper(ctx.get("recovery_action"))
    reconnect_blocked_reason = _upper(ctx.get("reconnect_blocked_reason"))

    if runtime_state in _BLOCKED_RUNTIME_STATES:
        blockers.append(runtime_state)
    if ws_connected is False:
        blockers.append("WS_DISCONNECTED")
    if feed_ws_connected is False:
        blockers.append("WS_DISCONNECTED")
    if feed_ok is False:
        blockers.append("GLOBAL_FEED_UNHEALTHY")
    if feed_truth_strict_live is False:
        blockers.append("GLOBAL_FEED_UNHEALTHY")
    if feed_truth_state_snapshot in {"RESTART_VERIFY_FAILED", "RECONNECT_BLOCKED", "MARKET_CLOSED"}:
        blockers.append(feed_truth_state_snapshot)
    if feed_truth_state in {"RESTART_VERIFY_FAILED", "RECONNECT_BLOCKED", "MARKET_CLOSED"}:
        blockers.append(feed_truth_state)
    if feed_truth_state_snapshot in _HARD_FEED_BLOCKERS:
        blockers.append(feed_truth_state_snapshot)
    if feed_truth_reason_code in _HARD_FEED_BLOCKERS:
        blockers.append(feed_truth_reason_code)
    if option_feed_block_reason and option_feed_block_reason not in {"OK", "NONE"}:
        blockers.append(option_feed_block_reason)
    if quote_health_state and quote_health_state not in {"OK", "LIVE", "FRESH"}:
        blockers.append(quote_health_state)
    if quote_health_stale_reasons:
        blockers.extend(quote_health_stale_reasons)
    if recovery_action == "PROCESS_RESTART_REQUIRED":
        blockers.append(recovery_action)
    if reconnect_blocked_reason:
        blockers.append(reconnect_blocked_reason)

    advisory = False
    if latency_action in _ADVISORY_LATENCY_ACTIONS:
        advisory = True
        blockers.append(f"LATENCY_GUARD_{latency_action}")
    elif bool(ctx.get("latency_guard_triggered")) or latency_action:
        if latency_action:
            blockers.append(f"LATENCY_GUARD_{latency_action}")
        elif latency_reason:
            blockers.append(latency_reason)
        elif bool(ctx.get("latency_guard_triggered")):
            blockers.append("LATENCY_GUARD_TRIGGERED")

    blocker_list = [item for item in blockers if item]
    hard_reason_markers = {
        "WS_DISCONNECTED",
        "GLOBAL_FEED_UNHEALTHY",
        "MARKET_CLOSED",
        "NO_LIVE_OPTION_FEED",
        "STALE_OPTION_LTP",
        "LTP_STALE",
        "DEPTH_STALE",
        "WS1006_PROCESS_RESTART_REQUIRED",
        "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED",
        "RECOVERY_BLOCKED",
        "RESTART_VERIFY_FAILED",
        "RECONNECT_BLOCKED",
    }
    hard_blocked = bool(
        any(
            reason in hard_reason_markers
            or (reason.startswith("LATENCY_GUARD_") and reason not in {f"LATENCY_GUARD_{action}" for action in _ADVISORY_LATENCY_ACTIONS})
            for reason in blocker_list
        )
    )

    if hard_blocked:
        mode = "blocked"
    elif advisory:
        mode = "advisory"

    if mode == "blocked":
        permission = "BLOCK"
        final_action = "BLOCK"
        execution_status = "blocked"
        readiness = "BLOCKED"
        candidate_status = "blocked"
        visibility_bucket = "blocked"
    elif mode == "advisory":
        permission = "QUEUE_ONLY"
        final_action = "QUEUE_ONLY"
        execution_status = "queue_only"
        readiness = "QUEUE_ONLY"
        candidate_status = "advisory_only"
        visibility_bucket = "advisory"
    else:
        permission = "EXECUTE"
        final_action = "EXECUTE"
        execution_status = "executable"
        readiness = "READY"
        candidate_status = "executable"
        visibility_bucket = "executable"

    return {
        "execution_truth_state": mode,
        "execution_truth_blocked": mode == "blocked",
        "execution_truth_advisory": mode == "advisory",
        "execution_truth_blockers": blocker_list,
        "execution_truth_source": (
            "latency_guard"
            if any(reason.startswith("LATENCY_GUARD_") for reason in blocker_list)
            else "feed_runtime"
            if blocker_list
            else "candidate"
        ),
        "visibility_bucket": visibility_bucket,
        "reportable_executable": mode == "executable",
        "execution_allowed": mode == "executable",
        "eligible_for_execution": mode == "executable",
        "permission": permission,
        "final_action": final_action,
        "execution_status": execution_status,
        "readiness": readiness,
        "candidate_status": candidate_status,
    }


def normalize_candidate_execution_truth_payload(
    payload: Mapping[str, Any] | None,
    *,
    execution_truth_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(payload or {})
    original_executable_signals = any(
        bool(out.get(key))
        for key in ("execution_allowed", "eligible_for_execution")
    ) or str(out.get("permission") or "").strip().upper() == "EXECUTE" or str(out.get("final_action") or "").strip().upper() == "EXECUTE" or str(out.get("execution_status") or "").strip().lower() == "executable" or str(out.get("readiness") or "").strip().upper() == "READY"
    truth = execution_truth_decision(execution_truth_context)
    if not truth["execution_truth_blockers"] and truth["reportable_executable"]:
        out.setdefault("execution_truth_state", truth["execution_truth_state"])
        out.setdefault("execution_truth_blockers", [])
        out.setdefault("execution_truth_source", truth["execution_truth_source"])
        return out

    out["execution_truth_state"] = truth["execution_truth_state"]
    out["execution_truth_blocked"] = truth["execution_truth_blocked"]
    out["execution_truth_advisory"] = truth["execution_truth_advisory"]
    out["execution_truth_blockers"] = list(truth["execution_truth_blockers"])
    out["execution_truth_source"] = truth["execution_truth_source"]
    out["visibility_bucket"] = truth["visibility_bucket"]
    out["reportable_executable"] = truth["reportable_executable"]
    out["execution_allowed"] = truth["execution_allowed"]
    out["eligible_for_execution"] = truth["eligible_for_execution"]
    out["permission"] = truth["permission"]
    out["final_action"] = truth["final_action"]
    out["execution_status"] = truth["execution_status"]
    out["readiness"] = truth["readiness"]
    out["candidate_status"] = truth["candidate_status"]
    if not truth["reportable_executable"]:
        out["runtime_truth_consistent"] = False
        reasons = list(out.get("runtime_truth_reasons") or [])
        if "execution_truth_not_reportable" not in reasons:
            reasons.append("execution_truth_not_reportable")
        out["runtime_truth_reasons"] = reasons
    if truth["execution_truth_blocked"]:
        out.setdefault("reason", None)
        if not out.get("final_emit_block_reason"):
            out["final_emit_block_reason"] = truth["execution_truth_blockers"][0] if truth["execution_truth_blockers"] else "execution_truth_blocked"
    elif truth["execution_truth_advisory"]:
        if not out.get("final_emit_block_reason"):
            out["final_emit_block_reason"] = truth["execution_truth_blockers"][0] if truth["execution_truth_blockers"] else "latency_guard"
    return out


__all__ = [
    "build_execution_truth_context",
    "execution_truth_decision",
    "normalize_candidate_execution_truth_payload",
]
