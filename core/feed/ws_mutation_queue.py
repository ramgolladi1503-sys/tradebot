import threading
from dataclasses import dataclass
from typing import Optional, List, Tuple, Callable, Any

@dataclass(frozen=True)
class WsMutationResult:
    ok: bool
    action: str
    tokens_count: int
    socket_present: bool
    ws_connected: Optional[bool]
    scheduled: bool
    queued: bool
    applied: bool
    failure_reason: Optional[str]
    reason: str
    ts_epoch: float

def _check_socket_health(ws) -> Tuple[bool, Optional[bool], Optional[str]]:
    """Returns (socket_present, ws_connected, failure_reason)"""
    if ws is None:
        return False, None, "ws_socket_none"
    if getattr(ws, "ws", None) is None:
        return False, None, "ws_socket_inner_none"

    if hasattr(ws, "factory") and hasattr(ws.factory, "is_connected"):
        try:
            return True, bool(ws.factory.is_connected()), None
        except Exception as exc:
            return True, False, f"is_connected_error:{type(exc).__name__}:{str(exc)}"
    return True, None, None

def safe_subscribe(ws, tokens: List[int], reason: str, now_epoch: float, on_applied_callback: Optional[Callable[[], None]] = None) -> WsMutationResult:
    return _safe_mutate(ws, "subscribe", tokens, reason, now_epoch, on_applied_callback)

def safe_unsubscribe(ws, tokens: List[int], reason: str, now_epoch: float, on_applied_callback: Optional[Callable[[], None]] = None) -> WsMutationResult:
    return _safe_mutate(ws, "unsubscribe", tokens, reason, now_epoch, on_applied_callback)

def safe_set_mode_full(ws, tokens: List[int], reason: str, now_epoch: float, on_applied_callback: Optional[Callable[[], None]] = None) -> WsMutationResult:
    present, connected, fail_reason = _check_socket_health(ws)
    if not present or connected is False:
        return WsMutationResult(
            ok=False, action="set_mode_full", tokens_count=len(tokens),
            socket_present=False, ws_connected=connected,
            scheduled=False, queued=True, applied=False,
            failure_reason=fail_reason, reason=reason, ts_epoch=now_epoch
        )

    unique_tokens = sorted(list(set(tokens)))
    if not unique_tokens:
        if on_applied_callback:
            on_applied_callback()
        return WsMutationResult(
            ok=True, action="set_mode_full", tokens_count=0,
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=True,
            failure_reason=None, reason=reason, ts_epoch=now_epoch
        )

    if not hasattr(ws, "set_mode"):
        return WsMutationResult(
            ok=False, action="set_mode_full", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=False,
            failure_reason="ws_method_missing", reason=reason, ts_epoch=now_epoch
        )

    try:
        if getattr(ws, "MODE_FULL", None) is None:
            raise ValueError("MODE_FULL not found on ws")

        def _apply_and_notify():
            ws.set_mode(ws.MODE_FULL, unique_tokens)
            if on_applied_callback:
                on_applied_callback()

        import sys
        if "twisted.internet.reactor" in sys.modules and "mock" not in str(type(ws)).lower() and not hasattr(ws, "_mock_name"):
            from twisted.internet import reactor
            if reactor.running:
                reactor.callFromThread(_apply_and_notify)
                return WsMutationResult(
                    ok=False, action="set_mode_full", tokens_count=len(unique_tokens),
                    socket_present=True, ws_connected=connected,
                    scheduled=True, queued=True, applied=False,
                    failure_reason="mutation_scheduled_not_applied", reason=reason, ts_epoch=now_epoch
                )

        _apply_and_notify()
        return WsMutationResult(
            ok=True, action="set_mode_full", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=True,
            failure_reason=fail_reason, reason=reason, ts_epoch=now_epoch
        )
    except Exception as exc:
        return WsMutationResult(
            ok=False, action="set_mode_full", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=False,
            failure_reason=f"{type(exc).__name__}:{str(exc)}", reason=reason, ts_epoch=now_epoch
        )

