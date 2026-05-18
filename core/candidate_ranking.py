"""Read-only candidate ranking engine for scored opportunities.

This module ranks OpportunityScoreRecord objects after scoring and optional
directional-balance auditing. It does not mutate scores, create synthetic
candidates, execute trades, call brokers, touch depth subscriptions, tune live
thresholds, or change dashboard behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

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
    "stale_option_ltp": 4,
    "untrusted_quote_source": 4,
    "missing_depth": 3,
    "wide_spread": 3,
    "weak_option_confirmation": 2,
}


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
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
        }


@dataclass(frozen=True)
class CandidateRankingReport:
    """Read-only ranking report for scored opportunities."""

    schema_version: int
    read_only: bool
    is_order_action: bool
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
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": self.is_order_action,
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
    directional_flags = _directional_flags(directional_balance)
    ranked_inputs = sorted(
        records,
        key=lambda record: _sort_key(record, _directional_warnings(record, directional_flags)),
    )
    ranks = tuple(
        _rank_record(index + 1, record, directional_flags)
        for index, record in enumerate(ranked_inputs)
    )

    blockers = tuple(sorted(set(blocker for rank in ranks for blocker in rank.blockers)))
    warnings = tuple(sorted(set(warning for rank in ranks for warning in rank.warnings) | set(directional_flags)))
    safety_flags = tuple(sorted(set(flag for rank in ranks for flag in rank.safety_flags)))

    return CandidateRankingReport(
        schema_version=RANKING_SCHEMA_VERSION,
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
            "source_scorer": getattr(scores, "metadata", {}).get("scorer") if isinstance(scores, OpportunityScoreReport) else None,
            "source_directional_balance": getattr(directional_balance, "metadata", {}).get("directional_balance")
            if isinstance(directional_balance, DirectionalBalanceReport)
            else None,
            "eligibility_priority": dict(ELIGIBILITY_PRIORITY),
            "bucket_priority": dict(BUCKET_PRIORITY),
        },
    )


def _rank_record(rank: int, record: OpportunityScoreRecord, directional_flags: tuple[str, ...]) -> CandidateRankRecord:
    family = direction_family(record.direction)
    directional_warnings = _directional_warnings(record, directional_flags)
    sort_key = _sort_key(record, directional_warnings)
    return CandidateRankRecord(
        rank=rank,
        strategy_id=record.strategy_id,
        symbol=record.symbol,
        direction=record.direction,
        directional_family=family,
        movement_type=record.movement_type,
        final_score=round(float(record.final_score), 6),
        bucket=record.bucket,
        score_eligibility=record.score_eligibility,
        executable_candidate=bool(record.executable_candidate and record.score_eligibility == SCORE_ELIGIBLE),
        rank_reason=_rank_reason(record, directional_warnings),
        downgrade_reasons=tuple(sorted(record.downgrade_reasons)),
        blockers=tuple(sorted(record.blockers)),
        warnings=tuple(sorted(record.warnings)),
        safety_flags=tuple(sorted(record.safety_flags)),
        directional_warnings=directional_warnings,
        sort_key=sort_key,
    )


def _sort_key(record: OpportunityScoreRecord, directional_warnings: tuple[str, ...]) -> tuple[Any, ...]:
    return (
        ELIGIBILITY_PRIORITY.get(record.score_eligibility, 99),
        _safety_severity(record),
        len(tuple(record.blockers)),
        len(tuple(record.safety_flags)),
        len(directional_warnings),
        -round(float(record.final_score), 6),
        BUCKET_PRIORITY.get(record.bucket, 99),
        str(record.symbol or ""),
        str(record.direction or ""),
        str(record.movement_type or ""),
        str(record.strategy_id or ""),
    )


def _safety_severity(record: OpportunityScoreRecord) -> int:
    values: list[int] = []
    for flag in tuple(record.safety_flags) + tuple(record.downgrade_reasons) + tuple(record.blockers):
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


def _rank_reason(record: OpportunityScoreRecord, directional_warnings: tuple[str, ...]) -> str:
    parts = [
        f"eligibility={record.score_eligibility}",
        f"bucket={record.bucket}",
        f"score={float(record.final_score):.6f}",
        f"family={direction_family(record.direction)}",
    ]
    if record.blockers:
        parts.append(f"blockers={len(record.blockers)}")
    if record.safety_flags:
        parts.append(f"safety_flags={len(record.safety_flags)}")
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


__all__ = [
    "BUCKET_PRIORITY",
    "ELIGIBILITY_PRIORITY",
    "RANKING_SCHEMA_VERSION",
    "CandidateRankRecord",
    "CandidateRankingReport",
    "rank_candidates",
]
