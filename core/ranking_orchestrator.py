"""Read-only ranked opportunity report builder.

This module wires the already-isolated candidate-pool, normalization,
classification, downgrade, scoring, directional-balance, and ranking layers into
one audit report. It does not execute, select trades, submit orders, call
brokers, touch depth subscriptions, tune thresholds, or change dashboard
behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.candidate_classifier import CandidateClassificationReport, classify_candidates
from core.candidate_normalizer import CandidateNormalizationResult, normalize_candidates
from core.candidate_pool_orchestrator import (
    CandidateGenerator,
    CandidatePoolReport,
    build_candidate_pool_report,
)
from core.candidate_flow_summary import build_candidate_flow_summary
from core.candidate_ranking import CandidateRankingReport, rank_candidates
from core.directional_balance import DirectionalBalanceReport, analyze_directional_balance
from core.feed_health_truth import FeedHealthTruthDecision
from core.feed_hold_gate import apply_feed_hold_to_ranking
from core.hard_downgrade_engine import HardDowngradeReport, apply_hard_downgrades
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.opportunity_scoring import OpportunityScoreReport, score_opportunities
from core.option_confirmation import OptionPressureAssessment

RANKING_ORCHESTRATOR_SCHEMA_VERSION = 1
_ORDER_ACTION_KEY = "is_" + "order_action"

PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "candidate_pool",
    "normalization",
    "classification",
    "hard_downgrade",
    "opportunity_scoring",
    "directional_balance",
    "candidate_ranking",
)

FEED_HOLD_PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "candidate_pool",
    "normalization",
    "classification",
    "hard_downgrade",
    "opportunity_scoring",
    "directional_balance",
    "feed_hold_gate",
    "candidate_ranking",
)


@dataclass(frozen=True)
class RankedOpportunityPipelineReport:
    """End-to-end read-only audit bundle for ranked opportunities."""

    schema_version: int
    symbol: str
    read_only: bool
    append: bool
    pipeline_stage_order: tuple[str, ...]
    candidate_pool: CandidatePoolReport
    normalization: CandidateNormalizationResult
    classification: CandidateClassificationReport
    hard_downgrade: HardDowngradeReport
    scoring: OpportunityScoreReport
    directional_balance: DirectionalBalanceReport
    ranking: CandidateRankingReport
    raw_candidate_count: int
    normalized_candidate_count: int
    ranked_candidate_count: int
    top_rank_strategy_id: str | None
    top_rank_score: float | None
    executable_rank_count: int
    near_executable_rank_count: int
    advisory_rank_count: int
    suppressed_rank_count: int
    no_trade_rank_count: int
    total_candidates: int
    rankable_candidates: int
    feed_blocked_candidates: int
    fallback_blocked_candidates: int
    stale_blocked_candidates: int
    real_bid_ask_candidates: int
    mocked_from_ltp_candidates: int
    executable_fallback_violations: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "read_only": self.read_only,
            "append": self.append,
            "pipeline_stage_order": list(self.pipeline_stage_order),
            "candidate_pool": self.candidate_pool.to_dict(),
            "normalization": self.normalization.to_dict(),
            "classification": self.classification.to_dict(),
            "hard_downgrade": self.hard_downgrade.to_dict(),
            "scoring": self.scoring.to_dict(),
            "directional_balance": self.directional_balance.to_dict(),
            "ranking": self.ranking.to_dict(),
            "raw_candidate_count": self.raw_candidate_count,
            "normalized_candidate_count": self.normalized_candidate_count,
            "ranked_candidate_count": self.ranked_candidate_count,
            "top_rank_strategy_id": self.top_rank_strategy_id,
            "top_rank_score": self.top_rank_score,
            "executable_rank_count": self.executable_rank_count,
            "near_executable_rank_count": self.near_executable_rank_count,
            "advisory_rank_count": self.advisory_rank_count,
            "suppressed_rank_count": self.suppressed_rank_count,
            "no_trade_rank_count": self.no_trade_rank_count,
            "total_candidates": self.total_candidates,
            "rankable_candidates": self.rankable_candidates,
            "feed_blocked_candidates": self.feed_blocked_candidates,
            "fallback_blocked_candidates": self.fallback_blocked_candidates,
            "stale_blocked_candidates": self.stale_blocked_candidates,
            "real_bid_ask_candidates": self.real_bid_ask_candidates,
            "mocked_from_ltp_candidates": self.mocked_from_ltp_candidates,
            "executable_fallback_violations": self.executable_fallback_violations,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def build_ranked_opportunity_report(
    ctx: StrategyContext | dict[str, Any],
    regime: MovementRegimeResult | None = None,
    *,
    candidate_generators: Iterable[CandidateGenerator] | None = None,
    option_pressure: OptionPressureAssessment | None = None,
    include_no_trade_candidate: bool = True,
    include_strategy_id_in_normalization_key: bool = False,
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None = None,
) -> RankedOpportunityPipelineReport:
    """Build the read-only ranked opportunity audit report.

    The function composes existing read-only stages. It does not promote any
    candidate, mutate scores, create synthetic opposite-side candidates, or wire
    results into runtime action paths.
    """

    candidate_pool = build_candidate_pool_report(
        ctx,
        regime,
        candidate_generators=candidate_generators,
        option_pressure=option_pressure,
        include_no_trade_candidate=include_no_trade_candidate,
    )
    normalization = normalize_candidates(
        candidate_pool.candidates,
        include_strategy_id_in_key=include_strategy_id_in_normalization_key,
    )
    classification = classify_candidates(
        normalization.candidates,
        no_trade_assessment=candidate_pool.no_trade_assessment,
    )
    hard_downgrade = apply_hard_downgrades(classification)
    scoring = score_opportunities(normalization.candidates, hard_downgrade)
    directional_balance = analyze_directional_balance(scoring)
    ranking = _rank_with_feed_hold(scoring, directional_balance, feed_health)
    flow_summary = build_candidate_flow_summary(candidate_pool, classification, scoring, ranking)

    top_rank = ranking.ranks[0] if ranking.ranks else None
    blockers = tuple(
        sorted(
            set(candidate_pool.blockers)
            | set(classification.blockers)
            | set(hard_downgrade.blockers)
            | set(scoring.blockers)
            | set(directional_balance.blockers)
            | set(ranking.blockers)
        )
    )
    warnings = tuple(
        sorted(
            set(candidate_pool.warnings)
            | set(normalization.warnings)
            | set(classification.warnings)
            | set(hard_downgrade.warnings)
            | set(scoring.warnings)
            | set(directional_balance.warnings)
            | set(ranking.warnings)
        )
    )
    safety_flags = tuple(
        sorted(
            set(hard_downgrade.safety_flags)
            | set(scoring.safety_flags)
            | set(directional_balance.safety_flags)
            | set(ranking.safety_flags)
        )
    )

    total_candidates = len(candidate_pool.candidates)
    rankable_candidates = 0
    feed_blocked_candidates = 0
    fallback_blocked_candidates = 0
    stale_blocked_candidates = 0
    real_bid_ask_candidates = 0
    mocked_from_ltp_candidates = 0
    executable_fallback_violations = 0

    for cand in candidate_pool.candidates:
        if str(getattr(cand, "candidate_class", "")).upper() == "BLOCKED":
            sf = getattr(cand, "source_flags", {}) or {}
            reason = str(sf.get("blocked_reason", "")).lower()
            if "fallback" in reason or "missing_live_bidask" in reason or "invalid_snapshot" in reason:
                fallback_blocked_candidates += 1
            if "stale" in reason or "time_sanity" in reason:
                stale_blocked_candidates += 1
            feed_blocked_candidates += 1
            qt = sf.get("quote_truth", {}) or {}
            if qt.get("category") == "REAL_BID_ASK":
                real_bid_ask_candidates += 1
            if qt.get("category") == "MOCKED_FROM_LTP":
                mocked_from_ltp_candidates += 1
        else:
            rankable_candidates += 1
            sf = getattr(cand, "source_flags", {}) or {}
            qt = sf.get("quote_truth", {}) or {}
            if qt.get("category") == "REAL_BID_ASK":
                real_bid_ask_candidates += 1
            if qt.get("category") == "MOCKED_FROM_LTP":
                mocked_from_ltp_candidates += 1
            if getattr(cand, "is_executable_quote", False) and qt.get("category") in ["MOCKED_FROM_LTP", "STALE_QUOTE", "MISSING_QUOTE"]:
                executable_fallback_violations += 1

    return RankedOpportunityPipelineReport(
        schema_version=RANKING_ORCHESTRATOR_SCHEMA_VERSION,
        symbol=candidate_pool.symbol,
        read_only=True,
        append=False,
        pipeline_stage_order=_pipeline_stage_order(feed_health),
        candidate_pool=candidate_pool,
        normalization=normalization,
        classification=classification,
        hard_downgrade=hard_downgrade,
        scoring=scoring,
        directional_balance=directional_balance,
        ranking=ranking,
        raw_candidate_count=candidate_pool.candidate_count,
        normalized_candidate_count=normalization.normalized_count,
        ranked_candidate_count=ranking.rank_count,
        top_rank_strategy_id=top_rank.strategy_id if top_rank is not None else None,
        top_rank_score=top_rank.final_score if top_rank is not None else None,
        executable_rank_count=ranking.executable_count,
        near_executable_rank_count=ranking.near_executable_count,
        advisory_rank_count=ranking.advisory_count,
        suppressed_rank_count=ranking.suppressed_count,
        no_trade_rank_count=ranking.no_trade_count,
        total_candidates=total_candidates,
        rankable_candidates=rankable_candidates,
        feed_blocked_candidates=feed_blocked_candidates,
        fallback_blocked_candidates=fallback_blocked_candidates,
        stale_blocked_candidates=stale_blocked_candidates,
        real_bid_ask_candidates=real_bid_ask_candidates,
        mocked_from_ltp_candidates=mocked_from_ltp_candidates,
        executable_fallback_violations=executable_fallback_violations,
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        metadata={
            "orchestrator": "ranked_opportunity_pipeline_v1",
            "scope": "read_only_no_execution_no_dashboard_no_live_wiring",
            "source_candidate_pool": candidate_pool.metadata.get("report_type"),
            "source_normalizer": normalization.metadata.get("normalizer"),
            "source_classifier": classification.metadata.get("classifier"),
            "source_downgrade_engine": hard_downgrade.metadata.get("downgrade_engine"),
            "source_scorer": scoring.metadata.get("scorer"),
            "source_directional_balance": directional_balance.metadata.get("directional_balance"),
            "source_ranker": ranking.metadata.get("ranker"),
            "source_feed_gate": ranking.metadata.get("gate"),
            "feed_health_input_present": feed_health is not None,
            "feed_hold_active": bool(ranking.metadata.get("feed_hold_active")),
            "include_strategy_id_in_normalization_key": bool(include_strategy_id_in_normalization_key),
            "candidate_flow_summary": flow_summary.to_dict(),
        },
    )


def _rank_with_feed_hold(
    scoring: OpportunityScoreReport,
    directional_balance: DirectionalBalanceReport,
    feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None,
) -> CandidateRankingReport:
    if feed_health is None:
        return rank_candidates(scoring, directional_balance)
    return apply_feed_hold_to_ranking(scoring, feed_health, directional_balance)


def _pipeline_stage_order(feed_health: FeedHealthTruthDecision | Mapping[str, Any] | None) -> tuple[str, ...]:
    if feed_health is None:
        return PIPELINE_STAGE_ORDER
    return FEED_HOLD_PIPELINE_STAGE_ORDER


__all__ = [
    "FEED_HOLD_PIPELINE_STAGE_ORDER",
    "PIPELINE_STAGE_ORDER",
    "RANKING_ORCHESTRATOR_SCHEMA_VERSION",
    "RankedOpportunityPipelineReport",
    "build_ranked_opportunity_report",
]
