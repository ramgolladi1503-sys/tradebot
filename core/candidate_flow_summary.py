"""Read-only candidate flow summary for diagnostics.

This module stitches together already-computed candidate pool, classification,
scoring, and ranking reports into a single drop-off summary. It does not change
ranking, execution, or strategy behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_pool_orchestrator import CandidatePoolReport
from core.candidate_classifier import CandidateClassificationReport
from core.opportunity_scoring import OpportunityScoreReport
from core.candidate_ranking import CandidateRankingReport


@dataclass(frozen=True)
class CandidateFlowSummary:
    schema_version: int
    symbol: str
    raw_candidate_count: int
    normalized_candidate_count: int
    classified_candidate_count: int
    scored_candidate_count: int
    ranked_candidate_count: int
    executable_candidate_count: int
    near_executable_candidate_count: int
    advisory_candidate_count: int
    suppressed_candidate_count: int
    no_trade_candidate_count: int
    movement_candidate_count: int
    no_trade_suppressed_count: int
    score_drop_count: int
    rank_drop_count: int
    dominant_blockers: tuple[str, ...]
    dominant_warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "raw_candidate_count": self.raw_candidate_count,
            "normalized_candidate_count": self.normalized_candidate_count,
            "classified_candidate_count": self.classified_candidate_count,
            "scored_candidate_count": self.scored_candidate_count,
            "ranked_candidate_count": self.ranked_candidate_count,
            "executable_candidate_count": self.executable_candidate_count,
            "near_executable_candidate_count": self.near_executable_candidate_count,
            "advisory_candidate_count": self.advisory_candidate_count,
            "suppressed_candidate_count": self.suppressed_candidate_count,
            "no_trade_candidate_count": self.no_trade_candidate_count,
            "movement_candidate_count": self.movement_candidate_count,
            "no_trade_suppressed_count": self.no_trade_suppressed_count,
            "score_drop_count": self.score_drop_count,
            "rank_drop_count": self.rank_drop_count,
            "dominant_blockers": list(self.dominant_blockers),
            "dominant_warnings": list(self.dominant_warnings),
            "metadata": dict(self.metadata),
        }


def build_candidate_flow_summary(
    candidate_pool: CandidatePoolReport,
    classification: CandidateClassificationReport,
    scoring: OpportunityScoreReport,
    ranking: CandidateRankingReport,
) -> CandidateFlowSummary:
    raw_candidate_count = int(candidate_pool.movement_candidate_count)
    classified_candidate_count = int(classification.candidate_count)
    scored_candidate_count = int(scoring.score_count)
    ranked_candidate_count = int(ranking.rank_count)
    no_trade_suppressed_count = max(
        0,
        int(candidate_pool.eligible_candidate_count_before_suppression) - int(candidate_pool.report_executable_eligible_count),
    )
    score_drop_count = max(0, raw_candidate_count - scored_candidate_count)
    rank_drop_count = max(0, scored_candidate_count - ranked_candidate_count)

    dominant_blockers = tuple(sorted(set(_top_set(candidate_pool.blockers, classification.blockers, scoring.blockers, ranking.blockers))))
    dominant_warnings = tuple(sorted(set(_top_set(candidate_pool.warnings, classification.warnings, scoring.warnings, ranking.warnings))))

    return CandidateFlowSummary(
        schema_version=1,
        symbol=candidate_pool.symbol,
        raw_candidate_count=raw_candidate_count,
        normalized_candidate_count=int(classification.candidate_count),
        classified_candidate_count=classified_candidate_count,
        scored_candidate_count=scored_candidate_count,
        ranked_candidate_count=ranked_candidate_count,
        executable_candidate_count=int(classification.executable_count),
        near_executable_candidate_count=int(classification.near_executable_count),
        advisory_candidate_count=int(classification.advisory_count),
        suppressed_candidate_count=int(classification.suppressed_count),
        no_trade_candidate_count=int(classification.no_trade_count),
        movement_candidate_count=int(candidate_pool.movement_candidate_count),
        no_trade_suppressed_count=no_trade_suppressed_count,
        score_drop_count=score_drop_count,
        rank_drop_count=rank_drop_count,
        dominant_blockers=dominant_blockers,
        dominant_warnings=dominant_warnings,
        metadata={
            "flow_summary": "candidate_flow_summary_v1",
            "candidate_pool_executable_before_suppression": int(candidate_pool.eligible_candidate_count_before_suppression),
            "candidate_pool_executable_after_suppression": int(candidate_pool.report_executable_eligible_count),
            "candidate_pool_failed_generators": int(candidate_pool.failed_generator_count),
            "classification_metadata": dict(classification.metadata),
            "scoring_metadata": dict(scoring.metadata),
            "ranking_metadata": dict(ranking.metadata),
        },
    )


def _top_set(*values: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for item in values:
        for text in item:
            normalized = str(text or "").strip()
            if normalized and normalized not in out:
                out.append(normalized)
    return out


__all__ = ["CandidateFlowSummary", "build_candidate_flow_summary"]