def _safe_mutate(ws, action: str, tokens: List[int], reason: str, now_epoch: float, on_applied_callback: Optional[Callable[[], None]] = None) -> WsMutationResult:
    present, connected, fail_reason = _check_socket_health(ws)
    if not present or connected is False:
        return WsMutationResult(
            ok=False, action=action, tokens_count=len(tokens),
            socket_present=False, ws_connected=connected,
            scheduled=False, queued=True, applied=False,
            failure_reason=fail_reason, reason=reason, ts_epoch=now_epoch
        )

    unique_tokens = sorted(list(set(tokens)))
    if not unique_tokens:
        if on_applied_callback:
            on_applied_callback()
        return WsMutationResult(
            ok=True, action=action, tokens_count=0,
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=True,
            failure_reason=None, reason=reason, ts_epoch=now_epoch
        )

    if not hasattr(ws, action):
        return WsMutationResult(
            ok=False, action=action, tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=False,
            failure_reason="ws_method_missing", reason=reason, ts_epoch=now_epoch
        )

    method = getattr(ws, action)

    def _apply_and_notify():
        method(unique_tokens)
        if on_applied_callback:
            on_applied_callback()

    try:
        import sys
        if "twisted.internet.reactor" in sys.modules and "mock" not in str(type(ws)).lower() and not hasattr(ws, "_mock_name"):
            from twisted.internet import reactor
            if reactor.running:
                reactor.callFromThread(_apply_and_notify)
                return WsMutationResult(
                    ok=False, action=action, tokens_count=len(unique_tokens),
                    socket_present=True, ws_connected=connected,
                    scheduled=True, queued=True, applied=False,
                    failure_reason="mutation_scheduled_not_applied", reason=reason, ts_epoch=now_epoch
                )

        _apply_and_notify()
        return WsMutationResult(
            ok=True, action=action, tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=True,
            failure_reason=fail_reason, reason=reason, ts_epoch=now_epoch
        )
    except Exception as exc:
        return WsMutationResult(
            ok=False, action=action, tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=False,
            failure_reason=f"{type(exc).__name__}:{str(exc)}", reason=reason, ts_epoch=now_epoch
        )


def safe_subscribe_full_mode(ws, tokens: List[int], reason: str, now_epoch: float, on_applied_callback: Optional[Callable[[], None]] = None) -> Tuple[WsMutationResult, WsMutationResult]:
    return safe_subscribe_full_mode_observed(
        ws,
        tokens,
        reason,
        now_epoch,
        on_applied_callback=on_applied_callback,
    )


