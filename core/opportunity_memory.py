from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEvent:
    symbol: str
    thesis: str
    level: float | None
    event_type: str
    ts_epoch: float
    meta: dict[str, Any] = field(default_factory=dict)


class OpportunityMemory:
    def __init__(self, max_events_per_symbol: int = 50) -> None:
        self.max_events_per_symbol = max(10, int(max_events_per_symbol))
        self._events: dict[str, list[MemoryEvent]] = {}

    def remember(self, event: MemoryEvent) -> None:
        bucket = self._events.setdefault(event.symbol, [])
        bucket.append(event)
        if len(bucket) > self.max_events_per_symbol:
            del bucket[:-self.max_events_per_symbol]

    def recent_events(self, symbol: str, thesis: str | None = None, event_type: str | None = None) -> list[MemoryEvent]:
        items = list(self._events.get(symbol, []))
        if thesis is not None:
            items = [x for x in items if x.thesis == thesis]
        if event_type is not None:
            items = [x for x in items if x.event_type == event_type]
        return items

    def score_repetition(self, symbol: str, level: float | None, thesis: str, tolerance: float = 15.0) -> float:
        if level is None:
            return 0.0
        matches = 0
        for event in self.recent_events(symbol, thesis=thesis):
            if event.level is None:
                continue
            if abs(float(event.level) - float(level)) <= float(tolerance):
                matches += 1
        if matches <= 0:
            return 0.0
        return min(1.0, 0.15 * matches)
