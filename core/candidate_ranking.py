"""Read-only candidate ranking engine for scored opportunities.

This module ranks OpportunityScoreRecord objects after scoring and optional
directional-balance auditing. It does not mutate scores, create synthetic
candidates, execute trades, call brokers, touch depth subscriptions, tune live
thresholds, or change dashboard behavior.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Dict

from core.feed_risk_truth import FEED_RISK_TOKENS, classify_feed_risk_reasons

@dataclass
class FeedRiskVerdict:
    is_risk: bool
    reasons: list[str]

from core.candidate_outcome_contract import CandidateOutcomeContract

from core.directional_balance import DirectionalBalanceReport, direction_family
from core.opportunity_scoring import (
    ADVISORY_ONLY,
    NEEDS_CONFIRMATION,
    NO_TRADE_ONLY,
    SCORE_ELIGIBLE,
    SUPPRESSED_BY_DOWNGRADE,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)

RANKING_SCHEMA_VERSION = 1
RANKING_FEED_RISK_SUPPRESSION_REASON = "ranking_feed_risk_suppression"
RANKING_FEED_RISK_SAFETY_FLAG = "ranking_feed_risk"

ELIGIBILITY_PRIORITY: dict[str, int] = {
    SCORE_ELIGIBLE: 0,
    NEEDS_CONFIRMATION: 1,
    ADVISORY_ONLY: 2,
    SUPPRESSED_BY_DOWNGRADE: 3,
    NO_TRADE_ONLY: 4,
}

BUCKET_PRIORITY: dict[str, int] = {
    "EXECUTABLE_CANDIDATE": 0,
    "NEAR_EXECUTABLE_CANDIDATE": 1,
    "ADVISORY_CANDIDATE": 2,
    "SUPPRESSED_CANDIDATE": 3,
    "NO_TRADE_CANDIDATE": 4,
}

SAFETY_FLAG_PRIORITY: dict[str, int] = {
    "broker_unavailable": 5,
    "market_closed": 5,
    "fallback_data": 4,
    "fallback_quote_data": 4,
    "ranking_feed_risk": 4,
    "stale_feed": 4,
    "stale_option_ltp": 4,
    "untrusted_quote_source": 4,
    "no_live_option_feed": 4,
    "subscription_failed": 4,
    "missing_depth": 3,
    "wide_spread": 3,
    "weak_option_confirmation": 2,
}

def is_feed_risk_candidate(candidate: dict[str, Any] | OpportunityScoreRecord) -> FeedRiskVerdict:
    """Central helper to detect if a candidate has feed/data quality risks."""
    if isinstance(candidate, dict):
        reasons = classify_feed_risk_reasons(
            safety_flags=tuple(candidate.get("safety_flags", [])),
            downgrade_reasons=tuple(candidate.get("downgrade_reasons", [])),
            blockers=tuple(candidate.get("blockers", [])),
            warnings=tuple(candidate.get("warnings", [])),
            candidate_class=str(candidate.get("candidate_class", "")).strip().lower(),
        )
    else:
        reasons = tuple(getattr(candidate, "feed_risk_reasons", ()) or ())
        if not reasons:
            reasons = classify_feed_risk_reasons(
                safety_flags=tuple(candidate.safety_flags),
                downgrade_reasons=tuple(candidate.downgrade_reasons),
                blockers=tuple(candidate.blockers),
                warnings=tuple(candidate.warnings),
            )

    return FeedRiskVerdict(is_risk=bool(reasons), reasons=list(reasons))


@dataclass(frozen=True)
class CandidateRankRecord:
    """Ranked view of one scored candidate."""

    rank: int
    strategy_id: str
    symbol: str
    direction: str
    directional_family: str
    movement_type: str
    final_score: float
    bucket: str
    score_eligibility: str
    executable_candidate: bool
    rank_reason: str
    downgrade_reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    directional_warnings: tuple[str, ...]
    sort_key: tuple[Any, ...]
    candidate_id: str = ""
    lineage_id: str = ""
    outcome_contract: Optional[CandidateOutcomeContract] = None

    @property
    def probability_ui_label(self) -> str:
        if (
            self.outcome_contract
            and self.outcome_contract.prediction_event
            and self.outcome_contract.prediction_horizon_minutes
            and self.outcome_contract.calibration_source
        ):
            return "Ranking score"
        return "Setup score"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "candidate_id": getattr(self, "candidate_id", self.strategy_id),
            "lineage_id": getattr(self, "lineage_id", getattr(self, "candidate_id", self.strategy_id)),
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "directional_family": self.directional_family,
            "movement_type": self.movement_type,
            "final_score": self.final_score,
            "bucket": self.bucket,
            "score_eligibility": self.score_eligibility,
            "executable_candidate": self.executable_candidate,
            "rank_reason": self.rank_reason,
            "downgrade_reasons": list(self.downgrade_reasons),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "directional_warnings": list(self.directional_warnings),
            "sort_key": list(self.sort_key),
            "probability_ui_label": self.probability_ui_label,
            "outcome_contract": self.outcome_contract.to_dict() if self.outcome_contract else None,
        }


@dataclass(frozen=True)
class CandidateRankingReport:
    """Read-only ranking report for scored opportunities."""

    schema_version: int
    read_only: bool
    is_order_action: bool  # is_order_action=false
    append: bool
    rank_count: int
    executable_count: int
    near_executable_count: int
    advisory_count: int
    suppressed_count: int
    no_trade_count: int
    ranks: tuple[CandidateRankRecord, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    directional_imbalance_flags: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    ranked_report_id: str = field(default_factory=lambda: f"ranking-{uuid.uuid4()}")
    generated_epoch: float = field(default_factory=time.time)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ranked_report_id": getattr(self, "ranked_report_id", "unknown_report_id"),
            "read_only": self.read_only,
            "is_order_action": False,
            "append": self.append,
            "rank_count": self.rank_count,
            "executable_count": self.executable_count,
            "near_executable_count": self.near_executable_count,
            "advisory_count": self.advisory_count,
            "suppressed_count": self.suppressed_count,
            "no_trade_count": self.no_trade_count,
            "ranks": [rank.to_dict() for rank in self.ranks],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "directional_imbalance_flags": list(self.directional_imbalance_flags),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def rank_candidates(
    scores: OpportunityScoreReport | Iterable[OpportunityScoreRecord],
    directional_balance: DirectionalBalanceReport | None = None,
) -> CandidateRankingReport:
    """Rank scored candidates without changing score records or execution state."""

    records = _coerce_scores(scores)
    source_metadata = _source_score_metadata(scores)
    directional_flags = _directional_flags(directional_balance)
    feed_risk_map = {id(record): _should_suppress_for_feed_risk(record) for record in records}
    ranked_inputs = sorted(
        records,
        key=lambda record: _sort_key(
            record,
            _directional_warnings(record, directional_flags),
            feed_risk_suppressed=feed_risk_map.get(id(record), False),
        ),
    )
    import uuid
    import time
    report_id = str(uuid.uuid4())
    epoch = time.time()

    ranks = tuple(
        _rank_record(index + 1, record, directional_flags, epoch, feed_risk_suppressed=feed_risk_map.get(id(record), False))
        for index, record in enumerate(ranked_inputs)
    )

    blockers = tuple(sorted(set(blocker for rank in ranks for blocker in rank.blockers)))
    warnings = tuple(sorted(set(warning for rank in ranks for warning in rank.warnings) | set(directional_flags)))
    safety_flags = tuple(sorted(set(flag for rank in ranks for flag in rank.safety_flags)))
    feed_risk_suppressed_count = sum(
        1 for rank in ranks if RANKING_FEED_RISK_SUPPRESSION_REASON in rank.downgrade_reasons
    )

    return CandidateRankingReport(
        schema_version=RANKING_SCHEMA_VERSION,
        ranked_report_id=report_id,
        generated_epoch=epoch,
        read_only=True,
        is_order_action=False,
        append=False,
        rank_count=len(ranks),
        executable_count=sum(1 for rank in ranks if rank.score_eligibility == SCORE_ELIGIBLE),
        near_executable_count=sum(1 for rank in ranks if rank.score_eligibility == NEEDS_CONFIRMATION),
        advisory_count=sum(1 for rank in ranks if rank.score_eligibility == ADVISORY_ONLY),
        suppressed_count=sum(1 for rank in ranks if rank.score_eligibility == SUPPRESSED_BY_DOWNGRADE),
        no_trade_count=sum(1 for rank in ranks if rank.score_eligibility == NO_TRADE_ONLY),
        ranks=ranks,
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        directional_imbalance_flags=directional_flags,
        metadata={
            "ranker": "candidate_ranking_v1",
            "scope": "read_only_no_execution_no_score_mutation",
            "source_scorer": source_metadata.get("scorer"),
            "source_directional_balance": getattr(directional_balance, "metadata", {}).get("directional_balance")
            if isinstance(directional_balance, DirectionalBalanceReport)
            else None,
            "eligibility_priority": dict(ELIGIBILITY_PRIORITY),
            "bucket_priority": dict(BUCKET_PRIORITY),
            "feed_risk_suppression": "enabled",
            "feed_risk_suppressed_count": feed_risk_suppressed_count,
            "ranking_sort_score_source": "opportunity_final_score",
            "profile_sort_cutover_enabled": False,
            "source_scoring_profile_applied": bool(source_metadata.get("scoring_profile_applied", False)),
            "source_scoring_profile_name": source_metadata.get("scoring_profile_name"),
            "source_component_weights": dict(source_metadata.get("component_weights") or {}),
            "source_base_component_weights": dict(source_metadata.get("base_component_weights") or {}),
        },
    )


def _rank_record(
    rank: int,
    record: OpportunityScoreRecord,
    directional_flags: tuple[str, ...],
    generated_epoch: float,
    *,
    feed_risk_suppressed: bool = False,
) -> CandidateRankRecord:
    family = direction_family(record.direction)
    directional_warnings = _directional_warnings(record, directional_flags)
    sort_key = _sort_key(record, directional_warnings, feed_risk_suppressed=feed_risk_suppressed)
    score_eligibility = _rank_score_eligibility(record, feed_risk_suppressed)
    bucket = _rank_bucket(record, feed_risk_suppressed)

    candidate_id = getattr(record, "candidate_id", None) or getattr(record.outcome_contract, "candidate_id", None) or f"{record.symbol}-{record.strategy_id}-{record.movement_type}-{record.direction}-{generated_epoch}"
    lineage_id = getattr(record, "lineage_id", None) or getattr(record.outcome_contract, "lineage_id", None) or candidate_id

    return CandidateRankRecord(
        rank=rank,
        candidate_id=str(candidate_id),
        lineage_id=str(lineage_id),
        strategy_id=record.strategy_id,
        symbol=record.symbol,
        direction=record.direction,
        directional_family=family,
        movement_type=record.movement_type,
        final_score=round(float(record.final_score), 6),
        bucket=bucket,
        score_eligibility=score_eligibility,
        executable_candidate=bool(record.executable_candidate and score_eligibility == SCORE_ELIGIBLE),
        rank_reason=_rank_reason(record, directional_warnings, feed_risk_suppressed=feed_risk_suppressed),
        downgrade_reasons=_rank_downgrade_reasons(record, feed_risk_suppressed),
        blockers=tuple(sorted(record.blockers)),
        warnings=tuple(sorted(record.warnings)),
        safety_flags=_rank_safety_flags(record, feed_risk_suppressed),
        directional_warnings=directional_warnings,
        sort_key=sort_key,
        outcome_contract=record.outcome_contract,
    )


def _sort_key(
    record: OpportunityScoreRecord,
    directional_warnings: tuple[str, ...],
    *,
    feed_risk_suppressed: bool = False,
) -> tuple[Any, ...]:
    score_eligibility = _rank_score_eligibility(record, feed_risk_suppressed)
    bucket = _rank_bucket(record, feed_risk_suppressed)
    safety_flags = _rank_safety_flags(record, feed_risk_suppressed)
    downgrade_reasons = _rank_downgrade_reasons(record, feed_risk_suppressed)
    return (
        ELIGIBILITY_PRIORITY.get(score_eligibility, 99),
        _safety_severity(record, safety_flags=safety_flags, downgrade_reasons=downgrade_reasons),
        len(tuple(record.blockers)),
        len(safety_flags),
        len(directional_warnings),
        -round(float(record.final_score), 6),
        BUCKET_PRIORITY.get(bucket, 99),
        str(record.symbol or ""),
        str(record.direction or ""),
        str(record.movement_type or ""),
        str(record.strategy_id or ""),
    )


def _should_suppress_for_feed_risk(record: OpportunityScoreRecord) -> bool:
    if record.score_eligibility not in {SCORE_ELIGIBLE, NEEDS_CONFIRMATION}:
        return False
    if bool(getattr(record, "feed_risk_precomputed", False)):
        precomputed = getattr(record, "feed_risk_reasons", ())
        return bool(tuple(precomputed))
    return _has_feed_risk(record)


def _has_feed_risk(record: OpportunityScoreRecord) -> bool:
    return is_feed_risk_candidate(record).is_risk


def _rank_score_eligibility(record: OpportunityScoreRecord, feed_risk_suppressed: bool) -> str:
    if feed_risk_suppressed:
        return SUPPRESSED_BY_DOWNGRADE
    return record.score_eligibility


def _rank_bucket(record: OpportunityScoreRecord, feed_risk_suppressed: bool) -> str:
    if feed_risk_suppressed:
        return "SUPPRESSED_CANDIDATE"
    return record.bucket


def _rank_downgrade_reasons(
    record: OpportunityScoreRecord,
    feed_risk_suppressed: bool,
) -> tuple[str, ...]:
    reasons = set(str(reason).strip() for reason in record.downgrade_reasons if str(reason).strip())
    if feed_risk_suppressed:
        reasons.add(RANKING_FEED_RISK_SUPPRESSION_REASON)
    return tuple(sorted(reasons))


def _rank_safety_flags(
    record: OpportunityScoreRecord,
    feed_risk_suppressed: bool,
) -> tuple[str, ...]:
    flags = set(str(flag).strip() for flag in record.safety_flags if str(flag).strip())
    if feed_risk_suppressed:
        flags.add(RANKING_FEED_RISK_SAFETY_FLAG)
    return tuple(sorted(flags))


def _safety_severity(
    record: OpportunityScoreRecord,
    *,
    safety_flags: tuple[str, ...] | None = None,
    downgrade_reasons: tuple[str, ...] | None = None,
) -> int:
    values: list[int] = []
    flag_values = tuple(record.safety_flags) if safety_flags is None else tuple(safety_flags)
    reason_values = tuple(record.downgrade_reasons) if downgrade_reasons is None else tuple(downgrade_reasons)
    for flag in flag_values + reason_values + tuple(record.blockers):
        normalized = str(flag or "").strip().lower()
        values.append(SAFETY_FLAG_PRIORITY.get(normalized, 1 if normalized else 0))
    return max(values, default=0)


def _directional_flags(directional_balance: DirectionalBalanceReport | None) -> tuple[str, ...]:
    if directional_balance is None:
        return ()
    if not isinstance(directional_balance, DirectionalBalanceReport):
        raise TypeError("candidate_ranking_expected_directional_balance_report")
    return tuple(sorted(str(flag) for flag in directional_balance.imbalance_flags))


def _directional_warnings(record: OpportunityScoreRecord, directional_flags: tuple[str, ...]) -> tuple[str, ...]:
    family = direction_family(record.direction)
    warnings: set[str] = set()
    flags = set(directional_flags)
    if family == "BULLISH":
        for flag in (
            "missing_bearish_candidate_coverage",
            "no_score_eligible_bearish_candidates",
            "bullish_score_concentration",
        ):
            if flag in flags:
                warnings.add(f"directional_balance_{flag}")
    elif family == "BEARISH":
        for flag in (
            "missing_bullish_candidate_coverage",
            "no_score_eligible_bullish_candidates",
            "bearish_score_concentration",
        ):
            if flag in flags:
                warnings.add(f"directional_balance_{flag}")
    elif family == "NO_TRADE":
        if "missing_directional_candidate_coverage" in flags:
            warnings.add("directional_balance_missing_directional_candidate_coverage")
    else:
        if "missing_directional_candidate_coverage" in flags:
            warnings.add("directional_balance_missing_directional_candidate_coverage")
    if family == "BULLISH" and "bullish_side_fully_suppressed" in flags:
        warnings.add("directional_balance_bullish_side_fully_suppressed")
    if family == "BEARISH" and "bearish_side_fully_suppressed" in flags:
        warnings.add("directional_balance_bearish_side_fully_suppressed")
    return tuple(sorted(warnings))


def _rank_reason(
    record: OpportunityScoreRecord,
    directional_warnings: tuple[str, ...],
    *,
    feed_risk_suppressed: bool = False,
) -> str:
    score_eligibility = _rank_score_eligibility(record, feed_risk_suppressed)
    bucket = _rank_bucket(record, feed_risk_suppressed)
    safety_flags = _rank_safety_flags(record, feed_risk_suppressed)
    parts = [
        f"eligibility={score_eligibility}",
        f"bucket={bucket}",
        f"score={float(record.final_score):.6f}",
        f"family={direction_family(record.direction)}",
    ]
    if feed_risk_suppressed:
        parts.append("feed_risk_suppressed=true")
    if record.blockers:
        parts.append(f"blockers={len(record.blockers)}")
    if safety_flags:
        parts.append(f"safety_flags={len(safety_flags)}")
    if directional_warnings:
        parts.append(f"directional_warnings={len(directional_warnings)}")
    return "; ".join(parts)


def _coerce_scores(scores: OpportunityScoreReport | Iterable[OpportunityScoreRecord]) -> tuple[OpportunityScoreRecord, ...]:
    if isinstance(scores, OpportunityScoreReport):
        return tuple(scores.scores)
    records = tuple(scores or ())
    for record in records:
        if not isinstance(record, OpportunityScoreRecord):
            raise TypeError("candidate_ranking_expected_opportunity_score_record")
    return records


def _source_score_metadata(scores: OpportunityScoreReport | Iterable[OpportunityScoreRecord]) -> dict[str, Any]:
    if isinstance(scores, OpportunityScoreReport):
        return dict(scores.metadata or {})
    return {}


__all__ = [
    "BUCKET_PRIORITY",
    "ELIGIBILITY_PRIORITY",
    "FEED_RISK_TOKENS",
    "RANKING_FEED_RISK_SAFETY_FLAG",
    "RANKING_FEED_RISK_SUPPRESSION_REASON",
    "RANKING_SCHEMA_VERSION",
    "CandidateRankRecord",
    "CandidateRankingReport",
    "FeedRiskVerdict",
    "is_feed_risk_candidate",
    "rank_candidates",
]
