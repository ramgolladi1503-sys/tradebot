"""Candidate pool shell for the future opportunity engine.

The pool normalizes and summarizes movement strategy candidates. It does not
rank opportunities, change execution gates, call brokers, call order APIs, touch
depth subscriptions, or tune trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from core.movement_contract import StrategyCandidate


@dataclass(frozen=True)
class CandidatePoolSummary:
    total_count: int
    raw_count: int
    validated_count: int
    blocked_count: int
    ranked_count: int
    no_trade_count: int
    executable_eligible_count: int
    hard_blocked_count: int
    deduped_count: int
    by_strategy: dict[str, int]
    by_movement_type: dict[str, int]
    by_direction: dict[str, int]
    blocker_counts: dict[str, int]
    warning_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_count": self.total_count,
            "raw_count": self.raw_count,
            "validated_count": self.validated_count,
            "blocked_count": self.blocked_count,
            "ranked_count": self.ranked_count,
            "no_trade_count": self.no_trade_count,
            "executable_eligible_count": self.executable_eligible_count,
            "hard_blocked_count": self.hard_blocked_count,
            "deduped_count": self.deduped_count,
            "by_strategy": dict(self.by_strategy),
            "by_movement_type": dict(self.by_movement_type),
            "by_direction": dict(self.by_direction),
            "blocker_counts": dict(self.blocker_counts),
            "warning_counts": dict(self.warning_counts),
        }


@dataclass(frozen=True)
class CandidatePool:
    candidates: tuple[StrategyCandidate, ...]
    duplicates_removed: tuple[StrategyCandidate, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_candidates(
        cls,
        candidates: Iterable[StrategyCandidate] | None,
        *,
        dedupe: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "CandidatePool":
        items = tuple(candidates or ())
        for item in items:
            if not isinstance(item, StrategyCandidate):
                raise TypeError(f"candidate_pool_item_not_strategy_candidate:{type(item).__name__}")
        if not dedupe:
            return cls(candidates=items, duplicates_removed=(), metadata=dict(metadata or {}))
        kept: list[StrategyCandidate] = []
        removed: list[StrategyCandidate] = []
        seen: set[tuple[str, str, str, str]] = set()
        for candidate in items:
            key = candidate_pool_dedupe_key(candidate)
            if key in seen:
                removed.append(candidate)
                continue
            seen.add(key)
            kept.append(candidate)
        return cls(candidates=tuple(kept), duplicates_removed=tuple(removed), metadata=dict(metadata or {}))

    def summary(self) -> CandidatePoolSummary:
        status_counts = _count_by(self.candidates, lambda c: c.status)
        return CandidatePoolSummary(
            total_count=len(self.candidates),
            raw_count=status_counts.get("RAW_CANDIDATE", 0),
            validated_count=status_counts.get("VALIDATED_CANDIDATE", 0),
            blocked_count=status_counts.get("BLOCKED_CANDIDATE", 0),
            ranked_count=status_counts.get("RANKED_OPPORTUNITY", 0),
            no_trade_count=status_counts.get("NO_TRADE", 0),
            executable_eligible_count=sum(1 for c in self.candidates if c.executable_eligible),
            hard_blocked_count=sum(1 for c in self.candidates if c.has_hard_blocker),
            deduped_count=len(self.duplicates_removed),
            by_strategy=_count_by(self.candidates, lambda c: c.strategy_id),
            by_movement_type=_count_by(self.candidates, lambda c: c.movement_type),
            by_direction=_count_by(self.candidates, lambda c: c.direction),
            blocker_counts=_count_tokens(self.candidates, "blockers"),
            warning_counts=_count_tokens(self.candidates, "warnings"),
        )

    def hard_blocked_candidates(self) -> tuple[StrategyCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.has_hard_blocker)

    def executable_eligible_candidates(self) -> tuple[StrategyCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.executable_eligible)

    def no_trade_candidates(self) -> tuple[StrategyCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.status == "NO_TRADE")

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary().to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "duplicates_removed": [candidate.to_dict() for candidate in self.duplicates_removed],
            "metadata": dict(self.metadata),
        }


def candidate_pool_dedupe_key(candidate: StrategyCandidate) -> tuple[str, str, str, str]:
    return (
        candidate.symbol,
        candidate.direction,
        candidate.movement_type,
        candidate.strategy_id,
    )


def build_candidate_pool(
    candidates: Iterable[StrategyCandidate] | None,
    *,
    dedupe: bool = True,
    metadata: dict[str, Any] | None = None,
) -> CandidatePool:
    return CandidatePool.from_candidates(candidates, dedupe=dedupe, metadata=metadata)


def _count_by(candidates: Iterable[StrategyCandidate], key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = str(key_fn(candidate) or "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _count_tokens(candidates: Iterable[StrategyCandidate], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for value in getattr(candidate, attr):
            key = str(value or "").strip().upper()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


__all__ = [
    "CandidatePool",
    "CandidatePoolSummary",
    "build_candidate_pool",
    "candidate_pool_dedupe_key",
]
