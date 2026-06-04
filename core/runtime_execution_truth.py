from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.feed_truth_contract import FeedTruthContract, build_feed_truth_contract


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


def _append_blocker(blockers: list[str], reason: Any) -> None:
    normalized = _normalized_reason_text(reason)
    if not normalized or normalized in {"OK", "LIVE", "FRESH", "NONE"} or normalized.endswith("_OK"):
        return
    if normalized not in blockers:
        blockers.append(normalized)


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
    quote_health_state = _upper(quote_health.get("state"))
    quote_health_stale_reasons = [
        _normalized_reason_text(reason)
        for reason in _as_list(quote_health.get("stale_reasons"))
        if _normalized_reason_text(reason)
    ]
    runtime_state = _upper(market.get("runtime_state"))
    feed_truth_state = _upper(market.get("feed_truth_state"))
    feed_truth_reason_code = _upper(market.get("feed_truth_reason_code"))
    reconnect_blocked_reason = _upper(market.get("reconnect_blocked_reason"))
    feed_fresh = feed.get("feed_fresh")
    feed_ok = feed.get("feed_ok")
    if feed_ok is None and feed_fresh is not None:
        feed_ok = feed_fresh
    feed_truth_strict_live = feed.get("feed_truth_strict_live")
    if feed_truth_strict_live is None and feed_fresh is not None:
        feed_truth_strict_live = feed_fresh
    if feed_ok is False and quote_health_state in {"", "OK", "LIVE", "FRESH"}:
        quote_health_state = "BLOCKED"
    stale_reason_values = [
        _normalized_reason_text(reason)
        for reason in _as_list(feed.get("stale_reason") or feed.get("stale_reasons"))
        if _normalized_reason_text(reason)
    ]
    for reason in stale_reason_values:
        if reason not in quote_health_stale_reasons:
            quote_health_stale_reasons.append(reason)
    feed_blocked = (
        runtime_state in _BLOCKED_RUNTIME_STATES
        or feed_truth_state in {"RESTART_VERIFY_FAILED", "RECONNECT_BLOCKED", "MARKET_CLOSED"}
        or feed_truth_reason_code in _HARD_FEED_BLOCKERS
        or reconnect_blocked_reason in _HARD_FEED_BLOCKERS
    )
    if feed_blocked and quote_health_state in {"OK", "LIVE", "FRESH"}:
        quote_health_state = "BLOCKED"
        if "RECOVERY_BLOCKED" not in quote_health_stale_reasons:
            quote_health_stale_reasons.append("RECOVERY_BLOCKED")
    feed_truth_contract = build_feed_truth_contract(
        {
            "runtime_state": runtime_state,
            "ws_connected": market.get("ws_connected", market.get("effective_ws_connected")),
            "effective_ws_connected": market.get("effective_ws_connected"),
            "feed_truth_state": feed_truth_state,
            "feed_truth_reason_code": feed_truth_reason_code,
            "feed_ok": feed_ok,
            "feed_truth_strict_live": feed_truth_strict_live,
            "quote_health": {
                "state": quote_health_state,
                "stale_reasons": list(quote_health_stale_reasons),
            },
            "option_feed_block_reason": _upper(market.get("option_feed_block_reason")),
            "option_feed_block_reason_by_symbol": _as_mapping(market.get("option_feed_block_reason_by_symbol")),
            "reconnect_blocked_reason": _upper(market.get("reconnect_blocked_reason")),
            "recovery_action": _upper(market.get("recovery_action")),
            "latency_guard": latency,
        }
    )
    return {
        "runtime_state": runtime_state,
        "ws_connected": market.get("ws_connected", market.get("effective_ws_connected")),
        "feed_truth_state": feed_truth_state,
        "feed_truth_reason_code": feed_truth_reason_code,
        "feed_ok": feed_ok,
        "feed_truth_strict_live": feed_truth_strict_live,
        "feed_ws_connected": feed.get("ws_connected"),
        "feed_truth_state_snapshot": _upper(feed.get("feed_truth_state")),
        "option_feed_block_reason": _upper(market.get("option_feed_block_reason")),
        "option_feed_block_reason_by_symbol": _as_mapping(market.get("option_feed_block_reason_by_symbol")),
        "quote_health_state": quote_health_state,
        "quote_health_stale_reasons": quote_health_stale_reasons,
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
        "feed_truth_contract": feed_truth_contract.to_payload(),
        "feed_truth_contract_state": feed_truth_contract.state,
        "feed_truth_contract_entries_allowed": feed_truth_contract.entries_allowed,
        "feed_truth_contract_quotes_trusted": feed_truth_contract.quotes_trusted,
        "feed_truth_contract_depth_trusted": feed_truth_contract.depth_trusted,
        "feed_truth_contract_reconnect_allowed": feed_truth_contract.reconnect_allowed,
        "feed_truth_contract_process_restart_required": feed_truth_contract.process_restart_required,
        "feed_truth_contract_blockers": list(feed_truth_contract.blockers),
        "feed_truth_contract_advisory_reasons": list(feed_truth_contract.advisory_reasons),
    }


