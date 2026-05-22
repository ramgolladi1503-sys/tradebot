from __future__ import annotations

import json
from dataclasses import dataclass
from typing import IO, Mapping

from core.observability.events import ObservabilityEvent, validate_event_payload

_DEFAULT_SEPARATORS = (",", ":")


class ObservabilityJsonLogError(ValueError):
    """Raised when a structured observability log record is invalid."""


@dataclass(frozen=True)
class ObservabilityJsonLogRecord:
    """Validated JSON-line representation of an observability event."""

    payload: Mapping[str, object]

    @classmethod
    def from_event(cls, event: ObservabilityEvent) -> "ObservabilityJsonLogRecord":
        return cls(payload=event.as_dict())

    def as_dict(self) -> dict[str, object]:
        payload = dict(self.payload)
        validate_event_payload(payload)
        return payload

    def to_json_line(self) -> str:
        payload = self.as_dict()
        return json.dumps(
            payload,
            sort_keys=True,
            separators=_DEFAULT_SEPARATORS,
            ensure_ascii=False,
        ) + "\n"


class ObservabilityJsonLogger:
    """Minimal stream writer for structured observability JSON lines."""

    def __init__(self, stream: IO[str]) -> None:
        if stream is None:
            raise ObservabilityJsonLogError("stream_required")
        self._stream = stream

    def write_event(self, event: ObservabilityEvent) -> dict[str, object]:
        record = ObservabilityJsonLogRecord.from_event(event)
        payload = record.as_dict()
        self._stream.write(record.to_json_line())
        self._stream.flush()
        return payload


def event_to_json_line(event: ObservabilityEvent) -> str:
    return ObservabilityJsonLogRecord.from_event(event).to_json_line()


def payload_to_json_line(payload: Mapping[str, object]) -> str:
    return ObservabilityJsonLogRecord(payload=payload).to_json_line()
