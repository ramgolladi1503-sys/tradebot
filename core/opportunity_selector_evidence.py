"""Read-only opportunity selector evidence for ranked candidates."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from core.candidate_ranking import CandidateRankRecord, CandidateRankingReport
from core.opportunity_scoring import SCORE_ELIGIBLE

SELECTOR_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class OpportunitySelectionEvidenceRecord:
    rank: int
    strategy_id: str
    symbol: str
    direction: str
    final_score: float
    selected: bool
    selector_decision: str
    selector_reason: str
    score_eligibility: str
    executable_candidate: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OpportunitySelectorEvidenceReport:
    schema_version: int
    read_only: bool
    source_rank_count: int
    selected_count: int
    not_selected_count: int
    executable_source_count: int
    score_eligible_source_count: int
    blocked_source_count: int
    no_selection_reason: str | None
    selected_strategy_ids: tuple[str, ...]
    records: tuple[OpportunitySelectionEvidenceRecord, ...]
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    is_order_action: bool = False
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": self.is_order_action,
            "append": self.append,
            "source_rank_count": self.source_rank_count,
            "selected_count": self.selected_count,
            "not_selected_count": self.not_selected_count,
            "executable_source_count": self.executable_source_count,
            "score_eligible_source_count": self.score_eligible_source_count,
            "blocked_source_count": self.blocked_source_count,
            "no_selection_reason": self.no_selection_reason,
            "selected_strategy_ids": list(self.selected_strategy_ids),
            "records": [record.to_dict() for record in self.records],
            "rejection_reasons": list(self.rejection_reasons),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def build_opportunity_selector_evidence(
    ranking_report: CandidateRankingReport | Iterable[CandidateRankRecord],
    *,
    selection_limit: int = 3,
) -> OpportunitySelectorEvidenceReport:
    """Build read-only selector evidence from a ranking report.

    This does not alter ranking, scores, or runtime state. It only explains which
    ranked rows are selector-eligible and why the remaining rows are not selected.
    """
    ranks, source_metadata = _coerce_ranks(ranking_report)
    normalized_limit = max(0, int(selection_limit or 0))
    selected_candidates = tuple(
        rank
        for rank in ranks
        if rank.executable_candidate and rank.score_eligibility == SCORE_ELIGIBLE and not rank.blockers
    )[:normalized_limit]
    selected_ids = {rank.strategy_id for rank in selected_candidates}
    records = tuple(_evidence_record(rank, rank.strategy_id in selected_ids) for rank in ranks)
    rejection_reasons = tuple(sorted(set(reason for record in records if not record.selected for reason in _record_reasons(record))))
    warnings = tuple(sorted(set(warning for record in records for warning in record.warnings)))
    safety_flags = tuple(sorted(set(flag for record in records for flag in record.safety_flags)))
    executable_count = sum(1 for rank in ranks if rank.executable_candidate)
    eligible_count = sum(1 for rank in ranks if rank.score_eligibility == SCORE_ELIGIBLE)
    blocked_count = sum(1 for rank in ranks if rank.blockers)

    return OpportunitySelectorEvidenceReport(
        schema_version=SELECTOR_EVIDENCE_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        source_rank_count=len(ranks),
        selected_count=len(selected_candidates),
        not_selected_count=max(0, len(ranks) - len(selected_candidates)),
        executable_source_count=executable_count,
        score_eligible_source_count=eligible_count,
        blocked_source_count=blocked_count,
        no_selection_reason=_no_selection_reason(ranks, selected_candidates, normalized_limit, eligible_count, executable_count),
        selected_strategy_ids=tuple(rank.strategy_id for rank in selected_candidates),
        records=records,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
        safety_flags=safety_flags,
        metadata={
            "selector_evidence": "opportunity_selector_evidence_v1",
            "scope": "read_only_no_selection_side_effects",
            "selection_limit": normalized_limit,
            "source_ranker": source_metadata.get("ranker"),
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
    )


def _coerce_ranks(
    ranking_report: CandidateRankingReport | Iterable[CandidateRankRecord],
) -> tuple[tuple[CandidateRankRecord, ...], dict[str, Any]]:
    if isinstance(ranking_report, CandidateRankingReport):
        return tuple(ranking_report.ranks), dict(ranking_report.metadata)
    ranks = tuple(ranking_report or ())
    for rank in ranks:
        if not isinstance(rank, CandidateRankRecord):
            raise TypeError("selector_evidence_expected_candidate_rank_record")
    return ranks, {}


def _evidence_record(rank: CandidateRankRecord, selected: bool) -> OpportunitySelectionEvidenceRecord:
    decision = "SELECTED" if selected else "NOT_SELECTED"
    return OpportunitySelectionEvidenceRecord(
        rank=rank.rank,
        strategy_id=rank.strategy_id,
        symbol=rank.symbol,
        direction=rank.direction,
        final_score=round(float(rank.final_score), 6),
        selected=bool(selected),
        selector_decision=decision,
        selector_reason=_selector_reason(rank, selected),
        score_eligibility=rank.score_eligibility,
        executable_candidate=rank.executable_candidate,
        blockers=tuple(rank.blockers),
        warnings=tuple(rank.warnings) + tuple(rank.directional_warnings),
        safety_flags=tuple(rank.safety_flags),
    )


def _selector_reason(rank: CandidateRankRecord, selected: bool) -> str:
    if selected:
        return "selected_score_eligible_executable_candidate"
    if rank.blockers:
        return "not_selected_blocked_candidate"
    if rank.safety_flags:
        return "not_selected_safety_flags_present"
    if rank.score_eligibility != SCORE_ELIGIBLE:
        return f"not_selected_score_eligibility_{rank.score_eligibility.lower()}"
    if not rank.executable_candidate:
        return "not_selected_not_executable_candidate"
    return "not_selected_selection_limit_or_tiebreak"


def _record_reasons(record: OpportunitySelectionEvidenceRecord) -> tuple[str, ...]:
    reasons = [record.selector_reason]
    reasons.extend(record.blockers)
    reasons.extend(record.safety_flags)
    return tuple(str(reason) for reason in reasons if reason)


def _no_selection_reason(
    ranks: tuple[CandidateRankRecord, ...],
    selected_candidates: tuple[CandidateRankRecord, ...],
    selection_limit: int,
    eligible_count: int,
    executable_count: int,
) -> str | None:
    if selected_candidates:
        return None
    if not ranks:
        return "no_ranked_candidates"
    if selection_limit <= 0:
        return "selection_limit_zero"
    if eligible_count <= 0:
        return "no_score_eligible_candidates"
    if executable_count <= 0:
        return "no_executable_candidates"
    return "all_selector_candidates_blocked"


__all__ = [
    "SELECTOR_EVIDENCE_SCHEMA_VERSION",
    "OpportunitySelectionEvidenceRecord",
    "OpportunitySelectorEvidenceReport",
    "build_opportunity_selector_evidence",
]
