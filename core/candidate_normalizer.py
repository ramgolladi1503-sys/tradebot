"""Read-only candidate normalization and deduplication.

This module prepares candidate-pool output for future classification/scoring by
collapsing duplicate setup rows while preserving all blockers, warnings, tags,
source signals, evidence, and lineage. It never ranks, executes, calls a broker,
touches depth subscriptions, mutates input candidates, or makes a blocked/fallback
candidate executable.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from core.movement_contract import SCORE_FIELDS, StrategyCandidate, has_hard_blocker

NORMALIZATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CandidateDuplicateGroup:
    """Audit record for one duplicate group collapsed by normalization."""

    key: tuple[str, str, str]
    candidate_count: int
    canonical_strategy_id: str
    duplicate_strategy_ids: tuple[str, ...]
    merged_blockers: tuple[str, ...]
    merged_warnings: tuple[str, ...]
    merged_source_signals: tuple[str, ...]
    canonical_status_before_merge: str
    canonical_status_after_merge: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": list(self.key),
            "candidate_count": self.candidate_count,
            "canonical_strategy_id": self.canonical_strategy_id,
            "duplicate_strategy_ids": list(self.duplicate_strategy_ids),
            "merged_blockers": list(self.merged_blockers),
            "merged_warnings": list(self.merged_warnings),
            "merged_source_signals": list(self.merged_source_signals),
            "canonical_status_before_merge": self.canonical_status_before_merge,
            "canonical_status_after_merge": self.canonical_status_after_merge,
        }


@dataclass(frozen=True)
class CandidateNormalizationResult:
    """Read-only output of candidate normalization."""

    schema_version: int
    read_only: bool
    is_order_action: bool
    append: bool
    raw_count: int
    normalized_count: int
    duplicate_group_count: int
    duplicate_candidate_count: int
    merged_blocker_count: int
    merged_warning_count: int
    candidates: tuple[StrategyCandidate, ...]
    duplicate_groups: tuple[CandidateDuplicateGroup, ...]
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": self.is_order_action,
            "append": self.append,
            "raw_count": self.raw_count,
            "normalized_count": self.normalized_count,
            "duplicate_group_count": self.duplicate_group_count,
            "duplicate_candidate_count": self.duplicate_candidate_count,
            "merged_blocker_count": self.merged_blocker_count,
            "merged_warning_count": self.merged_warning_count,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "duplicate_groups": [group.to_dict() for group in self.duplicate_groups],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def normalize_candidates(
    candidates: Iterable[StrategyCandidate],
    *,
    include_strategy_id_in_key: bool = False,
) -> CandidateNormalizationResult:
    """Normalize and deduplicate strategy candidates without changing execution truth.

    Default grouping is by ``symbol + direction + movement_type``. ``strategy_id``
    is intentionally excluded by default so multiple strategy modules emitting the
    same setup collapse into one canonical candidate while retaining lineage. If a
    caller needs stricter collision rules, ``include_strategy_id_in_key=True``
    keeps strategy ids separate.
    """

    raw_candidates = tuple(candidates or ())
    groups: dict[tuple[str, ...], list[StrategyCandidate]] = {}
    ordered_keys: list[tuple[str, ...]] = []

    for candidate in raw_candidates:
        if not isinstance(candidate, StrategyCandidate):
            raise TypeError("candidate_normalizer_expected_strategy_candidate")
        key = _normalization_key(candidate, include_strategy_id=include_strategy_id_in_key)
        if key not in groups:
            groups[key] = []
            ordered_keys.append(key)
        groups[key].append(candidate)

    normalized: list[StrategyCandidate] = []
    duplicate_groups: list[CandidateDuplicateGroup] = []
    warnings: list[str] = []
    merged_blocker_total = 0
    merged_warning_total = 0

    for key in ordered_keys:
        members = tuple(groups[key])
        canonical = _choose_canonical_candidate(members)
        merged = _merge_candidate_evidence(canonical, members)
        normalized.append(merged)

        extra_blockers = set(merged.blockers) - set(canonical.blockers)
        extra_warnings = set(merged.warnings) - set(canonical.warnings)
        merged_blocker_total += len(extra_blockers)
        merged_warning_total += len(extra_warnings)

        if len(members) > 1:
            duplicate_groups.append(
                CandidateDuplicateGroup(
                    key=(str(key[0]), str(key[1]), str(key[2])),
                    candidate_count=len(members),
                    canonical_strategy_id=canonical.strategy_id,
                    duplicate_strategy_ids=tuple(candidate.strategy_id for candidate in members if candidate.strategy_id != canonical.strategy_id),
                    merged_blockers=tuple(sorted(set(merged.blockers))),
                    merged_warnings=tuple(sorted(set(merged.warnings))),
                    merged_source_signals=tuple(sorted(set(merged.source_signals))),
                    canonical_status_before_merge=canonical.status,
                    canonical_status_after_merge=merged.status,
                )
            )
            if canonical.status != merged.status:
                warnings.append(f"canonical_status_downgraded:{canonical.strategy_id}:{canonical.status}->{merged.status}")

    duplicate_candidate_count = sum(max(group.candidate_count - 1, 0) for group in duplicate_groups)
    return CandidateNormalizationResult(
        schema_version=NORMALIZATION_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        raw_count=len(raw_candidates),
        normalized_count=len(normalized),
        duplicate_group_count=len(duplicate_groups),
        duplicate_candidate_count=duplicate_candidate_count,
        merged_blocker_count=merged_blocker_total,
        merged_warning_count=merged_warning_total,
        candidates=tuple(normalized),
        duplicate_groups=tuple(duplicate_groups),
        warnings=tuple(sorted(set(warnings))),
        metadata={
            "normalizer": "candidate_normalizer_v1",
            "scope": "read_only_no_execution_no_ranking",
            "key_fields": ["symbol", "direction", "movement_type"] + (["strategy_id"] if include_strategy_id_in_key else []),
            "include_strategy_id_in_key": bool(include_strategy_id_in_key),
        },
    )


def _normalization_key(candidate: StrategyCandidate, *, include_strategy_id: bool) -> tuple[str, ...]:
    key = (candidate.symbol, candidate.direction, candidate.movement_type)
    if include_strategy_id:
        return key + (candidate.strategy_id,)
    return key


def _choose_canonical_candidate(candidates: tuple[StrategyCandidate, ...]) -> StrategyCandidate:
    return max(candidates, key=_canonical_strength_key)


def _canonical_strength_key(candidate: StrategyCandidate) -> tuple[Any, ...]:
    # Prefer candidates that are structurally executable before evidence merge,
    # then higher quality scores. This is only canonical selection, not ranking.
    return (
        1 if candidate.executable_eligible else 0,
        0 if candidate.has_hard_blocker else 1,
        _status_weight(candidate.status),
        float(candidate.confidence_score),
        float(candidate.raw_score),
        float(candidate.option_confirmation_score),
        float(candidate.price_structure_score),
        float(candidate.liquidity_score),
        float(candidate.freshness_score),
        float(candidate.regime_alignment_score),
        -float(candidate.trap_risk_score),
        str(candidate.strategy_id),
    )


def _status_weight(status: str) -> int:
    return {
        "RANKED_OPPORTUNITY": 5,
        "VALIDATED_CANDIDATE": 4,
        "RAW_CANDIDATE": 3,
        "BLOCKED_CANDIDATE": 2,
        "NO_TRADE": 1,
    }.get(str(status).upper(), 0)


def _merge_candidate_evidence(canonical: StrategyCandidate, candidates: tuple[StrategyCandidate, ...]) -> StrategyCandidate:
    merged_blockers = _merge_texts(*(candidate.blockers for candidate in candidates))
    merged_warnings = _merge_texts(*(candidate.warnings for candidate in candidates))
    merged_confluence_tags = _merge_texts(*(candidate.confluence_tags for candidate in candidates))
    merged_suppression_tags = _merge_texts(*(candidate.suppression_tags for candidate in candidates))
    merged_source_signals = _merge_texts(*(candidate.source_signals for candidate in candidates), tuple(candidate.strategy_id for candidate in candidates))
    merged_regime_scores = _merge_score_maps(*(candidate.regime_scores for candidate in candidates))
    merged_evidence = _merge_evidence(canonical, candidates)
    merged_lineage = _merge_lineage(canonical, candidates)
    status = _merged_status(canonical, candidates, merged_blockers)

    return replace(
        canonical,
        status=status,
        blockers=merged_blockers,
        warnings=merged_warnings,
        confluence_tags=merged_confluence_tags,
        suppression_tags=merged_suppression_tags,
        source_signals=merged_source_signals,
        regime_scores=merged_regime_scores,
        evidence=merged_evidence,
        lineage=merged_lineage,
    )


def _merged_status(
    canonical: StrategyCandidate,
    candidates: tuple[StrategyCandidate, ...],
    blockers: tuple[str, ...],
) -> str:
    if canonical.direction == "NO_TRADE" or any(candidate.status == "NO_TRADE" for candidate in candidates):
        return "NO_TRADE"
    if has_hard_blocker(blockers):
        return "BLOCKED_CANDIDATE"
    if any(candidate.status == "RANKED_OPPORTUNITY" for candidate in candidates):
        return "RANKED_OPPORTUNITY"
    if any(candidate.status == "VALIDATED_CANDIDATE" for candidate in candidates):
        return "VALIDATED_CANDIDATE"
    if any(candidate.status == "RAW_CANDIDATE" for candidate in candidates):
        return "RAW_CANDIDATE"
    return canonical.status


def _merge_texts(*groups: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or ():
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return tuple(sorted(out))


def _merge_score_maps(*maps: dict[str, float]) -> dict[str, float]:
    merged: dict[str, float] = {}
    for mapping in maps:
        for key, value in dict(mapping or {}).items():
            k = str(key).strip().upper()
            if not k:
                continue
            try:
                val = float(value)
            except Exception:
                continue
            merged[k] = max(float(merged.get(k, 0.0)), val)
    return merged


def _merge_evidence(canonical: StrategyCandidate, candidates: tuple[StrategyCandidate, ...]) -> dict[str, Any]:
    merged = dict(canonical.evidence or {})
    merged["normalization"] = {
        "canonical_strategy_id": canonical.strategy_id,
        "merged_strategy_ids": [candidate.strategy_id for candidate in candidates],
        "merged_count": len(candidates),
        "duplicate_strategy_ids": [candidate.strategy_id for candidate in candidates if candidate.strategy_id != canonical.strategy_id],
    }
    merged["merged_candidate_evidence"] = {
        candidate.strategy_id: dict(candidate.evidence or {}) for candidate in candidates if candidate.evidence
    }
    return _jsonable(merged)


def _merge_lineage(canonical: StrategyCandidate, candidates: tuple[StrategyCandidate, ...]) -> dict[str, Any]:
    merged = dict(canonical.lineage or {})
    merged["normalization"] = {
        "canonical_strategy_id": canonical.strategy_id,
        "source_strategy_ids": [candidate.strategy_id for candidate in candidates],
        "source_statuses": {candidate.strategy_id: candidate.status for candidate in candidates},
        "source_blockers": {candidate.strategy_id: list(candidate.blockers) for candidate in candidates if candidate.blockers},
        "source_warnings": {candidate.strategy_id: list(candidate.warnings) for candidate in candidates if candidate.warnings},
    }
    return _jsonable(merged)


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    json.dumps(payload, sort_keys=True, default=str)
    return payload


__all__ = [
    "CandidateDuplicateGroup",
    "CandidateNormalizationResult",
    "NORMALIZATION_SCHEMA_VERSION",
    "normalize_candidates",
]
