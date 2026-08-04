from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from statistics import median
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CASPhase:
    name: str
    start: time
    end: time

    def __post_init__(self) -> None:
        if not self.name or self.end <= self.start:
            raise ValueError("cas_phase_invalid")

    def contains(self, timestamp: datetime) -> bool:
        local = timestamp.timetz().replace(tzinfo=None)
        return self.start <= local < self.end


@dataclass(frozen=True)
class CASObservation:
    session_id: str
    timestamp: datetime
    index_price: float
    phase: str
    expiry_class: str

    def __post_init__(self) -> None:
        if not self.session_id or not self.phase or not self.expiry_class:
            raise ValueError("cas_observation_identity_missing")
        if self.timestamp.tzinfo is None:
            raise ValueError("cas_timestamp_must_be_aware")
        if self.index_price <= 0:
            raise ValueError("cas_index_price_nonpositive")


@dataclass(frozen=True)
class CASSessionSummary:
    session_id: str
    expiry_class: str
    pre_transition_price: float
    final_price: float
    change_points: float
    change_fraction: float
    largest_revision_points: float
    largest_revision_time: str
    phase_returns: dict[str, float]


def assign_phase(timestamp: datetime, phases: Sequence[CASPhase]) -> str:
    matches = [phase.name for phase in phases if phase.contains(timestamp)]
    if len(matches) != 1:
        raise ValueError("cas_phase_missing_or_ambiguous")
    return matches[0]


def summarize_cas_session(
    observations: Sequence[CASObservation],
    *,
    pre_transition_phase: str,
) -> CASSessionSummary:
    if not observations:
        raise ValueError("cas_observations_empty")
    session_ids = {row.session_id for row in observations}
    expiry_classes = {row.expiry_class for row in observations}
    if len(session_ids) != 1 or len(expiry_classes) != 1:
        raise ValueError("cas_session_mixed_identity")
    rows = sorted(observations, key=lambda row: row.timestamp)
    anchors = [row for row in rows if row.phase == pre_transition_phase]
    if not anchors:
        raise ValueError("cas_pre_transition_anchor_missing")
    anchor = anchors[-1]
    final = rows[-1]
    revisions = [
        (current.index_price - previous.index_price, current.timestamp)
        for previous, current in zip(rows, rows[1:])
    ]
    largest_points, largest_time = max(revisions, key=lambda item: abs(item[0])) if revisions else (0.0, final.timestamp)
    phase_returns: dict[str, float] = {}
    for phase in sorted({row.phase for row in rows}):
        phase_rows = [row for row in rows if row.phase == phase]
        if phase_rows:
            phase_returns[phase] = phase_rows[-1].index_price / phase_rows[0].index_price - 1.0
    return CASSessionSummary(
        session_id=anchor.session_id,
        expiry_class=anchor.expiry_class,
        pre_transition_price=anchor.index_price,
        final_price=final.index_price,
        change_points=final.index_price - anchor.index_price,
        change_fraction=final.index_price / anchor.index_price - 1.0,
        largest_revision_points=largest_points,
        largest_revision_time=largest_time.isoformat(),
        phase_returns=phase_returns,
    )


def aggregate_cas_sessions(
    summaries: Iterable[CASSessionSummary],
) -> dict[str, object]:
    rows = list(summaries)
    if not rows:
        raise ValueError("cas_summaries_empty")
    grouped: dict[str, list[CASSessionSummary]] = {}
    for row in rows:
        grouped.setdefault(row.expiry_class, []).append(row)
    result: dict[str, object] = {}
    for expiry_class, group in sorted(grouped.items()):
        changes = [row.change_fraction for row in group]
        result[expiry_class] = {
            "sessions": len(group),
            "positive": sum(value > 0 for value in changes),
            "negative": sum(value < 0 for value in changes),
            "unchanged": sum(value == 0 for value in changes),
            "median_change_fraction": median(changes),
            "mean_change_fraction": sum(changes) / len(changes),
            "session_ids": [row.session_id for row in group],
        }
    return result
