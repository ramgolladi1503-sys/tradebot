from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping
import json
import math
import uuid


SUPPORTED_SCHEMA_MAJOR = 1


class EventValidationError(ValueError):
    """Raised when an intelligence event violates the canonical contract."""


def parse_timestamp(value: str | datetime, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise EventValidationError(f"{field_name}: invalid timestamp {value!r}") from exc
    else:
        raise EventValidationError(f"{field_name}: expected datetime or ISO-8601 string")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise EventValidationError(f"{field_name}: timezone is required")
    return dt.astimezone(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _validate_json_value(value: Any, path: str = "payload") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventValidationError(f"{path}: non-finite float is not allowed")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise EventValidationError(f"{path}: mapping keys must be non-empty strings")
            _validate_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            _validate_json_value(child, f"{path}[{idx}]")
        return
    raise EventValidationError(f"{path}: unsupported JSON value {type(value).__name__}")


def _schema_major(schema_version: str) -> int:
    try:
        return int(schema_version.split(".", 1)[0])
    except (ValueError, AttributeError) as exc:
        raise EventValidationError("schema_version must be semantic-like, for example 1.0") from exc


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    event_type: str
    session_id: str
    source_component: str
    event_time: datetime
    receive_time: datetime
    available_time: datetime
    parse_time: datetime
    persist_time: datetime
    payload: Mapping[str, Any]

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = "1.0"
    run_id: str = ""
    cycle_id: str = ""
    trace_id: str = ""
    parent_event_ids: tuple[str, ...] = ()
    producer_id: str = ""
    producer_sequence: int = 0

    instrument_key: str = ""
    underlying: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    model_id: str = ""
    model_version: str = ""
    candidate_id: str = ""
    order_id: str = ""
    position_id: str = ""

    source_provider: str = ""
    source_time: datetime | None = None
    data_quality_state: str = "OBSERVED"
    authority_class: str = "SOURCE_OBSERVED"
    payload_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", parse_timestamp(self.event_time, field_name="event_time"))
        object.__setattr__(self, "receive_time", parse_timestamp(self.receive_time, field_name="receive_time"))
        object.__setattr__(self, "available_time", parse_timestamp(self.available_time, field_name="available_time"))
        object.__setattr__(self, "parse_time", parse_timestamp(self.parse_time, field_name="parse_time"))
        object.__setattr__(self, "persist_time", parse_timestamp(self.persist_time, field_name="persist_time"))
        if self.source_time is not None:
            object.__setattr__(self, "source_time", parse_timestamp(self.source_time, field_name="source_time"))

        if not self.event_type.strip():
            raise EventValidationError("event_type is required")
        if not self.session_id.strip():
            raise EventValidationError("session_id is required")
        if not self.source_component.strip():
            raise EventValidationError("source_component is required")
        try:
            uuid.UUID(self.event_id)
        except ValueError as exc:
            raise EventValidationError("event_id must be a UUID") from exc
        if _schema_major(self.schema_version) != SUPPORTED_SCHEMA_MAJOR:
            raise EventValidationError(
                f"unsupported schema major {self.schema_version}; supported major is {SUPPORTED_SCHEMA_MAJOR}"
            )
        if self.producer_sequence < 0:
            raise EventValidationError("producer_sequence cannot be negative")
        if self.producer_id and self.producer_sequence <= 0:
            raise EventValidationError("producer_sequence must be positive when producer_id is set")
        if self.source_time is not None and self.receive_time < self.source_time:
            raise EventValidationError("receive_time cannot precede source_time")
        if self.available_time < self.event_time:
            raise EventValidationError("available_time cannot precede event_time")
        if self.available_time < self.receive_time:
            raise EventValidationError("available_time cannot precede receive_time")
        if self.parse_time < self.receive_time:
            raise EventValidationError("parse_time cannot precede receive_time")
        if self.persist_time < self.parse_time:
            raise EventValidationError("persist_time cannot precede parse_time")
        if self.persist_time < self.available_time:
            raise EventValidationError("persist_time cannot precede available_time")
        _validate_json_value(self.payload)
        for parent in self.parent_event_ids:
            try:
                uuid.UUID(parent)
            except ValueError as exc:
                raise EventValidationError(f"invalid parent_event_id {parent!r}") from exc

        expected_hash = sha256(canonical_json(dict(self.payload)).encode("utf-8")).hexdigest()
        if self.payload_hash and self.payload_hash != expected_hash:
            raise EventValidationError("payload_hash does not match canonical payload")
        object.__setattr__(self, "payload_hash", expected_hash)

    @property
    def deterministic_sort_key(self) -> tuple[datetime, str, int, str]:
        return (self.available_time, self.producer_id, self.producer_sequence, self.event_id)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        for key in ("event_time", "source_time", "receive_time", "available_time", "parse_time", "persist_time"):
            value = out[key]
            out[key] = value.isoformat().replace("+00:00", "Z") if value is not None else None
        out["parent_event_ids"] = list(self.parent_event_ids)
        out["payload"] = dict(self.payload)
        return out

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CanonicalEvent":
        values = dict(raw)
        for key in ("event_time", "source_time", "receive_time", "available_time", "parse_time", "persist_time"):
            if key in values and values[key] is not None:
                values[key] = parse_timestamp(values[key], field_name=key)
        values["parent_event_ids"] = tuple(values.get("parent_event_ids") or ())
        values["payload"] = dict(values.get("payload") or {})
        return cls(**values)

    @classmethod
    def from_json(cls, line: str) -> "CanonicalEvent":
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventValidationError(f"invalid JSON event: {exc}") from exc
        if not isinstance(raw, dict):
            raise EventValidationError("event JSON must be an object")
        return cls.from_dict(raw)