def _feed_truth_contract_from_context(ctx: Mapping[str, Any] | None) -> FeedTruthContract:
    context = _as_mapping(ctx)
    contract_payload = context.get("feed_truth_contract")
    if isinstance(contract_payload, Mapping):
        payload = dict(contract_payload)
        return FeedTruthContract(
            state=_upper(payload.get("state")),
            entries_allowed=bool(payload.get("entries_allowed")),
            exits_allowed=bool(payload.get("exits_allowed")),
            quotes_trusted=bool(payload.get("quotes_trusted")),
            depth_trusted=bool(payload.get("depth_trusted")),
            reconnect_allowed=bool(payload.get("reconnect_allowed")),
            process_restart_required=bool(payload.get("process_restart_required")),
            blockers=tuple(str(reason).strip().upper() for reason in list(payload.get("blockers") or []) if str(reason).strip()),
            advisory_reasons=tuple(str(reason).strip().upper() for reason in list(payload.get("advisory_reasons") or []) if str(reason).strip()),
            source_snapshot=_as_mapping(payload.get("source_snapshot")),
            reason_code=_upper(payload.get("reason_code") or payload.get("state")),
        )
    return build_feed_truth_contract(
        {
            "runtime_state": context.get("runtime_state"),
            "ws_connected": context.get("ws_connected"),
            "effective_ws_connected": context.get("ws_connected"),
            "feed_truth_state": context.get("feed_truth_state"),
            "feed_truth_reason_code": context.get("feed_truth_reason_code"),
            "feed_ok": context.get("feed_ok"),
            "feed_truth_strict_live": context.get("feed_truth_strict_live"),
            "quote_health": {
                "state": context.get("quote_health_state"),
                "stale_reasons": list(context.get("quote_health_stale_reasons") or []),
            },
            "option_feed_block_reason": context.get("option_feed_block_reason"),
            "option_feed_block_reason_by_symbol": context.get("option_feed_block_reason_by_symbol"),
            "reconnect_blocked_reason": context.get("reconnect_blocked_reason"),
            "recovery_action": context.get("recovery_action"),
            "latency_guard": {
                "latency_guard_triggered": context.get("latency_guard_triggered"),
                "latency_guard_mode": context.get("latency_guard_mode"),
                "latency_guard_action": context.get("latency_guard_action"),
                "latency_guard_source": context.get("latency_guard_source"),
                "latency_guard_reason": context.get("latency_guard_reason"),
                "latency_guard_metric": context.get("latency_guard_metric"),
                "latency_guard_value": context.get("latency_guard_value"),
                "latency_guard_threshold": context.get("latency_guard_threshold"),
                "latency_guard_age_sec": context.get("latency_guard_age_sec"),
                "latency_guard_last_ok_at": context.get("latency_guard_last_ok_at"),
                "latency_guard_last_bad_at": context.get("latency_guard_last_bad_at"),
                "latency_guard_recovery_required": context.get("latency_guard_recovery_required"),
            },
        }
    )


def _legacy_blocker_from_feed_truth_contract(reason: str, ctx: Mapping[str, Any]) -> str:
    normalized = _upper(reason)
    if normalized == "DISCONNECTED":
        return "WS_DISCONNECTED"
    if normalized == "STALE":
        feed_reason = _upper(ctx.get("feed_truth_reason_code"))
        option_reason = _upper(ctx.get("option_feed_block_reason"))
        if feed_reason == "STALE_OPTION_LTP" or option_reason == "STALE_OPTION_LTP":
            return "STALE_OPTION_LTP"
        return "STALE_OPTION_LTP"
    return normalized


