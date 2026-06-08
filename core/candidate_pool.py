"""Candidate pool shell for the future opportunity engine.

The pool normalizes and summarizes movement strategy candidates. It does not
rank opportunities, change execution gates, call brokers, call order APIs, touch
depth subscriptions, or tune trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.movement_contract import StrategyCandidate

LIFECYCLE_SCHEMA_VERSION = 1


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
class CandidateLifecycleSnapshot:
    """Canonical read-only lifecycle view for one candidate.

    This intentionally joins already-produced reports by ``strategy_id`` without
    mutating candidates or making new execution decisions. It gives later UI,
    selector, and RCA code one stable answer to: where is this candidate in the
    pipeline and why?
    """

    schema_version: int
    candidate_id: str
    source_intent_id: str | None
    strategy_id: str
    symbol: str
    direction: str
    movement_type: str
    candidate_status: str
    lifecycle_state: str
    capability: str
    classification_bucket: str | None
    downgraded_bucket: str | None
    score_eligibility: str | None
    final_score: float | None
    rank: int | None
    selector_bucket: str | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    downgrade_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    read_only: bool = True
    append: bool = False
    is_order_action: bool = False
    broker_api_called: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "source_intent_id": self.source_intent_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "movement_type": self.movement_type,
            "candidate_status": self.candidate_status,
            "lifecycle_state": self.lifecycle_state,
            "capability": self.capability,
            "classification_bucket": self.classification_bucket,
            "downgraded_bucket": self.downgraded_bucket,
            "score_eligibility": self.score_eligibility,
            "final_score": self.final_score,
            "rank": self.rank,
            "selector_bucket": self.selector_bucket,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "downgrade_reasons": list(self.downgrade_reasons),
            "evidence_refs": list(self.evidence_refs),
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
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

    def lifecycle_snapshots(
        self,
        *,
        classifications: Any = None,
        downgrades: Any = None,
        scores: Any = None,
        ranks: Any = None,
        selector_buckets: Mapping[str, str] | None = None,
    ) -> tuple[CandidateLifecycleSnapshot, ...]:
        return build_candidate_lifecycle_snapshots(
            self.candidates,
            classifications=classifications,
            downgrades=downgrades,
            scores=scores,
            ranks=ranks,
            selector_buckets=selector_buckets,
        )

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


def build_candidate_lifecycle_snapshots(
    candidates: Iterable[StrategyCandidate] | CandidatePool | None,
    *,
    classifications: Any = None,
    downgrades: Any = None,
    scores: Any = None,
    ranks: Any = None,
    selector_buckets: Mapping[str, str] | None = None,
) -> tuple[CandidateLifecycleSnapshot, ...]:
    """Join candidate-pipeline reports into read-only lifecycle snapshots.

    All joins are by ``strategy_id`` because that is the stable identity exposed by
    the existing classifier, downgrade, scorer, and ranker reports. Missing
    downstream reports are allowed; the snapshot then reflects the earliest known
    lifecycle state without inventing confidence or execution safety.
    """

    if isinstance(candidates, CandidatePool):
        items = candidates.candidates
    else:
        items = tuple(candidates or ())
    for item in items:
        if not isinstance(item, StrategyCandidate):
            raise TypeError(f"candidate_lifecycle_item_not_strategy_candidate:{type(item).__name__}")

    classification_by_id = _records_by_strategy_id(classifications, "classifications")
    downgrade_by_id = _records_by_strategy_id(downgrades, "decisions")
    score_by_id = _records_by_strategy_id(scores, "scores")
    rank_by_id = _records_by_strategy_id(ranks, "ranks")
    selector_buckets = {str(k): str(v).upper() for k, v in dict(selector_buckets or {}).items()}

    return tuple(
        _candidate_lifecycle_snapshot(
            candidate,
            classification=classification_by_id.get(candidate.strategy_id),
            downgrade=downgrade_by_id.get(candidate.strategy_id),
            score=score_by_id.get(candidate.strategy_id),
            rank=rank_by_id.get(candidate.strategy_id),
            selector_bucket=selector_buckets.get(candidate.strategy_id),
        )
        for candidate in items
    )


def _candidate_lifecycle_snapshot(
    candidate: StrategyCandidate,
    *,
    classification: Any = None,
    downgrade: Any = None,
    score: Any = None,
    rank: Any = None,
    selector_bucket: str | None = None,
) -> CandidateLifecycleSnapshot:
    classification_bucket = _optional_text(getattr(classification, "bucket", None))
    downgraded_bucket = _optional_text(getattr(downgrade, "downgraded_bucket", None))
    score_eligibility = _optional_text(getattr(score, "score_eligibility", None))
    final_score = _optional_float(getattr(score, "final_score", None))
    rank_value = _optional_int(getattr(rank, "rank", None))
    blockers = _merge_tokens(
        candidate.blockers,
        getattr(classification, "blockers", ()),
        getattr(downgrade, "blockers", ()),
        getattr(score, "blockers", ()),
        getattr(rank, "blockers", ()),
    )
    warnings = _merge_tokens(
        candidate.warnings,
        getattr(classification, "warnings", ()),
        getattr(downgrade, "warnings", ()),
        getattr(score, "warnings", ()),
        getattr(rank, "warnings", ()),
    )
    safety_flags = _merge_tokens(
        getattr(classification, "evidence_flags", ()),
        getattr(downgrade, "safety_flags", ()),
        getattr(score, "safety_flags", ()),
        getattr(rank, "safety_flags", ()),
    )
    downgrade_reasons = _merge_tokens(
        getattr(downgrade, "downgrade_reasons", ()),
        getattr(score, "downgrade_reasons", ()),
        getattr(rank, "downgrade_reasons", ()),
    )
    capability = _candidate_capability(
        candidate,
        classification_bucket=classification_bucket,
        downgraded_bucket=downgraded_bucket,
        score_eligibility=score_eligibility,
        selector_bucket=selector_bucket,
        blockers=blockers,
        safety_flags=safety_flags,
    )
    lifecycle_state = _candidate_lifecycle_state(
        candidate,
        classification_bucket=classification_bucket,
        downgraded_bucket=downgraded_bucket,
        score_eligibility=score_eligibility,
        rank=rank_value,
        selector_bucket=selector_bucket,
        capability=capability,
    )
    return CandidateLifecycleSnapshot(
        schema_version=LIFECYCLE_SCHEMA_VERSION,
        candidate_id=_candidate_lifecycle_id(candidate),
        source_intent_id=_source_intent_id(candidate),
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        movement_type=candidate.movement_type,
        candidate_status=candidate.status,
        lifecycle_state=lifecycle_state,
        capability=capability,
        classification_bucket=classification_bucket,
        downgraded_bucket=downgraded_bucket,
        score_eligibility=score_eligibility,
        final_score=final_score,
        rank=rank_value,
        selector_bucket=selector_bucket,
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        downgrade_reasons=downgrade_reasons,
        evidence_refs=_evidence_refs(candidate),
    )


def _candidate_lifecycle_id(candidate: StrategyCandidate) -> str:
    lineage_id = candidate.lineage.get("candidate_id") or candidate.lineage.get("source_candidate_id")
    if lineage_id:
        return str(lineage_id).strip()
    return "|".join(candidate_pool_dedupe_key(candidate))


def _source_intent_id(candidate: StrategyCandidate) -> str | None:
    for key in ("candidate_intent_id", "source_intent_id", "intent_id"):
        value = candidate.lineage.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return None


def _evidence_refs(candidate: StrategyCandidate) -> tuple[str, ...]:
    refs = candidate.evidence.get("evidence_refs") or candidate.lineage.get("evidence_refs") or ()
    return _merge_tokens(refs)


def _candidate_capability(
    candidate: StrategyCandidate,
    *,
    classification_bucket: str | None,
    downgraded_bucket: str | None,
    score_eligibility: str | None,
    selector_bucket: str | None,
    blockers: tuple[str, ...],
    safety_flags: tuple[str, ...],
) -> str:
    unsafe_tokens = {token.upper() for token in blockers + safety_flags}
    if candidate.status == "NO_TRADE" or classification_bucket == "NO_TRADE_CANDIDATE" or downgraded_bucket == "NO_TRADE_CANDIDATE":
        return "NO_TRADE_ONLY"
    if downgraded_bucket == "SUPPRESSED_CANDIDATE" or classification_bucket == "SUPPRESSED_CANDIDATE" or candidate.status == "BLOCKED_CANDIDATE":
        return "BLOCKED"
    if any("FALLBACK" in token or "STALE" in token or "UNTRUSTED" in token for token in unsafe_tokens):
        return "DISPLAY_SAFE"
    if selector_bucket == "EXECUTABLE" or (
        score_eligibility == "SCORE_ELIGIBLE"
        and downgraded_bucket == "EXECUTABLE_CANDIDATE"
        and candidate.executable_eligible
    ):
        return "EXECUTION_SAFE"
    if score_eligibility in {"SCORE_ELIGIBLE", "NEEDS_CONFIRMATION"} or classification_bucket in {
        "EXECUTABLE_CANDIDATE",
        "NEAR_EXECUTABLE_CANDIDATE",
    }:
        return "RANKING_SAFE"
    if classification_bucket == "ADVISORY_CANDIDATE" or score_eligibility == "ADVISORY_ONLY" or selector_bucket in {"ADVISORY", "SHADOW"}:
        return "ANALYTICS_SAFE"
    return "DISPLAY_SAFE"


def _candidate_lifecycle_state(
    candidate: StrategyCandidate,
    *,
    classification_bucket: str | None,
    downgraded_bucket: str | None,
    score_eligibility: str | None,
    rank: int | None,
    selector_bucket: str | None,
    capability: str,
) -> str:
    if capability == "NO_TRADE_ONLY":
        return "NO_TRADE"
    if capability == "BLOCKED" or selector_bucket == "REJECTED":
        return "BLOCKED"
    if selector_bucket == "EXECUTABLE":
        return "SELECTED"
    if rank is not None:
        return "RANKED"
    if score_eligibility:
        return "SCORED"
    if downgraded_bucket:
        return "DOWNGRADED" if downgraded_bucket != classification_bucket else "SAFETY_VERIFIED"
    if classification_bucket:
        return "CLASSIFIED"
    if candidate.status == "RANKED_OPPORTUNITY":
        return "RANKED"
    if candidate.status == "VALIDATED_CANDIDATE":
        return "RESOLVED"
    if candidate.status == "RAW_CANDIDATE":
        return "INTENT_CREATED"
    return "OBSERVABLE"


def _records_by_strategy_id(source: Any, attr: str) -> dict[str, Any]:
    if source is None:
        return {}
    records = getattr(source, attr, None)
    if records is None:
        records = source
    out: dict[str, Any] = {}
    for record in tuple(records or ()):
        strategy_id = str(getattr(record, "strategy_id", "") or "").strip()
        if strategy_id:
            out[strategy_id] = record
    return out


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


def _merge_tokens(*groups: Any) -> tuple[str, ...]:
    out: set[str] = set()
    for group in groups:
        if group is None:
            continue
        if isinstance(group, str):
            values = (group,)
        elif isinstance(group, Iterable):
            values = group
        else:
            values = (group,)
        for value in values:
            text = str(value or "").strip()
            if text:
                out.add(text)
    return tuple(sorted(out))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except Exception:
        return None


__all__ = [
    "CandidateLifecycleSnapshot",
    "CandidatePool",
    "CandidatePoolSummary",
    "build_candidate_lifecycle_snapshots",
    "build_candidate_pool",
    "candidate_pool_dedupe_key",
]
