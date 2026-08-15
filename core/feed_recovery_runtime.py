from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_RESTART_REQUIRED_STATES = {
    "RESTART_REQUIRED",
    "WS1006_PROCESS_RESTART_REQUIRED",
    "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED",
    "RESTART_VERIFY_FAILED",
    "FEED_LIFECYCLE_FATAL",
}
_RECOVERY_BLOCKED_STATES = {"RECOVERY_BLOCKED", "RECONNECT_BLOCKED", "FEED_LIFECYCLE_FATAL"}
_RECOVERING_STATES = {"RECOVERING_WS_DROP", "RECONNECTING", "RESUBSCRIBING"}


@dataclass(frozen=True)
class FeedRecoveryRuntimeDecision:
    """Read-only feed recovery classification for runtime status surfaces."""

    recovery_state: str
    action_hint: str
    reason: str
    should_attempt_recovery: bool
    force_full_restart: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "recovery_state": self.recovery_state,
            "action_hint": self.action_hint,
            "reason": self.reason,
            "should_attempt_recovery": bool(self.should_attempt_recovery),
            "force_full_restart": bool(self.force_full_restart),
            "context": dict(self.context or {}),
        }


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if out > 1e12:
            out = out / 1000.0
        return out
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "None"):
            return default
        return int(value)
    except Exception:
        return default


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _state_reason(payload: dict[str, Any]) -> tuple[str, str]:
    state_machine = _mapping(payload.get("state_machine"))
    state = str(state_machine.get("state") or "").strip().upper()
    reason = str(state_machine.get("reason") or "").strip().lower()
    return state, reason


def _primary_option_blocker(payload: dict[str, Any]) -> str | None:
    blockers = payload.get("option_feed_block_reason_by_symbol") or {}
    if not isinstance(blockers, dict):
        return None
    for _symbol, value in sorted(blockers.items()):
        code = str(value or "").strip().upper()
        if code and code != "OK":
            return code
    return None


def _base_context(payload: dict[str, Any]) -> dict[str, Any]:
    state, reason = _state_reason(payload)
    return {
        "feed_ok": payload.get("feed_ok"),
        "ws_connected": payload.get("ws_connected"),
        "effective_ws_connected": payload.get("effective_ws_connected"),
        "runtime_state": str(payload.get("runtime_state") or "").strip().upper() or None,
        "state_machine_state": state or None,
        "state_machine_reason": reason or None,
        "last_tick_age_sec": _safe_float(payload.get("last_tick_age_sec")),
        "last_depth_age_sec": _safe_float(payload.get("last_depth_age_sec")),
        "subscribed_tokens_count": _safe_int(payload.get("subscribed_tokens_count")),
        "intended_tokens_count": _safe_int(payload.get("intended_tokens_count")),
        "subscribed_option_tokens_count": _safe_int(payload.get("subscribed_option_tokens_count")),
        "missing_option_tokens_count": _safe_int(payload.get("missing_option_tokens_count")),
        "restart_count_1h": _safe_int(payload.get("restart_count_1h")),
        "stale_strikes": _safe_int(payload.get("stale_strikes")),
        "primary_option_blocker": _primary_option_blocker(payload),
    }


