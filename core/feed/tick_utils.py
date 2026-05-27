"""Pure tick helpers for feed ingestion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_TS_FIELDS: tuple[str, ...] = ("exchange_timestamp", "last_trade_time", "timestamp")


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


def tick_epoch(tick: Mapping[str, Any] | None, *, fallback_epoch: float | None = None) -> float | None:
    if not isinstance(tick, Mapping):
        return coerce_epoch(fallback_epoch)
    for field in _TS_FIELDS:
        epoch = coerce_epoch(tick.get(field))
        if epoch is not None:
            return epoch
    return coerce_epoch(fallback_epoch)


def best_price(levels: Sequence[Mapping[str, Any]] | None) -> float | None:
    try:
        if not levels:
            return None
        first_level = levels[0]
        if not isinstance(first_level, Mapping):
            return None
        return safe_float(first_level.get("price"))
    except Exception:
        return None


def depth_has_bid_ask(depth: Mapping[str, Any] | None) -> bool:
    if not isinstance(depth, Mapping):
        return False
    bid = best_price(depth.get("buy", []))
    ask = best_price(depth.get("sell", []))
    return bool(bid is not None and ask is not None and bid > 0 and ask > 0)


def initial_freshness_epoch(
    *,
    payload_epoch: float | None,
    receipt_epoch: float,
    use_receipt_time_for_options: bool,
    is_underlying_token: bool,
) -> float:
    if bool(use_receipt_time_for_options) and not bool(is_underlying_token):
        return float(receipt_epoch)
    return float(payload_epoch if payload_epoch is not None else receipt_epoch)


def normalized_tick_epoch(
    *,
    payload_epoch: float | None,
    receipt_epoch: float,
    previous_epoch: float | None = None,
    last_ws_tick_epoch: float | None = None,
    market_open_now: bool = False,
    max_payload_lag_sec: float = 2.0,
    use_receipt_time_for_options: bool = True,
    is_underlying_token: bool = False,
) -> float:
    previous = coerce_epoch(previous_epoch)
    if previous is None:
        previous = coerce_epoch(last_ws_tick_epoch)
        if previous is not None and previous <= 0.0:
            previous = None

    payload = coerce_epoch(payload_epoch)
    receipt = coerce_epoch(receipt_epoch)
    if receipt is None:
        return float(previous if previous is not None else 0.0)

    epoch = initial_freshness_epoch(
        payload_epoch=payload,
        receipt_epoch=receipt,
        use_receipt_time_for_options=use_receipt_time_for_options,
        is_underlying_token=is_underlying_token,
    )
    max_lag = safe_float(max_payload_lag_sec)
    if max_lag is None:
        max_lag = 2.0

    try:
        if payload is None:
            epoch = receipt
        elif bool(market_open_now) and previous is not None and (receipt - float(epoch)) > float(max_lag):
            epoch = receipt
    except Exception:
        epoch = receipt

    if previous is not None:
        epoch = max(float(epoch), float(previous))
    return float(epoch)
