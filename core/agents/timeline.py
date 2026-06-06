from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import AgentEvidenceRef


@dataclass(frozen=True)
class TimelineEvent:
    source_path: str
    line_number: int | None
    event: str | None
    ts_epoch: float | None
    excerpt: str
    fields: dict[str, Any]

    def to_evidence_ref(self) -> AgentEvidenceRef:
        return AgentEvidenceRef(
            source_path=self.source_path,
            line_number=self.line_number,
            event=self.event,
            ts_epoch=self.ts_epoch,
            excerpt=self.excerpt,
            fields=dict(self.fields),
        )


def sort_timeline_events(events: list[TimelineEvent]) -> list[TimelineEvent]:
    return sorted(
        events,
        key=lambda item: (
            float("inf") if item.ts_epoch is None else item.ts_epoch,
            item.source_path,
            item.line_number or 0,
            item.event or "",
            item.excerpt,
        ),
    )
