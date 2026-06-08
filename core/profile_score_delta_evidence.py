"""Offline profile-vs-default opportunity score delta evidence.

This module compares fixed-weight opportunity scoring against explicit
profile-aware scoring. It is evidence-only: it does not rank for runtime,
execute, call brokers, mutate candidates, touch feeds, or write dashboard state.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.candidate_ranking import rank_candidates
from core.hard_downgrade_engine import HardDowngradeDecision, HardDowngradeReport
from core.movement_contract import StrategyCandidate
from core.opportunity_scoring import (
    OpportunityScoreRecord,
    score_opportunities,
)

DELTA_EVIDENCE_SCHEMA_VERSION = 1
DELTA_EVIDENCE_SOURCE = "profile_score_delta_evidence_v1"


@dataclass(frozen=True)
class ComponentDelta:
    """Per-component score/weight delta explaining why a score moved."""

    component: str
    component_score: float
    default_weight: float
    profile_weight: float
    default_weighted_score: float
    profile_weighted_score: float
    weighted_delta: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "component_score": self.component_score,
            "default_weight": self.default_weight,
            "profile_weight": self.profile_weight,
            "default_weighted_score": self.default_weighted_score,
            "profile_weighted_score": self.profile_weighted_score,
            "weighted_delta": self.weighted_delta,
        }


@dataclass(frozen=True)
class ScoreDeltaRecord:
    """Candidate-level default-vs-profile evidence record."""

    candidate_id: str
    symbol: str
    direction: str
    movement_type: str
    bucket: str
    default_score: float
    profile_score: float
    score_delta: float
    default_rank_estimate: int | None
    profile_rank_estimate: int | None
    rank_delta: int | None
    profile_name: str | None
    component_delta_breakdown: tuple[ComponentDelta, ...]
    promotion_or_demotion_reason: str
    safety_status_unchanged: bool
    default_score_eligibility: str
    profile_score_eligibility: str
    default_executable_candidate: bool
    profile_executable_candidate: bool
    downgrade_reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    safety_flags: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "movement_type": self.movement_type,
            "bucket": self.bucket,
            "default_score": self.default_score,
            "profile_score": self.profile_score,
            "score_delta": self.score_delta,
            "default_rank_estimate": self.default_rank_estimate,
            "profile_rank_estimate": self.profile_rank_estimate,
            "rank_delta": self.rank_delta,
            "profile_name": self.profile_name,
            "component_delta_breakdown": [delta.to_dict() for delta in self.component_delta_breakdown],
            "promotion_or_demotion_reason": self.promotion_or_demotion_reason,
            "safety_status_unchanged": self.safety_status_unchanged,
            "default_score_eligibility": self.default_score_eligibility,
            "profile_score_eligibility": self.profile_score_eligibility,
            "default_executable_candidate": self.default_executable_candidate,
            "profile_executable_candidate": self.profile_executable_candidate,
            "downgrade_reasons": list(self.downgrade_reasons),
            "blockers": list(self.blockers),
            "safety_flags": list(self.safety_flags),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ScoreDeltaEvidenceReport:
    """Read-only offline evidence report for profile score deltas."""

    schema_version: int
    source: str
    read_only: bool
    append: bool
    candidate_count: int
    changed_score_count: int
    promoted_count: int
    demoted_count: int
    unchanged_rank_count: int
    safety_status_changed_count: int
    records: tuple[ScoreDeltaRecord, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
            "candidate_count": self.candidate_count,
            "changed_score_count": self.changed_score_count,
            "promoted_count": self.promoted_count,
            "demoted_count": self.demoted_count,
            "unchanged_rank_count": self.unchanged_rank_count,
            "safety_status_changed_count": self.safety_status_changed_count,
            "records": [record.to_dict() for record in self.records],
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def build_profile_score_delta_evidence(
    candidates: Iterable[StrategyCandidate],
    downgrade_report: HardDowngradeReport | Iterable[HardDowngradeDecision],
    *,
    scoring_profile: Any,
) -> ScoreDeltaEvidenceReport:
    """Build offline default-vs-profile score delta evidence.

    The function intentionally uses the existing scorer and ranking report in
    shadow/evidence mode only. It does not change runtime ranking behavior.
    """

    if scoring_profile is None:
        raise ValueError("profile_score_delta_requires_scoring_profile")

    candidate_tuple = tuple(candidates or ())
    default_report = score_opportunities(candidate_tuple, downgrade_report)
    profile_report = score_opportunities(candidate_tuple, downgrade_report, scoring_profile=scoring_profile)

    default_rank_by_id = _rank_by_strategy_id(default_report)
    profile_rank_by_id = _rank_by_strategy_id(profile_report)
    profile_by_id = {record.strategy_id: record for record in profile_report.scores}

    records = tuple(
        _delta_record(
            default_record,
            profile_by_id[default_record.strategy_id],
            default_rank_by_id.get(default_record.strategy_id),
            profile_rank_by_id.get(default_record.strategy_id),
            profile_report.metadata,
        )
        for default_record in default_report.scores
    )

    promoted_count = sum(1 for record in records if record.rank_delta is not None and record.rank_delta > 0)
    demoted_count = sum(1 for record in records if record.rank_delta is not None and record.rank_delta < 0)
    unchanged_rank_count = sum(1 for record in records if record.rank_delta == 0)
    safety_status_changed_count = sum(1 for record in records if not record.safety_status_unchanged)

    return ScoreDeltaEvidenceReport(
        schema_version=DELTA_EVIDENCE_SCHEMA_VERSION,
        source=DELTA_EVIDENCE_SOURCE,
        read_only=True,
        append=False,
        candidate_count=len(records),
        changed_score_count=sum(1 for record in records if record.score_delta != 0.0),
        promoted_count=promoted_count,
        demoted_count=demoted_count,
        unchanged_rank_count=unchanged_rank_count,
        safety_status_changed_count=safety_status_changed_count,
        records=records,
        metadata={
            "scope": "offline_profile_score_delta_evidence_only",
            "default_scorer": default_report.metadata.get("scorer"),
            "profile_scorer": profile_report.metadata.get("scorer"),
            "profile_name": profile_report.metadata.get("scoring_profile_name"),
            "scoring_profile_applied": bool(profile_report.metadata.get("scoring_profile_applied", False)),
            "default_component_weights": dict(default_report.metadata.get("component_weights") or {}),
            "profile_component_weights": dict(profile_report.metadata.get("component_weights") or {}),
            "rank_estimate_source": "candidate_ranking_v1_shadow_reports",
            "profile_sort_cutover_enabled": False,
            "runtime_wiring_changed": False,
            "broker_api_called": False,
        },
    )


def _delta_record(
    default_record: OpportunityScoreRecord,
    profile_record: OpportunityScoreRecord,
    default_rank: int | None,
    profile_rank: int | None,
    profile_metadata: Mapping[str, Any],
) -> ScoreDeltaRecord:
    if default_record.strategy_id != profile_record.strategy_id:
        raise ValueError("profile_score_delta_strategy_id_mismatch")

    score_delta = _round(profile_record.final_score - default_record.final_score)
    rank_delta = _rank_delta(default_rank, profile_rank)
    component_deltas = _component_deltas(default_record, profile_record)
    safety_status_unchanged = _safety_status(default_record) == _safety_status(profile_record)

    return ScoreDeltaRecord(
        candidate_id=default_record.strategy_id,
        symbol=default_record.symbol,
        direction=default_record.direction,
        movement_type=default_record.movement_type,
        bucket=profile_record.bucket,
        default_score=_round(default_record.final_score),
        profile_score=_round(profile_record.final_score),
        score_delta=score_delta,
        default_rank_estimate=default_rank,
        profile_rank_estimate=profile_rank,
        rank_delta=rank_delta,
        profile_name=_profile_name(profile_metadata),
        component_delta_breakdown=component_deltas,
        promotion_or_demotion_reason=_movement_reason(score_delta, rank_delta, component_deltas),
        safety_status_unchanged=safety_status_unchanged,
        default_score_eligibility=default_record.score_eligibility,
        profile_score_eligibility=profile_record.score_eligibility,
        default_executable_candidate=bool(default_record.executable_candidate),
        profile_executable_candidate=bool(profile_record.executable_candidate),
        downgrade_reasons=tuple(sorted(set(default_record.downgrade_reasons) | set(profile_record.downgrade_reasons))),
        blockers=tuple(sorted(set(default_record.blockers) | set(profile_record.blockers))),
        safety_flags=tuple(sorted(set(default_record.safety_flags) | set(profile_record.safety_flags))),
        warnings=tuple(sorted(set(default_record.warnings) | set(profile_record.warnings))),
    )


def _component_deltas(
    default_record: OpportunityScoreRecord,
    profile_record: OpportunityScoreRecord,
) -> tuple[ComponentDelta, ...]:
    components = sorted(
        set(default_record.breakdown.component_scores)
        | set(profile_record.breakdown.component_scores)
        | set(default_record.breakdown.component_weights)
        | set(profile_record.breakdown.component_weights)
    )
    deltas = []
    for component in components:
        default_weighted = _round(default_record.breakdown.weighted_component_scores.get(component, 0.0))
        profile_weighted = _round(profile_record.breakdown.weighted_component_scores.get(component, 0.0))
        deltas.append(
            ComponentDelta(
                component=component,
                component_score=_round(profile_record.breakdown.component_scores.get(component, 0.0)),
                default_weight=_round(default_record.breakdown.component_weights.get(component, 0.0)),
                profile_weight=_round(profile_record.breakdown.component_weights.get(component, 0.0)),
                default_weighted_score=default_weighted,
                profile_weighted_score=profile_weighted,
                weighted_delta=_round(profile_weighted - default_weighted),
            )
        )
    return tuple(deltas)


def _movement_reason(
    score_delta: float,
    rank_delta: int | None,
    component_deltas: tuple[ComponentDelta, ...],
) -> str:
    largest = max(component_deltas, key=lambda item: abs(item.weighted_delta), default=None)
    driver = f"driver={largest.component}:{largest.weighted_delta:+.6f}" if largest is not None else "driver=none"
    if rank_delta is not None and rank_delta > 0:
        return f"PROMOTED; score_delta={score_delta:+.6f}; rank_delta={rank_delta}; {driver}"
    if rank_delta is not None and rank_delta < 0:
        return f"DEMOTED; score_delta={score_delta:+.6f}; rank_delta={rank_delta}; {driver}"
    if score_delta > 0:
        return f"SCORE_UP_RANK_UNCHANGED; score_delta={score_delta:+.6f}; {driver}"
    if score_delta < 0:
        return f"SCORE_DOWN_RANK_UNCHANGED; score_delta={score_delta:+.6f}; {driver}"
    return f"UNCHANGED; score_delta={score_delta:+.6f}; {driver}"


def _rank_by_strategy_id(score_report) -> dict[str, int]:
    ranking_report = rank_candidates(score_report)
    return {record.strategy_id: record.rank for record in ranking_report.ranks}


def _rank_delta(default_rank: int | None, profile_rank: int | None) -> int | None:
    if default_rank is None or profile_rank is None:
        return None
    return int(default_rank - profile_rank)


def _safety_status(record: OpportunityScoreRecord) -> tuple[Any, ...]:
    return (
        record.bucket,
        record.score_eligibility,
        bool(record.executable_candidate),
        tuple(record.downgrade_reasons),
        tuple(record.blockers),
        tuple(record.safety_flags),
    )


def _profile_name(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("scoring_profile_name")
    if value is None:
        return None
    return str(value)


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "DELTA_EVIDENCE_SCHEMA_VERSION",
    "DELTA_EVIDENCE_SOURCE",
    "ComponentDelta",
    "ScoreDeltaEvidenceReport",
    "ScoreDeltaRecord",
    "build_profile_score_delta_evidence",
]
