"""Pure websocket lifecycle shell helpers for feed handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


_TERMINAL_STOP_PHASES: frozenset[str] = frozenset({"STOPPING", "STOPPED", "AUTH_BLOCKED"})
_ACTIVE_PHASES: frozenset[str] = frozenset({"CONNECTING", "CONNECTED", "SUBSCRIBED", "RECOVERING"})


@dataclass(frozen=True)
class WsLifecycleState:
    """Read-only lifecycle state snapshot with no websocket side effects."""

    phase: str
    ws_connected: bool | None = None
    subscribed_token_count: int = 0
    intended_token_count: int = 0
    market_open: bool = False
    premarket: bool = False
    stop_requested: bool = False
    auth_required: bool = False
    reconnect_pending: bool = False
    last_error: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "phase": normalize_phase(self.phase),
            "ws_connected": self.ws_connected,
            "subscribed_token_count": int(self.subscribed_token_count),
            "intended_token_count": int(self.intended_token_count),
            "market_open": bool(self.market_open),
            "premarket": bool(self.premarket),
            "stop_requested": bool(self.stop_requested),
            "auth_required": bool(self.auth_required),
            "reconnect_pending": bool(self.reconnect_pending),
            "last_error": str(self.last_error or "")[:1000],
        }


@dataclass(frozen=True)
class WsLifecycleTransition:
    """Decision-only lifecycle transition with explicit effect flags."""

    event: str
    previous_phase: str
    next_phase: str
    action: str
    reason: str
    should_connect: bool = False
    should_subscribe: bool = False
    should_soft_resubscribe: bool = False
    should_restart: bool = False
    should_stop: bool = False
    should_mark_connected: bool = False
    should_mark_disconnected: bool = False
    should_record_error: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "event": normalize_event(self.event),
            "previous_phase": normalize_phase(self.previous_phase),
            "next_phase": normalize_phase(self.next_phase),
            "action": normalize_action(self.action),
            "reason": str(self.reason or ""),
            "should_connect": bool(self.should_connect),
            "should_subscribe": bool(self.should_subscribe),
            "should_soft_resubscribe": bool(self.should_soft_resubscribe),
            "should_restart": bool(self.should_restart),
            "should_stop": bool(self.should_stop),
            "should_mark_connected": bool(self.should_mark_connected),
            "should_mark_disconnected": bool(self.should_mark_disconnected),
            "should_record_error": bool(self.should_record_error),
            "is_order_action": False,
            "broker_api_called": False,
        }


def normalize_phase(value: Any) -> str:
    text = str(value or "UNKNOWN").strip().upper()
    return text or "UNKNOWN"


def normalize_event(value: Any) -> str:
    text = str(value or "UNKNOWN").strip().upper()
    return text or "UNKNOWN"


def normalize_action(value: Any) -> str:
    text = str(value or "NOOP").strip().upper()
    return text or "NOOP"


def positive_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def normalize_token_sample(values: Iterable[Any] | None, *, limit: int = 25) -> tuple[int, ...]:
    out: list[int] = []
    seen: set[int] = set()
    max_items = max(0, int(limit or 0))
    for raw in list(values or []):
        try:
            token = int(raw)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if max_items and len(out) >= max_items:
            break
    return tuple(out)


def is_terminal_stop_phase(phase: Any) -> bool:
    return normalize_phase(phase) in _TERMINAL_STOP_PHASES


def is_active_phase(phase: Any) -> bool:
    return normalize_phase(phase) in _ACTIVE_PHASES


def build_lifecycle_state(
    *,
    phase: Any,
    ws_connected: bool | None,
    subscribed_token_count: Any = 0,
    intended_token_count: Any = 0,
    market_open: bool = False,
    premarket: bool = False,
    stop_requested: bool = False,
    auth_required: bool = False,
    reconnect_pending: bool = False,
    last_error: Any = "",
) -> WsLifecycleState:
    return WsLifecycleState(
        phase=normalize_phase(phase),
        ws_connected=ws_connected,
        subscribed_token_count=positive_count(subscribed_token_count),
        intended_token_count=positive_count(intended_token_count),
        market_open=bool(market_open),
        premarket=bool(premarket),
        stop_requested=bool(stop_requested),
        auth_required=bool(auth_required),
        reconnect_pending=bool(reconnect_pending),
        last_error=str(last_error or "")[:1000],
    )


def derive_phase_from_runtime(
    *,
    market_open: bool,
    premarket: bool = False,
    auth_required: bool,
    stop_requested: bool,
    ws_connected: bool | None,
    subscribed_token_count: Any = 0,
    intended_token_count: Any = 0,
    reconnect_pending: bool = False,
) -> str:
    if bool(auth_required):
        return "AUTH_BLOCKED"
    if bool(stop_requested):
        return "STOPPING" if ws_connected else "STOPPED"
    if bool(premarket):
        return "PREMARKET"
    if not bool(market_open):
        return "MARKET_CLOSED"
    if bool(reconnect_pending):
        return "RECOVERING"
    if ws_connected is True:
        if positive_count(subscribed_token_count) > 0 and positive_count(subscribed_token_count) >= positive_count(intended_token_count):
            return "SUBSCRIBED"
        return "CONNECTED"
    if ws_connected is False:
        return "DISCONNECTED"
    return "STARTING"


def derive_transport_health(
    *,
    ws_connected: bool | None,
    reconnect_pending: bool = False,
    runtime_state: Any = None,
    reconnect_blocked_reason: Any = None,
    last_error: Any = None,
) -> dict[str, Any]:
    state_text = normalize_phase(runtime_state)
    blocked_reason = str(reconnect_blocked_reason or "").strip().lower()
    error_text = str(last_error or "").strip()
    if blocked_reason:
        return {
            "state": "BLOCKED",
            "reason": f"reconnect_blocked:{blocked_reason}",
            "healthy": False,
            "ws_connected": ws_connected,
            "reconnect_pending": bool(reconnect_pending),
            "runtime_state": state_text,
            "last_error": error_text,
        }
    if bool(reconnect_pending) or state_text in {"RECOVERING", "CONNECTING", "SUBSCRIBING"}:
        return {
            "state": "RECONNECTING",
            "reason": state_text.lower() if state_text in {"RECOVERING", "CONNECTING", "SUBSCRIBING"} else "reconnect_pending",
            "healthy": False,
            "ws_connected": ws_connected,
            "reconnect_pending": True,
            "runtime_state": state_text,
            "last_error": error_text,
        }
    if ws_connected is True:
        return {
            "state": "CONNECTED",
            "reason": "ws_connected",
            "healthy": True,
            "ws_connected": True,
            "reconnect_pending": bool(reconnect_pending),
            "runtime_state": state_text,
            "last_error": error_text,
        }
    if ws_connected is False:
        return {
            "state": "DISCONNECTED",
            "reason": "ws_disconnected",
            "healthy": False,
            "ws_connected": False,
            "reconnect_pending": bool(reconnect_pending),
            "runtime_state": state_text,
            "last_error": error_text,
        }
    return {
        "state": "UNKNOWN",
        "reason": "transport_state_unavailable",
        "healthy": False,
        "ws_connected": ws_connected,
        "reconnect_pending": bool(reconnect_pending),
        "runtime_state": state_text,
        "last_error": error_text,
    }


def transition_for_connect_request(state: WsLifecycleState) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    if state.auth_required:
        return WsLifecycleTransition("CONNECT_REQUEST", phase, "AUTH_BLOCKED", "BLOCK", "auth_required", should_record_error=True)
    if state.stop_requested:
        return WsLifecycleTransition("CONNECT_REQUEST", phase, "STOPPED", "BLOCK", "stop_requested", should_stop=True)
    if not state.market_open and not state.premarket:
        return WsLifecycleTransition("CONNECT_REQUEST", phase, "MARKET_CLOSED", "BLOCK", "market_closed")
    if state.ws_connected is True:
        return WsLifecycleTransition("CONNECT_REQUEST", phase, phase, "NOOP", "already_connected")
    if state.premarket:
        return WsLifecycleTransition("CONNECT_REQUEST", phase, "CONNECTING", "CONNECT", "premarket_observation_allowed", should_connect=True)
    return WsLifecycleTransition("CONNECT_REQUEST", phase, "CONNECTING", "CONNECT", "connect_allowed", should_connect=True)


def transition_for_connected(state: WsLifecycleState) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    if state.auth_required:
        return WsLifecycleTransition("CONNECTED", phase, "AUTH_BLOCKED", "BLOCK", "auth_required", should_record_error=True)
    if state.stop_requested:
        return WsLifecycleTransition("CONNECTED", phase, "STOPPING", "STOP", "stop_requested", should_stop=True)
    return WsLifecycleTransition(
        "CONNECTED",
        phase,
        "CONNECTED",
        "MARK_CONNECTED",
        "websocket_connected",
        should_mark_connected=True,
    )


def transition_for_subscribe_request(state: WsLifecycleState, *, requested_tokens: Iterable[Any] | None) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    requested = normalize_token_sample(requested_tokens, limit=1000000)
    if state.auth_required:
        return WsLifecycleTransition("SUBSCRIBE_REQUEST", phase, "AUTH_BLOCKED", "BLOCK", "auth_required", should_record_error=True)
    if state.stop_requested:
        return WsLifecycleTransition("SUBSCRIBE_REQUEST", phase, "STOPPING", "BLOCK", "stop_requested", should_stop=True)
    if state.ws_connected is not True:
        return WsLifecycleTransition("SUBSCRIBE_REQUEST", phase, "DISCONNECTED", "BLOCK", "ws_disconnected")
    if requested == ():
        return WsLifecycleTransition("SUBSCRIBE_REQUEST", phase, "CONNECTED", "BLOCK", "no_tokens")
    return WsLifecycleTransition(
        "SUBSCRIBE_REQUEST",
        phase,
        "SUBSCRIBING",
        "SUBSCRIBE",
        "tokens_available",
        should_subscribe=True,
    )


def transition_for_subscribed(state: WsLifecycleState, *, subscribed_token_count: Any) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    count = positive_count(subscribed_token_count)
    if count <= 0:
        return WsLifecycleTransition("SUBSCRIBED", phase, "CONNECTED", "BLOCK", "no_subscribed_tokens")
    return WsLifecycleTransition("SUBSCRIBED", phase, "SUBSCRIBED", "MARK_SUBSCRIBED", "subscription_confirmed")


def transition_for_disconnect(
    state: WsLifecycleState,
    *,
    reason: Any,
    restart_requested: bool = False,
    soft_resubscribe_requested: bool = False,
) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    if state.auth_required:
        return WsLifecycleTransition("DISCONNECT", phase, "AUTH_BLOCKED", "BLOCK", "auth_required", should_record_error=True)
    if state.stop_requested:
        return WsLifecycleTransition("DISCONNECT", phase, "STOPPED", "MARK_DISCONNECTED", "stop_requested", should_mark_disconnected=True)
    if bool(restart_requested):
        return WsLifecycleTransition(
            "DISCONNECT",
            phase,
            "RECOVERING",
            "RESTART",
            str(reason or "restart_requested"),
            should_restart=True,
            should_mark_disconnected=True,
        )
    if bool(soft_resubscribe_requested) and state.ws_connected is True:
        return WsLifecycleTransition(
            "DISCONNECT",
            phase,
            "CONNECTED",
            "SOFT_RESUBSCRIBE",
            str(reason or "soft_resubscribe_requested"),
            should_soft_resubscribe=True,
        )
    return WsLifecycleTransition(
        "DISCONNECT",
        phase,
        "DISCONNECTED",
        "MARK_DISCONNECTED",
        str(reason or "disconnected"),
        should_mark_disconnected=True,
    )


def transition_for_error(
    state: WsLifecycleState,
    *,
    reason: Any,
    auth_error: bool = False,
    restart_requested: bool = False,
) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    if bool(auth_error) or state.auth_required:
        return WsLifecycleTransition("ERROR", phase, "AUTH_BLOCKED", "BLOCK", "auth_error", should_record_error=True)
    if state.stop_requested:
        return WsLifecycleTransition("ERROR", phase, "STOPPING", "STOP", "stop_requested", should_stop=True)
    if bool(restart_requested):
        return WsLifecycleTransition(
            "ERROR",
            phase,
            "RECOVERING",
            "RESTART",
            str(reason or "error_restart"),
            should_restart=True,
            should_record_error=True,
        )
    return WsLifecycleTransition("ERROR", phase, phase, "RECORD_ERROR", str(reason or "error"), should_record_error=True)


def transition_for_stop_request(state: WsLifecycleState) -> WsLifecycleTransition:
    phase = normalize_phase(state.phase)
    next_phase = "STOPPING" if is_active_phase(phase) or state.ws_connected else "STOPPED"
    return WsLifecycleTransition("STOP_REQUEST", phase, next_phase, "STOP", "stop_requested", should_stop=True)


def apply_transition(state: WsLifecycleState, transition: WsLifecycleTransition) -> WsLifecycleState:
    next_phase = normalize_phase(transition.next_phase)
    ws_connected = state.ws_connected
    reconnect_pending = state.reconnect_pending
    last_error = state.last_error
    if transition.should_mark_connected:
        ws_connected = True
        reconnect_pending = False
    if transition.should_mark_disconnected or transition.should_restart:
        ws_connected = False
    if transition.should_restart:
        reconnect_pending = True
    if next_phase in {"CONNECTED", "SUBSCRIBED"}:
        reconnect_pending = False
    if transition.should_record_error:
        last_error = str(transition.reason or "")[:1000]
    if transition.should_stop:
        reconnect_pending = False
    return WsLifecycleState(
        phase=next_phase,
        ws_connected=ws_connected,
        subscribed_token_count=state.subscribed_token_count,
        intended_token_count=state.intended_token_count,
        market_open=state.market_open,
        stop_requested=bool(state.stop_requested or transition.should_stop),
        auth_required=bool(state.auth_required or next_phase == "AUTH_BLOCKED"),
        reconnect_pending=reconnect_pending,
        last_error=last_error,
    )


def build_lifecycle_evidence(
    *,
    state: WsLifecycleState,
    transition: WsLifecycleTransition,
    token_sample: Iterable[Any] | None = None,
) -> dict[str, Any]:
    return {
        "state": state.to_payload(),
        "transition": transition.to_payload(),
        "token_sample": list(normalize_token_sample(token_sample)),
        "is_order_action": False,
        "broker_api_called": False,
    }


__all__ = [
    "WsLifecycleState",
    "WsLifecycleTransition",
    "apply_transition",
    "build_lifecycle_evidence",
    "build_lifecycle_state",
    "derive_phase_from_runtime",
    "derive_transport_health",
    "is_active_phase",
    "is_terminal_stop_phase",
    "normalize_action",
    "normalize_event",
    "normalize_phase",
    "normalize_token_sample",
    "positive_count",
    "transition_for_connect_request",
    "transition_for_connected",
    "transition_for_disconnect",
    "transition_for_error",
    "transition_for_stop_request",
    "transition_for_subscribe_request",
    "transition_for_subscribed",
]