def _full_feed_proof(payload: dict[str, Any]) -> tuple[bool, tuple[str, ...], dict[str, Any]]:
    blockers: list[str] = []
    feed_ok = payload.get("feed_ok")
    ws_connected = payload.get("ws_connected")
    effective_ws = payload.get("effective_ws_connected")
    runtime_state = str(payload.get("runtime_state") or "").strip().upper()
    feed_truth_state = str(payload.get("feed_truth_state") or "").strip().upper()
    feed_truth_reason_code = str(payload.get("feed_truth_reason_code") or "").strip().upper()
    option_block_reason = str(payload.get("option_feed_block_reason") or "").strip().upper()
    option_blockers_by_symbol = payload.get("option_feed_block_reason_by_symbol") or {}
    active_blockers_by_symbol = payload.get("option_active_blockers_by_symbol") or {}
    latest_ltp_age_sec = _safe_float(
        payload.get("latest_ltp_age_sec")
        or payload.get("ltp_age_sec")
        or payload.get("last_tick_age_sec")
    )
    latest_depth_age_sec = _safe_float(
        payload.get("latest_depth_age_sec")
        or payload.get("depth_age_sec")
        or payload.get("last_depth_age_sec")
    )
    max_ltp_age_sec = _safe_float(payload.get("max_ltp_age_sec")) or 2.5
    max_depth_age_sec = _safe_float(payload.get("max_depth_age_sec")) or 6.0
    underlying_tick_fresh = bool(
        payload.get("underlying_tick_fresh")
        or (latest_ltp_age_sec is not None and latest_ltp_age_sec <= float(max_ltp_age_sec))
    )
    depth_fresh = bool(
        payload.get("depth_fresh")
        or (latest_depth_age_sec is not None and latest_depth_age_sec <= float(max_depth_age_sec))
    )
    verified_option_symbols = [str(symbol).strip().upper() for symbol in list(payload.get("verified_option_symbols") or []) if str(symbol).strip()]
    missing_option_symbols = [str(symbol).strip().upper() for symbol in list(payload.get("missing_option_symbols") or []) if str(symbol).strip()]
    option_ticks_verified = bool(
        payload.get("option_ticks_verified")
        or (bool(verified_option_symbols) and not missing_option_symbols)
        or option_block_reason == "OK"
    )
    warmup_clean_cycles = _safe_int(payload.get("warmup_clean_cycles") or payload.get("clean_cycle_count"))
    warmup_required_clean_cycles = max(
        1,
        _safe_int(payload.get("warmup_required_clean_cycles") or payload.get("required_clean_cycles") or 3, default=3),
    )
    recovery_generation_id = _safe_int(payload.get("recovery_generation_id"))
    last_recovery_generation_id = _safe_int(payload.get("last_recovery_generation_id"))
    subscription_generation_id = _safe_int(payload.get("subscription_generation_id"))
    last_subscription_generation_id = _safe_int(payload.get("last_subscription_generation_id"))

    if feed_ok is False:
        blockers.append("FEED_NOT_OK")
    if ws_connected is False or effective_ws is False:
        blockers.append("WS_DISCONNECTED")
    if runtime_state in {"AUTH_BLOCKED", "LOGIN_REQUIRED", "TOKEN_INVALID"}:
        blockers.append("AUTH_REQUIRED")
    if runtime_state in _RESTART_REQUIRED_STATES or bool(payload.get("process_restart_required")):
        blockers.append("RESTART_REQUIRED")
    if runtime_state in _RECOVERY_BLOCKED_STATES or bool(payload.get("recovery_blocked")):
        blockers.append("RECOVERY_BLOCKED")
    if runtime_state in _RECOVERING_STATES or bool(payload.get("recovery_in_progress")):
        blockers.append("RECOVERING")
    if feed_truth_state == "DEAD" or feed_truth_reason_code == "FEED_UNHEALTHY":
        blockers.append("DEAD")
    if option_block_reason == "NO_LIVE_OPTION_FEED":
        blockers.append("NO_LIVE_OPTION_FEED")
    if any(str(value or "").strip().upper() == "NO_LIVE_OPTION_FEED" for value in dict(option_blockers_by_symbol).values()):
        blockers.append("NO_LIVE_OPTION_FEED")
    if any(
        any(str(item or "").strip().upper() == "NO_LIVE_OPTION_FEED" for item in (value or []))
        for value in dict(active_blockers_by_symbol).values()
    ):
        blockers.append("NO_LIVE_OPTION_FEED")
    if not underlying_tick_fresh:
        blockers.append("UNDERLYING_TICK_STALE")
    if not depth_fresh:
        blockers.append("DEPTH_STALE")
    if not option_ticks_verified:
        blockers.append("OPTION_TICKS_UNVERIFIED")
    warmup_active = bool(
        payload.get("recovery_in_progress")
        or runtime_state in _RECOVERING_STATES
        or runtime_state in {"VERIFYING", "WARMING_UP", "RESUBSCRIBING", "RECONNECTING"}
        or warmup_clean_cycles < warmup_required_clean_cycles
    )
    if warmup_active and warmup_clean_cycles < warmup_required_clean_cycles:
        blockers.append("WARMUP_INCOMPLETE")

    proof_ready = not blockers
    context = {
        "feed_ok": feed_ok,
        "ws_connected": ws_connected,
        "effective_ws_connected": effective_ws,
        "runtime_state": runtime_state or None,
        "feed_truth_state": feed_truth_state or None,
        "feed_truth_reason_code": feed_truth_reason_code or None,
        "option_feed_block_reason": option_block_reason or None,
        "underlying_tick_fresh": underlying_tick_fresh,
        "depth_fresh": depth_fresh,
        "option_ticks_verified": option_ticks_verified,
        "latest_ltp_age_sec": latest_ltp_age_sec,
        "latest_depth_age_sec": latest_depth_age_sec,
        "warmup_clean_cycles": warmup_clean_cycles,
        "warmup_required_clean_cycles": warmup_required_clean_cycles,
        "recovery_generation_id": recovery_generation_id,
        "last_recovery_generation_id": last_recovery_generation_id,
        "subscription_generation_id": subscription_generation_id,
        "last_subscription_generation_id": last_subscription_generation_id,
    }
    return proof_ready, tuple(dict.fromkeys(blockers)), context


