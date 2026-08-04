from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from .contracts import CanonicalEvent, EventValidationError


class EventLogError(RuntimeError):
    pass


def iter_events(path: str | Path) -> Iterator[CanonicalEvent]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    seen: set[str] = set()
    previous_sequence: dict[tuple[str, str], int] = {}
    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
                event = CanonicalEvent.from_record(record)
            except (json.JSONDecodeError, EventValidationError, TypeError) as exc:
                raise EventLogError(f"invalid_event_at_line={line_number}") from exc
            if event.event_id in seen:
                continue
            seen.add(event.event_id)
            if event.producer_sequence is not None:
                key = (event.session_id, event.source_component)
                previous = previous_sequence.get(key)
                if previous is not None and event.producer_sequence <= previous:
                    raise EventLogError(
                        f"non_monotonic_producer_sequence_at_line={line_number}"
                    )
                previous_sequence[key] = event.producer_sequence
            yield event


def event_log_hash(events: Iterable[CanonicalEvent]) -> str:
    digest = hashlib.sha256()
    for event in events:
        encoded = json.dumps(
            event.to_record(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def verify_event_log(path: str | Path) -> dict[str, object]:
    events = list(iter_events(path))
    sessions = sorted({event.session_id for event in events})
    return {
        "event_count": len(events),
        "session_count": len(sessions),
        "sessions": sessions,
        "event_log_sha256": event_log_hash(events),
        "valid": bool(events) and len(sessions) == 1,
    }
