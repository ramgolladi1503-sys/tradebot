from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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

    if feed_ok is True and effective_ws is not False:
        return FeedRecoveryRuntimeDecision(
            recovery_state="HEALTHY",
            action_hint="no_recovery_needed",
            reason="feed_ok",
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
