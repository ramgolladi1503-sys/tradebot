"""Pure market-close feed state classifier for HOTFIX/EDGE-79B."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

MARKET_CLOSE_FEED_STATE_SCHEMA_VERSION = 1
MARKET_CLOSE_FEED_STATE_SOURCE = "market_close_feed_state_classifier_v1"

WEBSOCKET_DISCONNECTED = "WEBSOCKET_DISCONNECTED"
LTP_STALE = "LTP_STALE"
OPTION_FEED_STALE = "OPTION_FEED_STALE"
CLOSE_WINDOW_TICK_SLOWDOWN = "CLOSE_WINDOW_TICK_SLOWDOWN"
CYCLE_LATENCY_STALE = "CYCLE_LATENCY_STALE"
MARKET_CLOSED = "MARKET_CLOSED"
FEED_STATE_HEALTHY = "FEED_STATE_HEALTHY"
FEED_STATE_UNKNOWN = "FEED_STATE_UNKNOWN"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class MarketCloseFeedStateDecision:
    state: str
    decision_gate_reason: str
    ws_connected: bool | None
    websocket_ok: bool | None
    ltp_age_sec: float | None
    option_feed_age_sec: float | None
    cycle_latency_sec: float | None
    seconds_to_close: float | None
    market_closed: bool
    close_window_active: bool
    max_ltp_age_sec: float
    max_option_feed_age_sec: float
    max_cycle_latency_sec: float
    close_window_sec: float
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = MARKET_CLOSE_FEED_STATE_SOURCE
    generated_epoch: float = field(default_factory=time.time)

    @property
    def feed_ok(self) -> bool:
        return self.state == FEED_STATE_HEALTHY and not self.blockers

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": MARKET_CLOSE_FEED_STATE_SCHEMA_VERSION,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "state": self.state,
            "feed_ok": self.feed_ok,
            "decision_gate_reason": self.decision_gate_reason,
            "ws_connected": self.ws_connected,
            "websocket_ok": self.websocket_ok,
            "ltp_age_sec": self.ltp_age_sec,
            "option_feed_age_sec": self.option_feed_age_sec,
            "cycle_latency_sec": self.cycle_latency_sec,
            "seconds_to_close": self.seconds_to_close,
            "market_closed": self.market_closed,
            "close_window_active": self.close_window_active,
            "max_ltp_age_sec": self.max_ltp_age_sec,
            "max_option_feed_age_sec": self.max_option_feed_age_sec,
            "max_cycle_latency_sec": self.max_cycle_latency_sec,
            "close_window_sec": self.close_window_sec,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload


def classify_market_close_feed_state(
    payload: Mapping[str, Any] | None,
    *,
    now_epoch: float | None = None,
    max_ltp_age_sec: float = 2.5,
    max_option_feed_age_sec: float = 3.0,
    max_cycle_latency_sec: float = 5.0,
    close_window_sec: float = 300.0,
    source: str = MARKET_CLOSE_FEED_STATE_SOURCE,
) -> MarketCloseFeedStateDecision:
    """Classify close-window feed state without reconnecting or mutating runtime."""

    snapshot = dict(payload or {}) if isinstance(payload, Mapping) else {}
    generated_epoch = float(time.time() if now_epoch is None else now_epoch)
    safe_max_ltp = max(0.0, float(max_ltp_age_sec))
    safe_max_option = max(0.0, float(max_option_feed_age_sec))
    safe_max_cycle = max(0.0, float(max_cycle_latency_sec))
    safe_close_window = max(0.0, float(close_window_sec))

    ws_connected = _bool_or_none(snapshot.get("ws_connected", snapshot.get("effective_ws_connected")))
    websocket_ok = _bool_or_none(snapshot.get("websocket_ok", snapshot.get("ws_ok")))
    if websocket_ok is None:
        websocket_ok = ws_connected

    ltp_age_sec = _first_float(snapshot, "ltp_age_sec", "last_tick_age_sec", "underlying_ltp_age_sec")
    option_age_sec = _first_float(snapshot, "option_feed_age_sec", "option_last_tick_age_sec", "last_option_tick_age_sec")
    cycle_latency_sec = _first_float(snapshot, "cycle_latency_sec", "cycle_age_sec", "last_cycle_age_sec")
    seconds_to_close = _first_float(snapshot, "seconds_to_close", "market_seconds_to_close")
    market_closed = bool(_bool_or_none(snapshot.get("market_closed")) is True or _state(snapshot.get("market_state")) == "CLOSED")
    close_window_active = bool(seconds_to_close is not None and 0.0 <= seconds_to_close <= safe_close_window)

    state, reason = _classify_state(
        market_closed=market_closed,
        ws_connected=ws_connected,
        websocket_ok=websocket_ok,
        ltp_age_sec=ltp_age_sec,
        option_age_sec=option_age_sec,
        cycle_latency_sec=cycle_latency_sec,
        close_window_active=close_window_active,
        max_ltp_age_sec=safe_max_ltp,
        max_option_feed_age_sec=safe_max_option,
        max_cycle_latency_sec=safe_max_cycle,
    )
    blockers = () if state == FEED_STATE_HEALTHY else (reason,)
    warnings = (CLOSE_WINDOW_TICK_SLOWDOWN,) if close_window_active and state in {LTP_STALE, OPTION_FEED_STALE} else ()
    return MarketCloseFeedStateDecision(
        state=state,
        decision_gate_reason=reason,
        ws_connected=ws_connected,
        websocket_ok=websocket_ok,
        ltp_age_sec=ltp_age_sec,
        option_feed_age_sec=option_age_sec,
        cycle_latency_sec=cycle_latency_sec,
        seconds_to_close=seconds_to_close,
        market_closed=market_closed,
        close_window_active=close_window_active,
        max_ltp_age_sec=safe_max_ltp,
        max_option_feed_age_sec=safe_max_option,
        max_cycle_latency_sec=safe_max_cycle,
        close_window_sec=safe_close_window,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "model": MARKET_CLOSE_FEED_STATE_SOURCE,
            "scope": "pure_market_close_feed_state_classifier_no_runtime_wiring",
            "websocket_disconnected_is_distinct_from_ltp_stale": True,
            "does_not_reconnect": True,
            "does_not_resubscribe": True,
            "does_not_touch_runtime": True,
        },
        source=source,
        generated_epoch=generated_epoch,
    )


def _classify_state(
    *,
    market_closed: bool,
    ws_connected: bool | None,
    websocket_ok: bool | None,
    ltp_age_sec: float | None,
    option_age_sec: float | None,
    cycle_latency_sec: float | None,
    close_window_active: bool,
    max_ltp_age_sec: float,
    max_option_feed_age_sec: float,
    max_cycle_latency_sec: float,
) -> tuple[str, str]:
    if market_closed:
        return MARKET_CLOSED, MARKET_CLOSED
    if ws_connected is False or websocket_ok is False:
        return WEBSOCKET_DISCONNECTED, WEBSOCKET_DISCONNECTED
    if cycle_latency_sec is not None and cycle_latency_sec > max_cycle_latency_sec:
        return CYCLE_LATENCY_STALE, CYCLE_LATENCY_STALE
    if ltp_age_sec is not None and ltp_age_sec > max_ltp_age_sec:
        if close_window_active:
            return CLOSE_WINDOW_TICK_SLOWDOWN, CLOSE_WINDOW_TICK_SLOWDOWN
        return LTP_STALE, LTP_STALE
    if option_age_sec is not None and option_age_sec > max_option_feed_age_sec:
        if close_window_active:
            return CLOSE_WINDOW_TICK_SLOWDOWN, CLOSE_WINDOW_TICK_SLOWDOWN
        return OPTION_FEED_STALE, OPTION_FEED_STALE
    if ws_connected is None and websocket_ok is None and ltp_age_sec is None and option_age_sec is None:
        return FEED_STATE_UNKNOWN, FEED_STATE_UNKNOWN
    return FEED_STATE_HEALTHY, "feed_state_healthy"


def _first_float(payload: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(payload.get(key))
        if value is not None:
            return max(0.0, value)
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "healthy", "connected"}:
        return True
    if text in {"0", "false", "no", "n", "down", "unhealthy", "degraded", "disconnected"}:
        return False
    return None


def _state(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ORDER_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "CLOSE_WINDOW_TICK_SLOWDOWN",
    "CYCLE_LATENCY_STALE",
    "FEED_STATE_HEALTHY",
    "FEED_STATE_UNKNOWN",
    "LTP_STALE",
    "MARKET_CLOSED",
    "MARKET_CLOSE_FEED_STATE_SCHEMA_VERSION",
    "MARKET_CLOSE_FEED_STATE_SOURCE",
    "OPTION_FEED_STALE",
    "WEBSOCKET_DISCONNECTED",
    "MarketCloseFeedStateDecision",
    "classify_market_close_feed_state",
]
