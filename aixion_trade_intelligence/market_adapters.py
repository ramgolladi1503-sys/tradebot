from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .contracts import CanonicalEvent, EventValidationError


def _parse_time(value: object, *, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        raw = float(value)
        if raw > 1_000_000_000_000:
            raw /= 1000.0
        parsed = datetime.fromtimestamp(raw, tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise EventValidationError(f"market_adapter_invalid_{name}") from exc
    else:
        raise EventValidationError(f"market_adapter_missing_{name}")
    if parsed.tzinfo is None:
        raise EventValidationError(f"market_adapter_naive_{name}")
    return parsed.astimezone(timezone.utc)


def _finite_or_none(value: object, *, name: str) -> float | None:
    if value is None or value == "":
        return None
    out = float(value)
    if not math.isfinite(out):
        raise EventValidationError(f"market_adapter_{name}_not_finite")
    return out


def _event_id(*, session_id: str, event_type: str, instrument_key: str, event_time: datetime, payload: Mapping[str, object]) -> str:
    explicit = str(payload.get("event_id") or "").strip()
    if explicit:
        return explicit
    identity = {"session_id": session_id, "event_type": event_type, "instrument_key": instrument_key, "event_time": event_time.isoformat(), "source_sequence": payload.get("source_sequence")}
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_depth(levels: object, *, side: str) -> list[dict[str, float | int | None]]:
    if levels is None:
        return []
    if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
        raise EventValidationError(f"market_adapter_{side}_depth_invalid")
    normalized: list[dict[str, float | int | None]] = []
    for index, row in enumerate(levels):
        if not isinstance(row, Mapping):
            raise EventValidationError(f"market_adapter_{side}_depth_row_invalid")
        price = _finite_or_none(row.get("price"), name=f"{side}_depth_price")
        quantity = _finite_or_none(row.get("quantity"), name=f"{side}_depth_quantity")
        orders = row.get("orders")
        orders_value = int(orders) if orders is not None else None
        if price is None or quantity is None or price <= 0 or quantity < 0:
            raise EventValidationError(f"market_adapter_{side}_depth_values_invalid")
        normalized.append({"level": index + 1, "price": price, "quantity": quantity, "orders": orders_value})
    prices = [float(row["price"]) for row in normalized]
    if side == "bid" and prices != sorted(prices, reverse=True):
        raise EventValidationError("market_adapter_bid_depth_not_descending")
    if side == "ask" and prices != sorted(prices):
        raise EventValidationError("market_adapter_ask_depth_not_ascending")
    return normalized


def market_tick_to_event(
    tick: Mapping[str, Any],
    *,
    session_id: str,
    run_id: str,
    receive_time: datetime,
    persist_time: datetime,
    producer_sequence: int,
    source_provider: str,
    source_component: str,
) -> CanonicalEvent:
    instrument_key = str(tick.get("instrument_key") or tick.get("instrument_id") or "").strip()
    if not instrument_key:
        raise EventValidationError("market_adapter_instrument_key_missing")
    event_time = _parse_time(tick.get("exchange_timestamp") or tick.get("event_time") or tick.get("timestamp"), name="event_time")
    available_time = _parse_time(tick.get("available_time") if tick.get("available_time") is not None else receive_time, name="available_time")
    source_time = _parse_time(tick.get("source_time") if tick.get("source_time") is not None else event_time, name="source_time")
    bid = _finite_or_none(tick.get("bid"), name="bid")
    ask = _finite_or_none(tick.get("ask"), name="ask")
    last = _finite_or_none(tick.get("last") if tick.get("last") is not None else tick.get("ltp"), name="last")
    if (bid is not None and bid <= 0) or (ask is not None and ask <= 0) or (last is not None and last <= 0):
        raise EventValidationError("market_adapter_price_nonpositive")
    if bid is not None and ask is not None and ask < bid:
        raise EventValidationError("market_adapter_crossed_quote")
    oi_raw = tick.get("open_interest") if tick.get("open_interest") is not None else tick.get("oi")
    iv_raw = tick.get("implied_volatility") if tick.get("implied_volatility") is not None else tick.get("iv")
    payload = {
        "last": last,
        "bid": bid,
        "ask": ask,
        "volume": _finite_or_none(tick.get("volume"), name="volume"),
        "open_interest": _finite_or_none(oi_raw, name="open_interest"),
        "implied_volatility": _finite_or_none(iv_raw, name="implied_volatility"),
        "delta": _finite_or_none(tick.get("delta"), name="delta"),
        "gamma": _finite_or_none(tick.get("gamma"), name="gamma"),
        "theta": _finite_or_none(tick.get("theta"), name="theta"),
        "vega": _finite_or_none(tick.get("vega"), name="vega"),
        "bid_depth": _normalize_depth(tick.get("bid_depth"), side="bid"),
        "ask_depth": _normalize_depth(tick.get("ask_depth"), side="ask"),
        "source_sequence": tick.get("source_sequence"),
        "raw_metadata": dict(tick.get("metadata") or {}),
    }
    quality = str(tick.get("data_quality_state") or "VALID").strip().upper()
    return CanonicalEvent(
        event_id=_event_id(session_id=session_id, event_type="MARKET_TICK", instrument_key=instrument_key, event_time=event_time, payload={**tick, "source_sequence": tick.get("source_sequence")}),
        event_type="MARKET_TICK",
        schema_version="1.0.0",
        session_id=session_id,
        run_id=run_id,
        cycle_id=str(tick.get("cycle_id") or ""),
        trace_id=str(tick.get("trace_id") or ""),
        event_time=event_time,
        source_time=source_time,
        receive_time=receive_time,
        available_time=available_time,
        parse_time=receive_time,
        persist_time=persist_time,
        source_provider=source_provider,
        source_component=source_component,
        authority_class=str(tick.get("authority_class") or "SOURCE_OBSERVED").strip().upper(),
        data_quality_state=quality,
        instrument_key=instrument_key,
        producer_sequence=producer_sequence,
        payload=payload,
    )


def option_chain_snapshot_to_events(
    snapshot: Mapping[str, Any],
    *,
    session_id: str,
    run_id: str,
    receive_time: datetime,
    persist_time: datetime,
    starting_sequence: int,
    source_provider: str,
    source_component: str,
) -> list[CanonicalEvent]:
    rows = snapshot.get("contracts")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise EventValidationError("option_chain_contracts_missing")
    events: list[CanonicalEvent] = []
    for offset, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EventValidationError("option_chain_contract_row_invalid")
        events.append(
            market_tick_to_event(
                {
                    **row,
                    "exchange_timestamp": row.get("exchange_timestamp") or snapshot.get("exchange_timestamp") or snapshot.get("event_time"),
                    "available_time": row.get("available_time") if row.get("available_time") is not None else snapshot.get("available_time") if snapshot.get("available_time") is not None else receive_time,
                    "source_time": row.get("source_time") or snapshot.get("source_time") or snapshot.get("event_time"),
                    "metadata": {**dict(snapshot.get("metadata") or {}), **dict(row.get("metadata") or {}), "snapshot_id": snapshot.get("snapshot_id"), "expiry": row.get("expiry"), "strike": row.get("strike"), "option_type": row.get("option_type")},
                },
                session_id=session_id,
                run_id=run_id,
                receive_time=receive_time,
                persist_time=persist_time,
                producer_sequence=starting_sequence + offset,
                source_provider=source_provider,
                source_component=source_component,
            )
        )
    return events
