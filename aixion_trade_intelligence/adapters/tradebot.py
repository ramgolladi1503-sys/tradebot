from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import uuid

from ..contracts import CanonicalEvent, parse_timestamp


class TradeBotAdapterError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _timestamp(raw: Mapping[str, Any], *keys: str, fallback: datetime | None = None) -> datetime:
    for key in keys:
        value = raw.get(key)
        if value:
            return parse_timestamp(value, field_name=key)
    if fallback is not None:
        return fallback
    raise TradeBotAdapterError(f"missing timestamp; checked {keys}")


def adapt_tradebot_record(
    raw: Mapping[str, Any],
    *,
    event_type: str,
    session_id: str,
    source_component: str,
    producer_id: str,
    producer_sequence: int,
    now: datetime | None = None,
) -> CanonicalEvent:
    """Convert an existing TradeBot record into a canonical event.

    The adapter copies source facts and does not infer prices, freshness, status,
    option identity, or execution permission. Callers must supply the event type
    and session identity from the authoritative runtime owner.
    """

    if not session_id:
        raise TradeBotAdapterError("session_id is required")
    observed_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    event_time = _timestamp(raw, "event_time", "timestamp", "ts", fallback=observed_now)
    source_time = None
    for key in ("source_time", "exchange_timestamp", "exchange_ts"):
        if raw.get(key):
            source_time = parse_timestamp(raw[key], field_name=key)
            break
    receive_time = _timestamp(raw, "receive_time", "received_at", fallback=observed_now)
    available_time = _timestamp(raw, "available_time", fallback=max(event_time, receive_time))
    parse_time = _timestamp(raw, "parse_time", fallback=max(receive_time, available_time))
    persist_time = _timestamp(raw, "persist_time", fallback=max(parse_time, observed_now))

    event_id = _text(raw.get("event_id")) or str(uuid.uuid4())
    payload = dict(raw.get("payload")) if isinstance(raw.get("payload"), Mapping) else dict(raw)
    for key in (
        "event_id",
        "event_type",
        "schema_version",
        "session_id",
        "source_component",
        "producer_id",
        "producer_sequence",
        "event_time",
        "timestamp",
        "ts",
        "source_time",
        "exchange_timestamp",
        "exchange_ts",
        "receive_time",
        "received_at",
        "available_time",
        "parse_time",
        "persist_time",
    ):
        payload.pop(key, None)

    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        session_id=session_id,
        run_id=_text(raw.get("run_id")),
        cycle_id=_text(raw.get("cycle_id")),
        trace_id=_text(raw.get("trace_id")),
        parent_event_ids=tuple(raw.get("parent_event_ids") or ()),
        producer_id=producer_id,
        producer_sequence=producer_sequence,
        source_component=source_component,
        event_time=event_time,
        source_time=source_time,
        receive_time=receive_time,
        available_time=available_time,
        parse_time=parse_time,
        persist_time=persist_time,
        instrument_key=_text(raw.get("instrument_key")),
        underlying=_text(raw.get("underlying")),
        strategy_id=_text(raw.get("strategy_id") or raw.get("strategy_name")),
        strategy_version=_text(raw.get("strategy_version")),
        model_id=_text(raw.get("model_id")),
        model_version=_text(raw.get("model_version")),
        candidate_id=_text(raw.get("candidate_id") or raw.get("trade_id")),
        order_id=_text(raw.get("order_id")),
        position_id=_text(raw.get("position_id")),
        source_provider=_text(raw.get("source_provider") or raw.get("provider")),
        data_quality_state=_text(raw.get("data_quality_state")) or "OBSERVED",
        authority_class=_text(raw.get("authority_class")) or "SOURCE_OBSERVED",
        payload=payload,
    )
