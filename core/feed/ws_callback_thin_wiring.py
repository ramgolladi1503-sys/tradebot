"""Thin callback-to-lifecycle adapters for feed websocket handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.feed.ws_lifecycle_shell import (
    WsLifecycleState,
    WsLifecycleTransition,
    apply_transition,
    build_lifecycle_evidence,
    build_lifecycle_state,
    transition_for_connected,
    transition_for_disconnect,
    transition_for_error,
    transition_for_subscribe_request,
)


@dataclass(frozen=True)
class WsCallbackLifecycleResult:
    """Pure callback lifecycle result with no broker or websocket side effects."""

    state: WsLifecycleState
    transition: WsLifecycleTransition
    next_state: WsLifecycleState
    evidence: dict[str, Any]
    runtime_state: str
    runtime_error: str
    snapshot_connected: bool | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "state": self.state.to_payload(),
            "transition": self.transition.to_payload(),
            "next_state": self.next_state.to_payload(),
            "evidence": dict(self.evidence),
            "runtime_state": self.runtime_state,
            "runtime_error": self.runtime_error,
            "snapshot_connected": self.snapshot_connected,
            "is_order_action": False,
            "broker_api_called": False,
        }


def callback_state_from_runtime(
    *,
    phase: Any,
    ws_connected: bool | None,
    market_open: bool,
    stop_requested: bool = False,
    auth_required: bool = False,
    reconnect_pending: bool = False,
    subscribed_token_count: Any = 0,
    intended_token_count: Any = 0,
    last_error: Any = "",
) -> WsLifecycleState:
    return build_lifecycle_state(
        phase=phase,
        ws_connected=ws_connected,
        market_open=bool(market_open),
        stop_requested=bool(stop_requested),
        auth_required=bool(auth_required),
        reconnect_pending=bool(reconnect_pending),
        subscribed_token_count=subscribed_token_count,
        intended_token_count=intended_token_count,
        last_error=last_error,
    )


def handle_connected_callback(
    *,
    state: WsLifecycleState,
    token_sample: Iterable[Any] | None = None,
) -> WsCallbackLifecycleResult:
    transition = transition_for_connected(state)
    next_state = apply_transition(state, transition)
    runtime_state = "RUNNING" if transition.should_mark_connected else transition.next_phase
    runtime_error = "" if transition.should_mark_connected else str(transition.reason or "")[:1000]
    return _result(
        state=state,
        transition=transition,
        next_state=next_state,
        token_sample=token_sample,
        runtime_state=runtime_state,
        runtime_error=runtime_error,
        snapshot_connected=transition.should_mark_connected,
    )


def handle_subscribe_callback(
    *,
    state: WsLifecycleState,
    requested_tokens: Iterable[Any] | None,
) -> WsCallbackLifecycleResult:
    transition = transition_for_subscribe_request(state, requested_tokens=requested_tokens)
    next_state = apply_transition(state, transition)
    runtime_state = "RUNNING" if transition.should_subscribe else "SUBSCRIBE_FAILED"
    runtime_error = "" if transition.should_subscribe else str(transition.reason or "")[:1000]
    return _result(
        state=state,
        transition=transition,
        next_state=next_state,
        token_sample=requested_tokens,
        runtime_state=runtime_state,
        runtime_error=runtime_error,
        snapshot_connected=state.ws_connected if transition.should_subscribe else False,
    )


def handle_error_callback(
    *,
    state: WsLifecycleState,
    reason: Any,
    auth_error: bool = False,
    restart_requested: bool = False,
    token_sample: Iterable[Any] | None = None,
) -> WsCallbackLifecycleResult:
    transition = transition_for_error(
        state,
        reason=reason,
        auth_error=bool(auth_error),
        restart_requested=bool(restart_requested),
    )
    next_state = apply_transition(state, transition)
    if transition.next_phase == "AUTH_BLOCKED":
        runtime_state = "AUTH_BLOCKED"
    elif transition.should_restart:
        runtime_state = "RECOVERING"
    else:
        runtime_state = "SUBSCRIBE_FAILED"
    return _result(
        state=state,
        transition=transition,
        next_state=next_state,
        token_sample=token_sample,
        runtime_state=runtime_state,
        runtime_error=str(reason or transition.reason or "")[:1000],
        snapshot_connected=False,
    )


def handle_close_callback(
    *,
    state: WsLifecycleState,
    reason: Any,
    restart_requested: bool = False,
    soft_resubscribe_requested: bool = False,
    token_sample: Iterable[Any] | None = None,
) -> WsCallbackLifecycleResult:
    transition = transition_for_disconnect(
        state,
        reason=reason,
        restart_requested=bool(restart_requested),
        soft_resubscribe_requested=bool(soft_resubscribe_requested),
    )
    next_state = apply_transition(state, transition)
    if transition.next_phase == "AUTH_BLOCKED":
        runtime_state = "AUTH_BLOCKED"
    elif transition.should_restart:
        runtime_state = "RECOVERING"
    elif transition.should_soft_resubscribe:
        runtime_state = "RUNNING"
    elif transition.next_phase == "STOPPED":
        runtime_state = "STOPPED"
    else:
        runtime_state = "SUBSCRIBE_FAILED"
    return _result(
        state=state,
        transition=transition,
        next_state=next_state,
        token_sample=token_sample,
        runtime_state=runtime_state,
        runtime_error=str(reason or transition.reason or "")[:1000],
        snapshot_connected=True if transition.should_soft_resubscribe else False,
    )


def _result(
    *,
    state: WsLifecycleState,
    transition: WsLifecycleTransition,
    next_state: WsLifecycleState,
    token_sample: Iterable[Any] | None,
    runtime_state: str,
    runtime_error: str,
    snapshot_connected: bool | None,
) -> WsCallbackLifecycleResult:
    evidence = build_lifecycle_evidence(state=state, transition=transition, token_sample=token_sample)
    return WsCallbackLifecycleResult(
        state=state,
        transition=transition,
        next_state=next_state,
        evidence=evidence,
        runtime_state=str(runtime_state or "UNKNOWN").strip().upper(),
        runtime_error=str(runtime_error or "")[:1000],
        snapshot_connected=snapshot_connected,
    )


__all__ = [
    "WsCallbackLifecycleResult",
    "callback_state_from_runtime",
    "handle_close_callback",
    "handle_connected_callback",
    "handle_error_callback",
    "handle_subscribe_callback",
]
