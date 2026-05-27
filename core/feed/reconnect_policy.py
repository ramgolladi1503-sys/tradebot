"""Pure reconnect decision helpers for feed websocket handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_FATAL_WS_CODES: frozenset[int] = frozenset({1006, 1011, 1012})
_DEFAULT_COOLDOWN_BYPASS_CODES: frozenset[int] = frozenset({1006, 1011, 1012})
_DEFAULT_COOLDOWN_BYPASS_MARKERS: tuple[str, ...] = (
    "connection closed",
    "connection lost",
    "opening handshake",
)


@dataclass(frozen=True)
class ReconnectDecision:
    """Decision-only reconnect outcome with no side effects."""

    action: str
    reason: str
    should_restart: bool = False
    should_soft_resubscribe: bool = False
    should_suppress_restart: bool = False
    ignore_cooldown: bool = False
    force_full_restart: bool = False
    stale_strikes: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "reason": self.reason,
            "should_restart": bool(self.should_restart),
            "should_soft_resubscribe": bool(self.should_soft_resubscribe),
            "should_suppress_restart": bool(self.should_suppress_restart),
            "ignore_cooldown": bool(self.ignore_cooldown),
            "force_full_restart": bool(self.force_full_restart),
        }
        if self.stale_strikes is not None:
            payload["stale_strikes"] = int(self.stale_strikes)
        return payload


def normalize_ws_code(code: Any) -> int | None:
    try:
        if code is None:
            return None
        return int(code)
    except Exception:
        return None


def _reason_text(reason_text: Any) -> str:
    return str(reason_text or "")


def _reason_lower(reason_text: Any) -> str:
    return _reason_text(reason_text).lower()


def is_fatal_ws_fault(code: Any, reason_text: Any) -> bool:
    code_int = normalize_ws_code(code)
    reason_lower = _reason_lower(reason_text)
    if code_int in _FATAL_WS_CODES:
        return True
    return bool("connection" in reason_lower and "closed" in reason_lower)


def is_opening_handshake_error(code: Any, reason_text: Any) -> bool:
    return bool(normalize_ws_code(code) == 1006 and "opening handshake" in _reason_lower(reason_text))


def should_ignore_restart_cooldown_for_ws_fault(
    *,
    code: Any,
    reason_text: Any,
    bypass_codes: frozenset[int] | set[int] | tuple[int, ...] | list[int] | None = None,
    bypass_reason_markers: tuple[str, ...] | list[str] | None = None,
) -> bool:
    code_int = normalize_ws_code(code)
    codes = set(int(c) for c in (bypass_codes or _DEFAULT_COOLDOWN_BYPASS_CODES))
    if code_int is not None and code_int in codes:
        return True
    reason_lower = _reason_lower(reason_text)
    for marker in tuple(bypass_reason_markers or _DEFAULT_COOLDOWN_BYPASS_MARKERS):
        marker_text = str(marker or "").strip().lower()
        if marker_text and marker_text in reason_lower:
            return True
    return False


def evaluate_soft_resubscribe_policy(
    *,
    reason: Any,
    ws_connected: bool | None,
    last_ws_tick_epoch: float | None,
    now_epoch: float,
    max_tick_age_sec: float = 2.0,
    hard_block_markers: tuple[str, ...] | list[str] | None = None,
) -> ReconnectDecision:
    reason_lower = _reason_lower(reason)
    for marker in tuple(hard_block_markers or ()):
        marker_text = str(marker or "").strip().lower()
        if marker_text and marker_text in reason_lower:
            return ReconnectDecision(action="SKIP", reason=f"hard_reason_marker:{marker_text}")
    if ws_connected is not True:
        return ReconnectDecision(action="SKIP", reason="ws_disconnected")
    try:
        last_tick = float(last_ws_tick_epoch or 0.0)
    except Exception:
        last_tick = 0.0
    if last_tick <= 0.0:
        return ReconnectDecision(action="SKIP", reason="no_recent_ws_tick")
    try:
        tick_age_sec = max(0.0, float(now_epoch) - last_tick)
    except Exception:
        return ReconnectDecision(action="SKIP", reason="invalid_time_input")
    try:
        max_age = float(max_tick_age_sec)
    except Exception:
        max_age = 2.0
    if tick_age_sec > max_age:
        return ReconnectDecision(action="SKIP", reason=f"ws_tick_stale:{tick_age_sec:.2f}s")
    return ReconnectDecision(action="SOFT_RESUBSCRIBE", reason="eligible", should_soft_resubscribe=True)


def evaluate_watchdog_stale_tick_policy(
    *,
    market_open: bool,
    db_tick_age_sec: float | None,
    ws_tick_age_sec: float | None,
    previous_stale_strikes: int,
    stale_restart_sec: float,
    reset_sec: float = 2.0,
    strikes_to_restart: int = 2,
) -> ReconnectDecision:
    strikes = max(0, int(previous_stale_strikes or 0))
    if not bool(market_open):
        return ReconnectDecision(action="RESET_STALE", reason="market_closed", stale_strikes=0)
    try:
        reset_threshold = float(reset_sec)
    except Exception:
        reset_threshold = 2.0
    if ws_tick_age_sec is not None and float(ws_tick_age_sec) <= reset_threshold:
        return ReconnectDecision(action="RESET_STALE", reason="ws_ticks_flowing", stale_strikes=0)
    if db_tick_age_sec is not None:
        try:
            stale_threshold = float(stale_restart_sec)
        except Exception:
            stale_threshold = 0.0
        if float(db_tick_age_sec) > stale_threshold:
            strikes += 1
            required = max(1, int(strikes_to_restart or 1))
            if strikes >= required:
                return ReconnectDecision(
                    action="RESTART",
                    reason="db_tick_stale_restart_threshold",
                    should_restart=True,
                    stale_strikes=strikes,
                )
            return ReconnectDecision(action="MARK_STALE", reason="db_tick_stale", stale_strikes=strikes)
        if float(db_tick_age_sec) <= reset_threshold:
            return ReconnectDecision(action="RESET_STALE", reason="db_ticks_recovered", stale_strikes=0)
    return ReconnectDecision(action="NOOP", reason="insufficient_tick_age_evidence", stale_strikes=strikes)


def evaluate_ws_error_reconnect_policy(
    *,
    code: Any,
    reason_text: Any,
    is_auth_error: bool,
    market_open: bool,
    stop_requested: bool,
    watchdog_stop_set: bool,
    use_internal_reconnect: bool,
    handshake_soft_reset_used: bool,
) -> ReconnectDecision:
    if bool(is_auth_error):
        return ReconnectDecision(action="AUTH_BLOCKED", reason="auth_error", should_suppress_restart=True)
    if is_opening_handshake_error(code, reason_text):
        if not bool(handshake_soft_reset_used):
            return ReconnectDecision(
                action="HANDSHAKE_SOFT_RESET",
                reason="opening_handshake_error",
                should_soft_resubscribe=True,
                should_suppress_restart=True,
            )
        return ReconnectDecision(action="SUPPRESS_RESTART", reason="opening_handshake_error", should_suppress_restart=True)
    if not is_fatal_ws_fault(code, reason_text):
        return ReconnectDecision(action="NOOP", reason="non_fatal_ws_error")
    if not bool(market_open):
        return ReconnectDecision(action="NOOP", reason="market_closed")
    if bool(stop_requested) or bool(watchdog_stop_set):
        return ReconnectDecision(action="NOOP", reason="stop_requested")
    ignore_cooldown = should_ignore_restart_cooldown_for_ws_fault(code=code, reason_text=reason_text)
    if bool(use_internal_reconnect):
        return ReconnectDecision(
            action="SCHEDULE_FULL_RESTART",
            reason="fatal_ws_error_internal_reconnect",
            should_restart=True,
            ignore_cooldown=ignore_cooldown,
            force_full_restart=True,
        )
    return ReconnectDecision(
        action="RESTART",
        reason="fatal_ws_error",
        should_restart=True,
        ignore_cooldown=ignore_cooldown,
    )


def evaluate_ws_close_reconnect_policy(
    *,
    code: Any,
    reason_text: Any,
    auth_required_latch: bool,
    stop_requested: bool,
    watchdog_stop_set: bool,
    market_open: bool,
    use_internal_reconnect: bool,
) -> ReconnectDecision:
    if bool(auth_required_latch):
        return ReconnectDecision(action="AUTH_BLOCKED", reason="auth_required_latch", should_suppress_restart=True)
    if bool(stop_requested) or bool(watchdog_stop_set):
        return ReconnectDecision(action="STOPPED", reason="stop_requested", should_suppress_restart=True)
    if not bool(market_open):
        return ReconnectDecision(action="NOOP", reason="market_closed")
    fatal = is_fatal_ws_fault(code, reason_text)
    ignore_cooldown = should_ignore_restart_cooldown_for_ws_fault(code=code, reason_text=reason_text)
    if bool(use_internal_reconnect):
        if fatal:
            return ReconnectDecision(
                action="SCHEDULE_FULL_RESTART",
                reason="fatal_ws_close_internal_reconnect",
                should_restart=True,
                ignore_cooldown=ignore_cooldown,
                force_full_restart=True,
            )
        return ReconnectDecision(
            action="SOFT_RESUBSCRIBE",
            reason="non_fatal_ws_close_internal_reconnect",
            should_soft_resubscribe=True,
        )
    return ReconnectDecision(action="RESTART", reason="ws_close", should_restart=True, ignore_cooldown=ignore_cooldown)


__all__ = [
    "ReconnectDecision",
    "evaluate_soft_resubscribe_policy",
    "evaluate_watchdog_stale_tick_policy",
    "evaluate_ws_close_reconnect_policy",
    "evaluate_ws_error_reconnect_policy",
    "is_fatal_ws_fault",
    "is_opening_handshake_error",
    "normalize_ws_code",
    "should_ignore_restart_cooldown_for_ws_fault",
]
