from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    event_type: str
    event_time: datetime
    available_time: datetime
    direction: str
    magnitude: float
    parent_event_ids: tuple[str, ...]
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.event_id or not self.event_type:
            raise ValueError("market_event_identity_missing")
        if self.event_time.tzinfo is None or self.available_time.tzinfo is None:
            raise ValueError("market_event_times_must_be_aware")
        if self.available_time > self.event_time:
            raise ValueError("market_event_available_after_event_time")
        if self.direction not in {"UP", "DOWN", "NEUTRAL", "MIXED"}:
            raise ValueError("market_event_direction_invalid")
        if len(set(self.parent_event_ids)) != len(self.parent_event_ids):
            raise ValueError("duplicate_market_event_parent")


@dataclass(frozen=True)
class EventGraphValidation:
    valid: bool
    missing_parents: tuple[str, ...]
    future_parent_edges: tuple[tuple[str, str], ...]
    cycles: tuple[tuple[str, ...], ...]
    topological_order: tuple[str, ...]


def validate_market_event_graph(events: Iterable[MarketEvent]) -> EventGraphValidation:
    rows = list(events)
    if not rows:
        raise ValueError("market_events_empty")
    mapping = {row.event_id: row for row in rows}
    if len(mapping) != len(rows):
        raise ValueError("duplicate_market_event_id")
    missing: set[str] = set()
    future_edges: list[tuple[str, str]] = []
    children: dict[str, list[str]] = {event_id: [] for event_id in mapping}
    indegree: dict[str, int] = {event_id: 0 for event_id in mapping}
    for row in rows:
        for parent_id in row.parent_event_ids:
            parent = mapping.get(parent_id)
            if parent is None:
                missing.add(parent_id)
                continue
            if parent.event_time > row.event_time or parent.available_time > row.event_time:
                future_edges.append((parent_id, row.event_id))
            children[parent_id].append(row.event_id)
            indegree[row.event_id] += 1
    queue = sorted(event_id for event_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()
    cycles: tuple[tuple[str, ...], ...] = ()
    if len(order) != len(mapping):
        cyclic_nodes = tuple(sorted(event_id for event_id, degree in indegree.items() if degree > 0))
        cycles = (cyclic_nodes,)
    valid = not missing and not future_edges and not cycles
    return EventGraphValidation(
        valid=valid,
        missing_parents=tuple(sorted(missing)),
        future_parent_edges=tuple(sorted(future_edges)),
        cycles=cycles,
        topological_order=tuple(order),
    )


def event_path(
    events: Iterable[MarketEvent],
    *,
    target_event_id: str,
) -> tuple[str, ...]:
    mapping = {row.event_id: row for row in events}
    if target_event_id not in mapping:
        raise ValueError("target_market_event_missing")
    validation = validate_market_event_graph(mapping.values())
    if not validation.valid:
        raise ValueError("market_event_graph_invalid")
    ancestors: set[str] = set()

    def visit(event_id: str) -> None:
        for parent_id in mapping[event_id].parent_event_ids:
            if parent_id not in ancestors:
                visit(parent_id)
                ancestors.add(parent_id)

    visit(target_event_id)
    return tuple(
        event_id
        for event_id in validation.topological_order
        if event_id in ancestors or event_id == target_event_id
    )
