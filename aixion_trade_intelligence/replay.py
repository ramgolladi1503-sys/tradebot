from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

from .contracts import CanonicalEvent


class ReplayConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReplayResult:
    ordered_events: tuple[CanonicalEvent, ...]
    raw_event_count: int
    event_count: int
    idempotent_duplicate_count: int
    deterministic_hash: str


def deduplicate_events(events: Iterable[CanonicalEvent]) -> tuple[tuple[CanonicalEvent, ...], int]:
    by_id: dict[str, CanonicalEvent] = {}
    duplicates = 0
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is None:
            by_id[event.event_id] = event
            continue
        if existing.to_json() != event.to_json():
            raise ReplayConflictError(f"event_id {event.event_id} has conflicting payloads")
        duplicates += 1
    return tuple(by_id.values()), duplicates


def order_events(events: Iterable[CanonicalEvent]) -> tuple[CanonicalEvent, ...]:
    unique, _ = deduplicate_events(events)
    return tuple(sorted(unique, key=lambda event: event.deterministic_sort_key))


def replay(events: Iterable[CanonicalEvent]) -> ReplayResult:
    materialized = tuple(events)
    unique, duplicates = deduplicate_events(materialized)
    ordered = tuple(sorted(unique, key=lambda event: event.deterministic_sort_key))
    digest = sha256()
    for event in ordered:
        digest.update(event.to_json().encode("utf-8"))
        digest.update(b"\n")
    return ReplayResult(
        ordered_events=ordered,
        raw_event_count=len(materialized),
        event_count=len(ordered),
        idempotent_duplicate_count=duplicates,
        deterministic_hash=digest.hexdigest(),
    )


def assert_replay_deterministic(events: Iterable[CanonicalEvent]) -> ReplayResult:
    materialized = tuple(events)
    first = replay(materialized)
    second = replay(reversed(materialized))
    if first.deterministic_hash != second.deterministic_hash:
        raise AssertionError("replay hash changed when input iteration order changed")
    if tuple(event.event_id for event in first.ordered_events) != tuple(
        event.event_id for event in second.ordered_events
    ):
        raise AssertionError("replay ordering is not deterministic")
    return first