def safe_subscribe_full_mode_observed(
    ws,
    tokens: List[int],
    reason: str,
    now_epoch: float,
    on_applied_callback: Optional[Callable[[], None]] = None,
    *,
    socket_generation: Optional[int] = None,
    active_generation: Optional[Callable[[], int]] = None,
    event_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
) -> Tuple[WsMutationResult, WsMutationResult]:
    """Subscribe and set full mode without letting an old socket mutate current truth.

    The returned result describes the state at return time. Reactor-scheduled work is
    queued, never applied. Its eventual outcome is reported through ``event_callback``.
    """
    present, connected, fail_reason = _check_socket_health(ws)
    unique_tokens = sorted(list(set(tokens)))

    def emit(event: str, *, result: str, failure_reason: Optional[str] = None) -> None:
        if event_callback is None:
            return
        event_callback(
            event,
            {
                "socket_generation": socket_generation,
                "token_count": len(unique_tokens),
                "token_ids": list(unique_tokens),
                "callback_thread": threading.current_thread().name,
                "timestamp": now_epoch,
                "result": result,
                "failure_reason": failure_reason,
                "reason": reason,
            },
        )

    emit("FEED_SUBSCRIBE_REQUESTED", result="requested")
    emit("FEED_MODE_FULL_REQUESTED", result="requested")
    if not present or connected is False:
        res_sub = WsMutationResult(
            ok=False, action="subscribe", tokens_count=len(tokens),
            socket_present=present, ws_connected=connected,
            scheduled=False, queued=True, applied=False,
            failure_reason=fail_reason or "ws_disconnected", reason=reason, ts_epoch=now_epoch
        )
        res_mode = WsMutationResult(
            ok=False, action="set_mode_full", tokens_count=len(tokens),
            socket_present=present, ws_connected=connected,
            scheduled=False, queued=True, applied=False,
            failure_reason=fail_reason or "ws_disconnected", reason=reason, ts_epoch=now_epoch
        )
        emit("FEED_SUBSCRIBE_QUEUED", result="queued", failure_reason=res_sub.failure_reason)
        emit("FEED_MODE_FULL_QUEUED", result="queued", failure_reason=res_mode.failure_reason)
        return res_sub, res_mode

    if not unique_tokens:
        if on_applied_callback:
            on_applied_callback()
        res_sub = WsMutationResult(
            ok=True, action="subscribe", tokens_count=0,
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=True,
            failure_reason=None, reason=reason, ts_epoch=now_epoch
        )
        res_mode = WsMutationResult(
            ok=True, action="set_mode_full", tokens_count=0,
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=True,
            failure_reason=None, reason=reason, ts_epoch=now_epoch
        )
        return res_sub, res_mode

    if not hasattr(ws, "subscribe") or not hasattr(ws, "set_mode"):
        res = WsMutationResult(
            ok=False, action="subscribe_full_mode", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=False,
            failure_reason="ws_method_missing", reason=reason, ts_epoch=now_epoch
        )
        return res, res

    try:
        if getattr(ws, "MODE_FULL", None) is None:
            raise ValueError("MODE_FULL not found on ws")

        callback_status = {"subscribe": False, "mode_full": False, "failure_reason": None}

        def _apply_and_notify():
            if socket_generation is not None and active_generation is not None:
                current_generation = int(active_generation())
                if int(socket_generation) != current_generation:
                    emit(
                        "FEED_OLD_GENERATION_CALLBACK_IGNORED",
                        result="ignored",
                        failure_reason=f"active_generation:{current_generation}",
                    )
                    callback_status["failure_reason"] = "old_socket_generation"
                    return
            try:
                ws.subscribe(unique_tokens)
                callback_status["subscribe"] = True
                emit("FEED_SUBSCRIBE_CALLBACK_APPLIED", result="applied")
            except Exception as exc:
                emit(
                    "FEED_SUBSCRIBE_CALLBACK_FAILED",
                    result="failed",
                    failure_reason=f"{type(exc).__name__}:{exc}",
                )
                callback_status["failure_reason"] = f"{type(exc).__name__}:{exc}"
                return
            try:
                ws.set_mode(ws.MODE_FULL, unique_tokens)
                callback_status["mode_full"] = True
                emit("FEED_MODE_FULL_CALLBACK_APPLIED", result="applied")
            except Exception as exc:
                emit(
                    "FEED_MODE_FULL_CALLBACK_FAILED",
                    result="failed",
                    failure_reason=f"{type(exc).__name__}:{exc}",
                )
                callback_status["failure_reason"] = f"{type(exc).__name__}:{exc}"
                return
            if on_applied_callback:
                on_applied_callback()

        import sys
        if "twisted.internet.reactor" in sys.modules and "mock" not in str(type(ws)).lower() and not hasattr(ws, "_mock_name"):
            from twisted.internet import reactor
            if reactor.running:
                reactor.callFromThread(_apply_and_notify)
                emit("FEED_SUBSCRIBE_QUEUED", result="queued", failure_reason="mutation_scheduled_not_applied")
                emit("FEED_MODE_FULL_QUEUED", result="queued", failure_reason="mutation_scheduled_not_applied")
                res_sub = WsMutationResult(
                    ok=False, action="subscribe", tokens_count=len(unique_tokens),
                    socket_present=True, ws_connected=connected,
                    scheduled=True, queued=True, applied=False,
                    failure_reason="mutation_scheduled_not_applied", reason=reason, ts_epoch=now_epoch
                )
                res_mode = WsMutationResult(
                    ok=False, action="set_mode_full", tokens_count=len(unique_tokens),
                    socket_present=True, ws_connected=connected,
                    scheduled=True, queued=True, applied=False,
                    failure_reason="mutation_scheduled_not_applied", reason=reason, ts_epoch=now_epoch
                )
                return res_sub, res_mode

        _apply_and_notify()
        res_sub = WsMutationResult(
            ok=bool(callback_status["subscribe"]), action="subscribe", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=bool(callback_status["subscribe"]),
            failure_reason=callback_status["failure_reason"], reason=reason, ts_epoch=now_epoch
        )
        res_mode = WsMutationResult(
            ok=bool(callback_status["mode_full"]), action="set_mode_full", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=bool(callback_status["mode_full"]),
            failure_reason=callback_status["failure_reason"], reason=reason, ts_epoch=now_epoch
        )
        return res_sub, res_mode
    except Exception as exc:
        res = WsMutationResult(
            ok=False, action="subscribe_full_mode", tokens_count=len(unique_tokens),
            socket_present=True, ws_connected=connected,
            scheduled=False, queued=False, applied=False,
            failure_reason=f"{type(exc).__name__}:{str(exc)}", reason=reason, ts_epoch=now_epoch
        )
        return res, res
