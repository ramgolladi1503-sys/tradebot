from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class MarketEventNode:
    event_id: str
    event_type: str
    event_time: datetime
    available_time: datetime
    parent_event_ids: tuple[str, ...]
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.event_type.strip() or not self.evidence_ref.strip():
            raise ValueError("market_event_identity_missing")
        if self.event_time.tzinfo is None or self.available_time.tzinfo is None:
            raise ValueError("market_event_timezone_required")
        if self.available_time > self.event_time:
            raise ValueError("market_event_available_after_event_time")
        if any(not value.strip() for value in self.parent_event_ids):
            raise ValueError("market_event_empty_parent")


@dataclass(frozen=True)
class MarketEventGraph:
    nodes: tuple[MarketEventNode, ...]
    roots: tuple[str, ...]
    leaves: tuple[str, ...]
    topological_order: tuple[str, ...]
    lead_times_seconds: dict[str, dict[str, float]]

    def to_record(self) -> dict[str, object]:
        return {"roots": list(self.roots), "leaves": list(self.leaves), "topological_order": list(self.topological_order), "lead_times_seconds": self.lead_times_seconds, "nodes": [{"event_id": node.event_id, "event_type": node.event_type, "event_time": node.event_time.isoformat(), "available_time": node.available_time.isoformat(), "parent_event_ids": list(node.parent_event_ids), "evidence_ref": node.evidence_ref} for node in self.nodes]}


def build_market_event_graph(nodes: Iterable[MarketEventNode]) -> MarketEventGraph:
    rows = tuple(nodes)
    if not rows:
        raise ValueError("market_event_graph_empty")
    by_id = {node.event_id: node for node in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate_market_event_id")
    children: dict[str, list[str]] = {event_id: [] for event_id in by_id}
    indegree = {event_id: 0 for event_id in by_id}
    lead_times: dict[str, dict[str, float]] = {}
    for node in rows:
        for parent_id in node.parent_event_ids:
            if parent_id not in by_id:
                raise ValueError(f"missing_market_event_parent={parent_id}")
            parent = by_id[parent_id]
            if parent.event_time > node.event_time:
                raise ValueError("market_event_parent_after_child")
            children[parent_id].append(node.event_id)
            indegree[node.event_id] += 1
            lead_times.setdefault(parent_id, {})[node.event_id] = (node.event_time - parent.event_time).total_seconds()
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
    if len(order) != len(rows):
        raise ValueError("market_event_graph_cycle")
    roots = tuple(event_id for event_id in order if not by_id[event_id].parent_event_ids)
    leaves = tuple(event_id for event_id in order if not children[event_id])
    return MarketEventGraph(tuple(by_id[event_id] for event_id in order), roots, leaves, tuple(order), lead_times)
