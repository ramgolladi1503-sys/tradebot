"""Pure feed runtime snapshot payload builders."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.feed.ws_lifecycle_shell import derive_transport_health
from core.runtime_truth_integrity import build_truth_integrity_payload


@dataclass(frozen=True)
class FeedRuntimeSnapshotInputs:
    ts_epoch: float
    ws_connected: bool | None
    subscribed_tokens_count: int
    intended_tokens_count: int
    market_open: bool
    runtime_state: str | None = None
    last_error: str | None = None
    source: str | None = None
    subscribed_tokens_sample: Sequence[int] = field(default_factory=tuple)
    subscribed_tokens_count_by_symbol: Mapping[str, int] = field(default_factory=dict)
    missing_option_tokens_count: int | None = None
    missing_option_tokens_count_by_symbol: Mapping[str, int] = field(default_factory=dict)
    subscribed_option_tokens_count: int | None = None
    option_last_tick_age_by_symbol: Mapping[str, float | None] = field(default_factory=dict)
    option_last_tick_sample: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    option_tokens_resolved_count_by_symbol: Mapping[str, int] = field(default_factory=dict)
    option_tokens_subscribed_count_by_symbol: Mapping[str, int] = field(default_factory=dict)
    option_ticks_received_count_by_symbol: Mapping[str, int] = field(default_factory=dict)
    last_option_tick_ts_by_symbol: Mapping[str, float | None] = field(default_factory=dict)
    option_feed_block_reason_by_symbol: Mapping[str, str] = field(default_factory=dict)
    option_active_blockers_by_symbol: Mapping[str, Sequence[str]] = field(default_factory=dict)
    last_db_tick_epoch: float | None = None
    last_db_tick_age_sec: float | None = None
    last_ws_tick_epoch: float | None = None
    last_tick_age_sec: float | None = None
    last_depth_epoch: float | None = None
    last_depth_age_sec: float | None = None
    state_machine: Mapping[str, Any] = field(default_factory=dict)
    reconnect_pending: bool | None = None
    reconnect_blocked_reason: str | None = None
    restart_count_1h: int = 0
    stale_strikes: int = 0
    option_ticks_verified: bool | None = None
    verified_option_symbols: Sequence[str] = field(default_factory=tuple)
    missing_option_symbols: Sequence[str] = field(default_factory=tuple)
    warmup_clean_cycles: int | None = None
    warmup_required_clean_cycles: int | None = None


def coerce_epoch(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if hasattr(value, "timestamp"):
            epoch = float(value.timestamp())
        else:
            epoch = float(value)
        if epoch > 1e12:
            epoch = epoch / 1000.0
        return epoch
    except Exception:
        return None


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def normalized_runtime_state(value: Any, default: str = "UNKNOWN") -> str:
    text = str(value or default or "UNKNOWN").strip().upper()
    return text or "UNKNOWN"


def trimmed_error(value: Any, limit: int = 1000) -> str:
    return str(value or "")[: max(0, int(limit))]


def dict_copy(value: Mapping[Any, Any] | None) -> dict[Any, Any]:
    return dict(value or {})


def list_copy(value: Sequence[Any] | None) -> list[Any]:
    return list(value or [])


def derive_runtime_state_machine(
    *,
    market_open: bool,
    ws_connected: bool | None,
    last_tick_age_sec: float | None,
    live_tick_age_sec: float = 10.0,
) -> dict[str, str]:
    if not bool(market_open):
        return {"state": "MARKET_CLOSED", "reason": "market_closed"}
    if ws_connected is False:
        return {"state": "DOWN", "reason": "ws_disconnected"}
    if last_tick_age_sec is None:
        return {"state": "STARTING", "reason": "awaiting_first_tick"}
    try:
        if float(last_tick_age_sec) <= float(live_tick_age_sec):
            return {"state": "LIVE", "reason": "ticks_flowing"}
    except Exception:
        return {"state": "DOWN", "reason": "invalid_tick_age"}
    return {"state": "DOWN", "reason": "no_ws_messages"}


def build_feed_runtime_store_payload(inputs: FeedRuntimeSnapshotInputs) -> dict[str, Any]:
    transport_health = derive_transport_health(
        ws_connected=inputs.ws_connected,
        reconnect_pending=bool(inputs.reconnect_pending),
        runtime_state=inputs.runtime_state,
        reconnect_blocked_reason=inputs.reconnect_blocked_reason,
        last_error=inputs.last_error,
    )
    payload = {
        "ts_epoch": float(inputs.ts_epoch),
        "ws_connected": inputs.ws_connected,
        "subscribed_tokens_count": int(inputs.subscribed_tokens_count),
        "intended_tokens_count": int(inputs.intended_tokens_count),
        "subscribed_tokens_sample": list_copy(inputs.subscribed_tokens_sample)[:25],
        "subscribed_tokens_count_by_symbol": dict_copy(inputs.subscribed_tokens_count_by_symbol),
        "missing_option_tokens_count": int(inputs.missing_option_tokens_count or 0),
        "missing_option_tokens_count_by_symbol": dict_copy(inputs.missing_option_tokens_count_by_symbol),
        "subscribed_option_tokens_count": int(inputs.subscribed_option_tokens_count or 0),
        "option_last_tick_age_by_symbol": dict_copy(inputs.option_last_tick_age_by_symbol),
        "option_last_tick_sample": list_copy(inputs.option_last_tick_sample),
        "option_tokens_resolved_count_by_symbol": dict_copy(inputs.option_tokens_resolved_count_by_symbol),
        "option_tokens_subscribed_count_by_symbol": dict_copy(inputs.option_tokens_subscribed_count_by_symbol),
        "option_ticks_received_count_by_symbol": dict_copy(inputs.option_ticks_received_count_by_symbol),
        "last_option_tick_ts_by_symbol": dict_copy(inputs.last_option_tick_ts_by_symbol),
        "option_feed_block_reason_by_symbol": dict_copy(inputs.option_feed_block_reason_by_symbol),
        "option_active_blockers_by_symbol": dict_copy(inputs.option_active_blockers_by_symbol),
        "market_open": bool(inputs.market_open),
        "last_ws_tick_epoch": coerce_epoch(inputs.last_ws_tick_epoch),
        "last_tick_age_sec": safe_float(inputs.last_tick_age_sec),
        "last_depth_epoch": coerce_epoch(inputs.last_depth_epoch),
        "last_depth_age_sec": safe_float(inputs.last_depth_age_sec),
        "state_machine": dict_copy(inputs.state_machine),
        "transport_state": transport_health["state"],
        "transport_reason": transport_health["reason"],
        "transport_healthy": bool(transport_health["healthy"]),
        "transport": dict(transport_health),
        "source": str(inputs.source or ""),
        "runtime_state": normalized_runtime_state(inputs.runtime_state),
        "last_error": trimmed_error(inputs.last_error),
    }
    payload.update(
        build_truth_integrity_payload(
            source_payload=payload,
            transport_state=payload.get("transport_state"),
            feed_truth_state=payload.get("feed_truth_state"),
            reason_code=payload.get("feed_truth_reason_code"),
            heartbeat_epoch=inputs.ts_epoch,
        )
    )
    return payload


def build_feed_runtime_latest_payload(
    inputs: FeedRuntimeSnapshotInputs,
    *,
    derive_effective_ws_connected: Callable[[dict[str, Any]], bool | None] | None = None,
    derive_feed_ok: Callable[[dict[str, Any]], bool | None] | None = None,
    stamp_payload: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    transport_health = derive_transport_health(
        ws_connected=inputs.ws_connected,
        reconnect_pending=bool(inputs.reconnect_pending),
        runtime_state=inputs.runtime_state,
        reconnect_blocked_reason=inputs.reconnect_blocked_reason,
        last_error=inputs.last_error,
    )
    payload: dict[str, Any] = {
        "ts_epoch": float(inputs.ts_epoch),
        "ws_connected": inputs.ws_connected,
        "subscribed_tokens_count": int(inputs.subscribed_tokens_count),
        "intended_tokens_count": int(inputs.intended_tokens_count),
        "subscribed_tokens_count_by_symbol": dict_copy(inputs.subscribed_tokens_count_by_symbol),
        "missing_option_tokens_count": int(inputs.missing_option_tokens_count or 0),
        "missing_option_tokens_count_by_symbol": dict_copy(inputs.missing_option_tokens_count_by_symbol),
        "last_db_tick_epoch": coerce_epoch(inputs.last_db_tick_epoch),
        "last_db_tick_age_sec": safe_float(inputs.last_db_tick_age_sec),
        "last_ws_tick_epoch": coerce_epoch(inputs.last_ws_tick_epoch),
        "last_tick_age_sec": safe_float(inputs.last_tick_age_sec),
        "last_depth_epoch": coerce_epoch(inputs.last_depth_epoch),
        "last_depth_age_sec": safe_float(inputs.last_depth_age_sec),
        "market_open": bool(inputs.market_open),
        "state_machine": dict_copy(inputs.state_machine),
        "subscribed_option_tokens_count": int(inputs.subscribed_option_tokens_count or 0),
        "option_last_tick_age_by_symbol": dict_copy(inputs.option_last_tick_age_by_symbol),
        "option_last_tick_sample": list_copy(inputs.option_last_tick_sample),
        "option_tokens_resolved_count_by_symbol": dict_copy(inputs.option_tokens_resolved_count_by_symbol),
        "option_tokens_subscribed_count_by_symbol": dict_copy(inputs.option_tokens_subscribed_count_by_symbol),
        "option_ticks_received_count_by_symbol": dict_copy(inputs.option_ticks_received_count_by_symbol),
        "last_option_tick_ts_by_symbol": dict_copy(inputs.last_option_tick_ts_by_symbol),
        "option_feed_block_reason_by_symbol": dict_copy(inputs.option_feed_block_reason_by_symbol),
        "option_active_blockers_by_symbol": dict_copy(inputs.option_active_blockers_by_symbol),
        "restart_count_1h": int(inputs.restart_count_1h),
        "stale_strikes": int(inputs.stale_strikes),
        "runtime_state": normalized_runtime_state(inputs.runtime_state),
        "last_error": trimmed_error(inputs.last_error),
        "transport_state": transport_health["state"],
        "transport_reason": transport_health["reason"],
        "transport_healthy": bool(transport_health["healthy"]),
        "transport": dict(transport_health),
    }
    for key, value in (
        ("option_ticks_verified", inputs.option_ticks_verified),
        ("warmup_clean_cycles", inputs.warmup_clean_cycles),
        ("warmup_required_clean_cycles", inputs.warmup_required_clean_cycles),
    ):
        if value is not None:
            payload[key] = value
    if inputs.verified_option_symbols:
        payload["verified_option_symbols"] = list_copy(inputs.verified_option_symbols)
    if inputs.missing_option_symbols:
        payload["missing_option_symbols"] = list_copy(inputs.missing_option_symbols)
    if derive_effective_ws_connected is not None:
        payload["effective_ws_connected"] = derive_effective_ws_connected(dict(payload))
    if derive_feed_ok is not None:
        payload["feed_ok"] = derive_feed_ok(dict(payload))
    if stamp_payload is not None:
        stamped = stamp_payload(dict(payload))
        if isinstance(stamped, dict):
            payload = stamped
    payload.update(
        build_truth_integrity_payload(
            source_payload=payload,
            transport_state=payload.get("transport_state"),
            feed_truth_state=payload.get("feed_truth_state"),
            reason_code=payload.get("feed_truth_reason_code"),
            heartbeat_epoch=inputs.ts_epoch,
        )
    )
    return payload


__all__ = [
    "FeedRuntimeSnapshotInputs",
    "build_feed_runtime_latest_payload",
    "build_feed_runtime_store_payload",
    "coerce_epoch",
    "derive_runtime_state_machine",
    "normalized_runtime_state",
    "safe_float",
    "safe_int",
    "trimmed_error",
]