def execution_truth_decision(context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ctx = _as_mapping(context)
    feed_truth_contract = _feed_truth_contract_from_context(ctx)
    blockers: list[str] = []
    mode = "executable"
    for blocker in feed_truth_contract.blockers:
        _append_blocker(blockers, _legacy_blocker_from_feed_truth_contract(blocker, ctx))

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
        _append_blocker(blockers, runtime_state)
    if ws_connected is False:
        _append_blocker(blockers, "WS_DISCONNECTED")
    if feed_ws_connected is False:
        _append_blocker(blockers, "WS_DISCONNECTED")
    if feed_ok is False:
        _append_blocker(blockers, "GLOBAL_FEED_UNHEALTHY")
    if feed_truth_strict_live is False:
        _append_blocker(blockers, "GLOBAL_FEED_UNHEALTHY")
    if feed_truth_state_snapshot in {"RESTART_VERIFY_FAILED", "RECONNECT_BLOCKED", "MARKET_CLOSED"}:
        _append_blocker(blockers, feed_truth_state_snapshot)
    if feed_truth_state in {"RESTART_VERIFY_FAILED", "RECONNECT_BLOCKED", "MARKET_CLOSED"}:
        _append_blocker(blockers, feed_truth_state)
    if feed_truth_state_snapshot in _HARD_FEED_BLOCKERS:
        _append_blocker(blockers, feed_truth_state_snapshot)
    if feed_truth_reason_code in _HARD_FEED_BLOCKERS:
        _append_blocker(blockers, feed_truth_reason_code)
    if option_feed_block_reason and option_feed_block_reason not in {"OK", "NONE"}:
        _append_blocker(blockers, option_feed_block_reason)
    if quote_health_state and quote_health_state not in {"OK", "LIVE", "FRESH", "BLOCKED"}:
        _append_blocker(blockers, quote_health_state)
    if quote_health_stale_reasons:
        for reason in quote_health_stale_reasons:
            _append_blocker(blockers, reason)
    if recovery_action == "PROCESS_RESTART_REQUIRED":
        _append_blocker(blockers, recovery_action)
    if reconnect_blocked_reason:
        _append_blocker(blockers, reconnect_blocked_reason)

    if latency_action in _ADVISORY_LATENCY_ACTIONS:
        if latency_action:
            _append_blocker(blockers, f"LATENCY_GUARD_{latency_action}")
    elif bool(ctx.get("latency_guard_triggered")) or latency_action:
        if latency_action:
            _append_blocker(blockers, f"LATENCY_GUARD_{latency_action}")
        elif latency_reason:
            _append_blocker(blockers, latency_reason)
        elif bool(ctx.get("latency_guard_triggered")):
            _append_blocker(blockers, "LATENCY_GUARD_TRIGGERED")

    advisory = False
    if feed_truth_contract.advisory_reasons and feed_truth_contract.state in {"LIVE", "DEGRADED"}:
        advisory = True
    if feed_truth_contract.state == "DEGRADED" and advisory:
        mode = "advisory"
    elif not feed_truth_contract.entries_allowed or feed_truth_contract.state in {"AUTH_BLOCKED", "IMPORT_MISSING", "RECOVERY_BLOCKED", "DISCONNECTED", "STALE", "UNKNOWN"}:
        mode = "blocked"
    else:
        mode = "executable"

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
        "feed_truth_contract": feed_truth_contract.to_payload(),
        "execution_truth_blockers": list(dict.fromkeys(blockers)),
        "execution_truth_source": (
            "latency_guard"
            if any(reason.startswith("LATENCY_GUARD_") for reason in blockers)
            else "feed_runtime"
            if blockers
            else "candidate"
        ),
        "visibility_bucket": visibility_bucket,
        "reportable_executable": mode == "executable" and feed_truth_contract.entries_allowed and feed_truth_contract.quotes_trusted,
        "execution_allowed": mode == "executable" and feed_truth_contract.entries_allowed,
        "eligible_for_execution": mode == "executable" and feed_truth_contract.entries_allowed,
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
