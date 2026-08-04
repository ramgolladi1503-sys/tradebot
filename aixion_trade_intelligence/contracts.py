from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


class EventValidationError(ValueError):
    """Raised when a canonical intelligence event is unsafe or incomplete."""


_DECISION_EVENT_TYPES = {
    "STRATEGY_EVALUATED",
    "SIGNAL_GENERATED",
    "CANDIDATE_CREATED",
    "CANDIDATE_BLOCKED",
    "CANDIDATE_RANKED",
    "APPROVAL_REQUESTED",
    "APPROVAL_DECIDED",
}

_SOURCE_OBSERVATION_EVENT_TYPES = {
    "MARKET_TICK",
    "MARKET_SNAPSHOT",
    "ORDER_BOOK_SNAPSHOT",
    "OPTION_CHAIN_SNAPSHOT",
}


def _parse_utc(value: str | datetime, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise EventValidationError(f"invalid_{field_name}") from exc
    else:
        raise EventValidationError(f"missing_{field_name}")
    if parsed.tzinfo is None:
        raise EventValidationError(f"naive_{field_name}")
    return parsed.astimezone(timezone.utc)


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EventValidationError("payload_not_json_safe") from exc
    return json.loads(encoded)


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    event_type: str
    schema_version: str
    session_id: str
    run_id: str
    event_time: datetime
    receive_time: datetime
    available_time: datetime
    parse_time: datetime
    persist_time: datetime
    source_provider: str
    source_component: str
    authority_class: str
    data_quality_state: str
    payload: Mapping[str, Any]
    source_time: datetime | None = None
    cycle_id: str = ""
    trace_id: str = ""
    parent_event_ids: tuple[str, ...] = field(default_factory=tuple)
    instrument_key: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    candidate_id: str = ""
    producer_sequence: int | None = None

    def __post_init__(self) -> None:
        required_text = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "source_provider": self.source_provider,
            "source_component": self.source_component,
            "authority_class": self.authority_class,
            "data_quality_state": self.data_quality_state,
        }
        for name, value in required_text.items():
            if not str(value or "").strip():
                raise EventValidationError(f"missing_{name}")
        if self.producer_sequence is not None and self.producer_sequence < 0:
            raise EventValidationError("negative_producer_sequence")
        for parent in self.parent_event_ids:
            if not str(parent).strip():
                raise EventValidationError("empty_parent_event_id")
        event_type = str(self.event_type).strip().upper()
        event_time = _parse_utc(self.event_time, field_name="event_time")
        receive_time = _parse_utc(self.receive_time, field_name="receive_time")
        available_time = _parse_utc(self.available_time, field_name="available_time")
        parse_time = _parse_utc(self.parse_time, field_name="parse_time")
        persist_time = _parse_utc(self.persist_time, field_name="persist_time")
        source_time = _parse_utc(self.source_time, field_name="source_time") if self.source_time is not None else None

        if receive_time > parse_time or parse_time > persist_time:
            raise EventValidationError("invalid_processing_time_order")
        if event_time > persist_time:
            raise EventValidationError("event_after_persist_time")
        if available_time > persist_time:
            raise EventValidationError("available_after_persist_time")
        if event_type in _DECISION_EVENT_TYPES and available_time > event_time:
            raise EventValidationError("available_after_decision_time")
        if event_type in _SOURCE_OBSERVATION_EVENT_TYPES and available_time < event_time:
            raise EventValidationError("observation_available_before_event_time")

        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "receive_time", receive_time)
        object.__setattr__(self, "available_time", available_time)
        object.__setattr__(self, "parse_time", parse_time)
        object.__setattr__(self, "persist_time", persist_time)
        object.__setattr__(self, "source_time", source_time)
        object.__setattr__(self, "payload", _canonical_payload(self.payload))
        object.__setattr__(self, "parent_event_ids", tuple(self.parent_event_ids))

    @property
    def payload_hash(self) -> str:
        encoded = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        for name in ("event_time", "receive_time", "available_time", "parse_time", "persist_time", "source_time"):
            value = record[name]
            record[name] = value.isoformat() if value is not None else None
        record["parent_event_ids"] = list(self.parent_event_ids)
        record["payload_hash"] = self.payload_hash
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CanonicalEvent":
        expected_hash = str(record.get("payload_hash") or "")
        event = cls(
            event_id=str(record.get("event_id") or ""),
            event_type=str(record.get("event_type") or ""),
            schema_version=str(record.get("schema_version") or ""),
            session_id=str(record.get("session_id") or ""),
            run_id=str(record.get("run_id") or ""),
            event_time=record.get("event_time"),
            source_time=record.get("source_time"),
            receive_time=record.get("receive_time"),
            available_time=record.get("available_time"),
            parse_time=record.get("parse_time"),
            persist_time=record.get("persist_time"),
            source_provider=str(record.get("source_provider") or ""),
            source_component=str(record.get("source_component") or ""),
            authority_class=str(record.get("authority_class") or ""),
            data_quality_state=str(record.get("data_quality_state") or ""),
            payload=record.get("payload") if isinstance(record.get("payload"), Mapping) else {},
            cycle_id=str(record.get("cycle_id") or ""),
            trace_id=str(record.get("trace_id") or ""),
            parent_event_ids=tuple(record.get("parent_event_ids") or ()),
            instrument_key=str(record.get("instrument_key") or ""),
            strategy_id=str(record.get("strategy_id") or ""),
            strategy_version=str(record.get("strategy_version") or ""),
            candidate_id=str(record.get("candidate_id") or ""),
            producer_sequence=int(record["producer_sequence"]) if record.get("producer_sequence") is not None else None,
        )
        if expected_hash and expected_hash != event.payload_hash:
            raise EventValidationError("payload_hash_mismatch")
        return event