def classify_feed_recovery_runtime(payload: dict[str, Any] | None) -> FeedRecoveryRuntimeDecision:
    """Classify feed recovery state without executing recovery."""

    if not isinstance(payload, dict):
        return FeedRecoveryRuntimeDecision(
            recovery_state="UNKNOWN",
            action_hint="inspect_runtime_payload",
            reason="invalid_payload",
            should_attempt_recovery=False,
            context={},
        )

    context = _base_context(payload)
    proof_ready, proof_blockers, proof_context = _full_feed_proof(payload)
    context.update(
        {
            "full_feed_proof_ready": proof_ready,
            "full_feed_proof_blockers": list(proof_blockers),
        }
    )
    context.update(proof_context)
    state, state_reason = _state_reason(payload)
    market_open = bool(payload.get("market_open", False))
    feed_ok = payload.get("feed_ok")
    effective_ws = payload.get("effective_ws_connected")
    ws_connected = payload.get("ws_connected")
    runtime_state = str(payload.get("runtime_state") or "").strip().upper()
    last_tick_age_sec = _safe_float(payload.get("last_tick_age_sec"))
    missing_option_tokens = _safe_int(payload.get("missing_option_tokens_count"))
    subscribed_option_tokens = _safe_int(payload.get("subscribed_option_tokens_count"))
    intended_tokens = _safe_int(payload.get("intended_tokens_count"))
    subscribed_tokens = _safe_int(payload.get("subscribed_tokens_count"))
    primary_option_blocker = context.get("primary_option_blocker")

    if not market_open:
        return FeedRecoveryRuntimeDecision(
            recovery_state="MARKET_CLOSED",
            action_hint="no_recovery_market_closed",
            reason="market_closed",
            should_attempt_recovery=False,
            context=context,
        )

    if runtime_state == "AUTH_BLOCKED":
        return FeedRecoveryRuntimeDecision(
            recovery_state="AUTH_BLOCKED",
            action_hint="manual_auth_required",
            reason="auth_blocked",
            should_attempt_recovery=False,
            context=context,
        )

    if feed_ok is True and effective_ws is not False and proof_ready:
        return FeedRecoveryRuntimeDecision(
            recovery_state="HEALTHY",
            action_hint="no_recovery_needed",
            reason="feed_ok",
            should_attempt_recovery=False,
            context=context,
        )

    if feed_ok is True and effective_ws is not False and not proof_ready:
        return FeedRecoveryRuntimeDecision(
            recovery_state="RECOVERY_PROOF_PENDING",
            action_hint="await_full_feed_proof",
            reason="feed_proof_pending",
            should_attempt_recovery=False,
            context=context,
        )

    if ws_connected is False or effective_ws is False or state_reason == "ws_disconnected":
        return FeedRecoveryRuntimeDecision(
            recovery_state="WS_DISCONNECTED",
            action_hint="full_restart_candidate",
            reason="ws_disconnected",
            should_attempt_recovery=True,
            force_full_restart=True,
            context=context,
        )

    if state_reason.startswith("no_ws_messages") or state == "DOWN":
        return FeedRecoveryRuntimeDecision(
            recovery_state="SILENT_FEED",
            action_hint="silent_reconnect_candidate",
            reason=state_reason or "no_ws_messages",
            should_attempt_recovery=True,
            context=context,
        )

    if intended_tokens > 0 and subscribed_tokens <= 0:
        return FeedRecoveryRuntimeDecision(
            recovery_state="NO_SUBSCRIPTIONS",
            action_hint="resubscribe_candidate",
            reason="no_subscribed_tokens",
            should_attempt_recovery=True,
            context=context,
        )

    if missing_option_tokens > 0 or (intended_tokens > 0 and subscribed_option_tokens <= 0):
        return FeedRecoveryRuntimeDecision(
            recovery_state="OPTION_SUBSCRIPTIONS_MISSING",
            action_hint="option_resubscribe_candidate",
            reason="option_subscriptions_missing",
            should_attempt_recovery=True,
            context=context,
        )

    if primary_option_blocker:
        return FeedRecoveryRuntimeDecision(
            recovery_state="OPTION_FEED_BLOCKED",
            action_hint="option_freshness_recovery_candidate",
            reason=str(primary_option_blocker).lower(),
            should_attempt_recovery=True,
            context=context,
        )

    if last_tick_age_sec is not None and last_tick_age_sec > 0:
        return FeedRecoveryRuntimeDecision(
            recovery_state="STALE_TICKS",
            action_hint="tick_stale_recovery_candidate",
            reason="last_tick_stale",
            should_attempt_recovery=True,
            context=context,
        )

    return FeedRecoveryRuntimeDecision(
        recovery_state="DEGRADED_UNKNOWN",
        action_hint="inspect_feed_runtime",
        reason="feed_unhealthy_unknown",
        should_attempt_recovery=False,
        context=context,
    )
