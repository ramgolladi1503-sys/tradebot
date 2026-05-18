"""Read-only directional balance audit for opportunity scores.

This module detects bullish-only / bearish-only candidate coverage before future
ranking work. It does not create synthetic trades, alter scores, rank candidates,
submit orders, call brokers, touch depth subscriptions, tune thresholds, or change
dashboard behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from core.opportunity_scoring import (
    ADVISORY_ONLY,
    NEEDS_CONFIRMATION,
    NO_TRADE_ONLY,
    SCORE_ELIGIBLE,
    SUPPRESSED_BY_DOWNGRADE,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)

DIRECTIONAL_BALANCE_SCHEMA_VERSION = 1

DirectionFamily = Literal["BULLISH", "BEARISH", "NO_TRADE", "OTHER"]
CoverageState = Literal[
    "BALANCED_DIRECTIONAL_COVERAGE",
    "BULLISH_ONLY_COVERAGE",
    "BEARISH_ONLY_COVERAGE",
    "NO_DIRECTIONAL_COVERAGE",
    "MIXED_WITH_OTHER_COVERAGE",
]

BULLISH_DIRECTIONS: frozenset[str] = frozenset({"BUY_CALL", "LONG_CALL", "CALL", "CE", "BULLISH"})
BEARISH_DIRECTIONS: frozenset[str] = frozenset({"BUY_PUT", "LONG_PUT", "PUT", "PE", "BEARISH"})
NO_TRADE_DIRECTIONS: frozenset[str] = frozenset({"NO_TRADE", "NONE", "SKIP"})


@dataclass(frozen=True)
class DirectionFamilySummary:
    """Aggregated score evidence for one directional family."""

    family: DirectionFamily
    directions: tuple[str, ...]
    score_count: int
    score_eligible_count: int
    needs_confirmation_count: int
    advisory_count: int
    suppressed_count: int
    no_trade_count: int
    max_final_score: float
    avg_final_score: float
    total_final_score: float
    top_strategy_id: str | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "directions": list(self.directions),
            "score_count": self.score_count,
            "score_eligible_count": self.score_eligible_count,
            "needs_confirmation_count": self.needs_confirmation_count,
            "advisory_count": self.advisory_count,
            "suppressed_count": self.suppressed_count,
            "no_trade_count": self.no_trade_count,
            "max_final_score": self.max_final_score,
            "avg_final_score": self.avg_final_score,
            "total_final_score": self.total_final_score,
            "top_strategy_id": self.top_strategy_id,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
        }


@dataclass(frozen=True)
class DirectionalBalanceReport:
    """Read-only directional coverage audit for scored opportunities."""

    schema_version: int
    read_only: bool
    is_order_action: bool
    append: bool
    score_count: int
    directional_score_count: int
    bullish_count: int
    bearish_count: int
    no_trade_count: int
    other_count: int
    coverage_state: CoverageState
    imbalance_flags: tuple[str, ...]
    recommendations: tuple[str, ...]
    family_summaries: tuple[DirectionFamilySummary, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": self.is_order_action,
            "append": self.append,
            "score_count": self.score_count,
            "directional_score_count": self.directional_score_count,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "no_trade_count": self.no_trade_count,
            "other_count": self.other_count,
            "coverage_state": self.coverage_state,
            "imbalance_flags": list(self.imbalance_flags),
            "recommendations": list(self.recommendations),
            "family_summaries": [summary.to_dict() for summary in self.family_summaries],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def analyze_directional_balance(
    scores: OpportunityScoreReport | Iterable[OpportunityScoreRecord],
) -> DirectionalBalanceReport:
    """Analyze bullish/bearish/no-trade score coverage without changing scores."""

    records = _coerce_scores(scores)
    groups: dict[DirectionFamily, list[OpportunityScoreRecord]] = {
        "BULLISH": [],
        "BEARISH": [],
        "NO_TRADE": [],
        "OTHER": [],
    }
    for record in records:
        groups[direction_family(record.direction)].append(record)

    summaries = tuple(_summary_for_family(family, tuple(groups[family])) for family in ("BULLISH", "BEARISH", "NO_TRADE", "OTHER"))
    bullish_count = len(groups["BULLISH"])
    bearish_count = len(groups["BEARISH"])
    no_trade_count = len(groups["NO_TRADE"])
    other_count = len(groups["OTHER"])
    coverage_state = _coverage_state(bullish_count, bearish_count, other_count)
    imbalance_flags = _imbalance_flags(groups)
    recommendations = _recommendations(coverage_state, imbalance_flags)

    blockers = tuple(sorted(set(blocker for record in records for blocker in record.blockers)))
    warnings = tuple(sorted(set(warning for record in records for warning in record.warnings)))
    safety_flags = tuple(sorted(set(flag for record in records for flag in record.safety_flags)))

    return DirectionalBalanceReport(
        schema_version=DIRECTIONAL_BALANCE_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=len(records),
        directional_score_count=bullish_count + bearish_count,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        no_trade_count=no_trade_count,
        other_count=other_count,
        coverage_state=coverage_state,
        imbalance_flags=imbalance_flags,
        recommendations=recommendations,
        family_summaries=summaries,
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        metadata={
            "directional_balance": "directional_balance_v1",
            "scope": "read_only_no_execution_no_ranking",
            "source_scorer": getattr(scores, "metadata", {}).get("scorer") if isinstance(scores, OpportunityScoreReport) else None,
            "bullish_directions": sorted(BULLISH_DIRECTIONS),
            "bearish_directions": sorted(BEARISH_DIRECTIONS),
        },
    )


def direction_family(direction: str) -> DirectionFamily:
    normalized = str(direction or "").strip().upper()
    if normalized in BULLISH_DIRECTIONS:
        return "BULLISH"
    if normalized in BEARISH_DIRECTIONS:
        return "BEARISH"
    if normalized in NO_TRADE_DIRECTIONS:
        return "NO_TRADE"
    return "OTHER"


def _coerce_scores(scores: OpportunityScoreReport | Iterable[OpportunityScoreRecord]) -> tuple[OpportunityScoreRecord, ...]:
    if isinstance(scores, OpportunityScoreReport):
        return tuple(scores.scores)
    records = tuple(scores or ())
    for record in records:
        if not isinstance(record, OpportunityScoreRecord):
            raise TypeError("directional_balance_expected_opportunity_score_record")
    return records


def _summary_for_family(family: DirectionFamily, records: tuple[OpportunityScoreRecord, ...]) -> DirectionFamilySummary:
    scores = tuple(float(record.final_score) for record in records)
    total = round(sum(scores), 6)
    max_score = round(max(scores), 6) if scores else 0.0
    avg_score = round(total / len(scores), 6) if scores else 0.0
    top = max(records, key=lambda item: (float(item.final_score), item.strategy_id), default=None)
    return DirectionFamilySummary(
        family=family,
        directions=tuple(sorted(set(str(record.direction).upper() for record in records))),
        score_count=len(records),
        score_eligible_count=sum(1 for record in records if record.score_eligibility == SCORE_ELIGIBLE),
        needs_confirmation_count=sum(1 for record in records if record.score_eligibility == NEEDS_CONFIRMATION),
        advisory_count=sum(1 for record in records if record.score_eligibility == ADVISORY_ONLY),
        suppressed_count=sum(1 for record in records if record.score_eligibility == SUPPRESSED_BY_DOWNGRADE),
        no_trade_count=sum(1 for record in records if record.score_eligibility == NO_TRADE_ONLY),
        max_final_score=max_score,
        avg_final_score=avg_score,
        total_final_score=total,
        top_strategy_id=top.strategy_id if top is not None else None,
        blockers=tuple(sorted(set(blocker for record in records for blocker in record.blockers))),
        warnings=tuple(sorted(set(warning for record in records for warning in record.warnings))),
        safety_flags=tuple(sorted(set(flag for record in records for flag in record.safety_flags))),
    )


def _coverage_state(bullish_count: int, bearish_count: int, other_count: int) -> CoverageState:
    if bullish_count > 0 and bearish_count > 0:
        return "BALANCED_DIRECTIONAL_COVERAGE"
    if bullish_count > 0 and bearish_count == 0:
        return "BULLISH_ONLY_COVERAGE"
    if bearish_count > 0 and bullish_count == 0:
        return "BEARISH_ONLY_COVERAGE"
    if other_count > 0:
        return "MIXED_WITH_OTHER_COVERAGE"
    return "NO_DIRECTIONAL_COVERAGE"


def _imbalance_flags(groups: dict[DirectionFamily, list[OpportunityScoreRecord]]) -> tuple[str, ...]:
    flags: set[str] = set()
    bullish = groups["BULLISH"]
    bearish = groups["BEARISH"]
    if bullish and not bearish:
        flags.add("missing_bearish_candidate_coverage")
    if bearish and not bullish:
        flags.add("missing_bullish_candidate_coverage")
    if not bullish and not bearish:
        flags.add("missing_directional_candidate_coverage")
    if _eligible_count(bullish) > 0 and _eligible_count(bearish) == 0:
        flags.add("no_score_eligible_bearish_candidates")
    if _eligible_count(bearish) > 0 and _eligible_count(bullish) == 0:
        flags.add("no_score_eligible_bullish_candidates")
    if _side_is_fully_suppressed(bullish) and bearish:
        flags.add("bullish_side_fully_suppressed")
    if _side_is_fully_suppressed(bearish) and bullish:
        flags.add("bearish_side_fully_suppressed")
    if _score_skew_ratio(bullish, bearish) >= 3.0:
        flags.add("bullish_score_concentration")
    if _score_skew_ratio(bearish, bullish) >= 3.0:
        flags.add("bearish_score_concentration")
    return tuple(sorted(flags))


def _recommendations(coverage_state: CoverageState, imbalance_flags: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    if coverage_state == "BULLISH_ONLY_COVERAGE":
        out.append("review_put_strategy_generation_and_option_confirmation_paths")
    if coverage_state == "BEARISH_ONLY_COVERAGE":
        out.append("review_call_strategy_generation_and_option_confirmation_paths")
    if coverage_state == "NO_DIRECTIONAL_COVERAGE":
        out.append("inspect_candidate_generation_before_scoring_or_ranking")
    if "bearish_side_fully_suppressed" in imbalance_flags:
        out.append("inspect_put_side_blockers_before_ranking")
    if "bullish_side_fully_suppressed" in imbalance_flags:
        out.append("inspect_call_side_blockers_before_ranking")
    if "bullish_score_concentration" in imbalance_flags or "bearish_score_concentration" in imbalance_flags:
        out.append("review_directional_score_concentration_before_final_ranking")
    if not out:
        out.append("directional_coverage_ok_for_next_read_only_ranking_step")
    return tuple(out)


def _eligible_count(records: list[OpportunityScoreRecord]) -> int:
    return sum(1 for record in records if record.score_eligibility == SCORE_ELIGIBLE)


def _side_is_fully_suppressed(records: list[OpportunityScoreRecord]) -> bool:
    return bool(records) and all(record.score_eligibility in {SUPPRESSED_BY_DOWNGRADE, NO_TRADE_ONLY} for record in records)


def _score_skew_ratio(primary: list[OpportunityScoreRecord], secondary: list[OpportunityScoreRecord]) -> float:
    primary_total = sum(float(record.final_score) for record in primary)
    secondary_total = sum(float(record.final_score) for record in secondary)
    if primary_total <= 0.0:
        return 0.0
    if secondary_total <= 0.0:
        return float("inf")
    return primary_total / secondary_total


__all__ = [
    "BEARISH_DIRECTIONS",
    "BULLISH_DIRECTIONS",
    "DIRECTIONAL_BALANCE_SCHEMA_VERSION",
    "NO_TRADE_DIRECTIONS",
    "DirectionFamilySummary",
    "DirectionalBalanceReport",
    "analyze_directional_balance",
    "direction_family",
]
