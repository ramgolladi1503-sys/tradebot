"""Read-only candidate classification layer.

This module turns normalized movement candidates into operational buckets before
future scoring/ranking work. It does not rank, score, execute, call brokers,
touch depth subscriptions, mutate candidates, or change dashboard behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from core.movement_contract import HARD_EXECUTION_BLOCKERS, StrategyCandidate, has_hard_blocker
from core.no_trade_engine import NoTradeAssessment

CLASSIFICATION_SCHEMA_VERSION = 1

CandidateBucket = Literal[
    "EXECUTABLE_CANDIDATE",
    "NEAR_EXECUTABLE_CANDIDATE",
    "ADVISORY_CANDIDATE",
    "SUPPRESSED_CANDIDATE",
    "NO_TRADE_CANDIDATE",
]

SUPPRESSION_BLOCKERS: frozenset[str] = frozenset(HARD_EXECUTION_BLOCKERS).union(
    {
        "NO_TRADE_STALE_FEED",
        "NO_TRADE_FALLBACK_DATA",
        "NO_TRADE_LIQUIDITY",
        "NO_TRADE_WEAK_OPTION_CONFIRMATION",
        "NO_TRADE_CONFLICTING_SIGNALS",
        "NO_TRADE_INCONCLUSIVE_REGIME",
    }
)

STALE_WARNING_TOKENS: tuple[str, ...] = ("stale", "age_missing")
FALLBACK_WARNING_TOKENS: tuple[str, ...] = ("fallback",)
LIQUIDITY_WARNING_TOKENS: tuple[str, ...] = ("spread", "depth", "liquidity")


@dataclass(frozen=True)
class CandidateClassification:
    """Classification audit record for a single candidate."""

    strategy_id: str
    symbol: str
    direction: str
    movement_type: str
    candidate_status: str
    bucket: CandidateBucket
    executable_candidate: bool
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    hard_blockers: tuple[str, ...]
    evidence_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "movement_type": self.movement_type,
            "candidate_status": self.candidate_status,
            "bucket": self.bucket,
            "executable_candidate": self.executable_candidate,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "hard_blockers": list(self.hard_blockers),
            "evidence_flags": list(self.evidence_flags),
        }


@dataclass(frozen=True)
class CandidateClassificationReport:
    """Read-only classification report for normalized candidate pools."""

    schema_version: int
    read_only: bool
    is_order_action: bool
    append: bool
    candidate_count: int
    executable_count: int
    near_executable_count: int
    advisory_count: int
    suppressed_count: int
    no_trade_count: int
    classifications: tuple[CandidateClassification, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": self.is_order_action,
            "append": self.append,
            "candidate_count": self.candidate_count,
            "executable_count": self.executable_count,
            "near_executable_count": self.near_executable_count,
            "advisory_count": self.advisory_count,
            "suppressed_count": self.suppressed_count,
            "no_trade_count": self.no_trade_count,
            "classifications": [item.to_dict() for item in self.classifications],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def classify_candidates(
    candidates: Iterable[StrategyCandidate],
    *,
    no_trade_assessment: NoTradeAssessment | None = None,
    no_trade_active: bool | None = None,
    no_trade_reason: str | None = None,
) -> CandidateClassificationReport:
    """Classify candidates into pre-ranking operational buckets.

    ``no_trade_assessment`` is preferred when available. The explicit
    ``no_trade_active`` and ``no_trade_reason`` parameters exist for isolated
    tests and future callers that only have a summarized no-trade state.
    """

    candidate_tuple = tuple(candidates or ())
    for candidate in candidate_tuple:
        if not isinstance(candidate, StrategyCandidate):
            raise TypeError("candidate_classifier_expected_strategy_candidate")

    active_no_trade, active_no_trade_reason = _resolve_no_trade_state(
        no_trade_assessment=no_trade_assessment,
        no_trade_active=no_trade_active,
        no_trade_reason=no_trade_reason,
    )

    classifications = tuple(
        classify_candidate(
            candidate,
            no_trade_active=active_no_trade,
            no_trade_reason=active_no_trade_reason,
        )
        for candidate in candidate_tuple
    )

    blockers = tuple(sorted(set(blocker for item in classifications for blocker in item.blockers)))
    warnings = tuple(sorted(set(warning for item in classifications for warning in item.warnings)))

    return CandidateClassificationReport(
        schema_version=CLASSIFICATION_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        candidate_count=len(classifications),
        executable_count=sum(1 for item in classifications if item.bucket == "EXECUTABLE_CANDIDATE"),
        near_executable_count=sum(1 for item in classifications if item.bucket == "NEAR_EXECUTABLE_CANDIDATE"),
        advisory_count=sum(1 for item in classifications if item.bucket == "ADVISORY_CANDIDATE"),
        suppressed_count=sum(1 for item in classifications if item.bucket == "SUPPRESSED_CANDIDATE"),
        no_trade_count=sum(1 for item in classifications if item.bucket == "NO_TRADE_CANDIDATE"),
        classifications=classifications,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "classifier": "candidate_classifier_v1",
            "scope": "read_only_no_execution_no_ranking",
            "no_trade_active": active_no_trade,
            "no_trade_reason": active_no_trade_reason,
            "bucket_order": [
                "EXECUTABLE_CANDIDATE",
                "NEAR_EXECUTABLE_CANDIDATE",
                "ADVISORY_CANDIDATE",
                "SUPPRESSED_CANDIDATE",
                "NO_TRADE_CANDIDATE",
            ],
        },
    )


def classify_candidate(
    candidate: StrategyCandidate,
    *,
    no_trade_active: bool = False,
    no_trade_reason: str | None = None,
) -> CandidateClassification:
    if not isinstance(candidate, StrategyCandidate):
        raise TypeError("candidate_classifier_expected_strategy_candidate")

    blockers = tuple(sorted(set(str(item).strip().upper() for item in candidate.blockers if str(item).strip())))
    warnings = tuple(sorted(set(str(item).strip() for item in candidate.warnings if str(item).strip())))
    hard_blockers = tuple(sorted(set(blocker for blocker in blockers if blocker in SUPPRESSION_BLOCKERS)))
    evidence_flags = _evidence_flags(blockers, warnings)
    reasons: list[str] = []

    if _is_no_trade_candidate(candidate):
        reasons.append("candidate_is_no_trade_signal")
        return _classification(
            candidate,
            bucket="NO_TRADE_CANDIDATE",
            executable_candidate=False,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            hard_blockers=hard_blockers,
            evidence_flags=evidence_flags,
        )

    if no_trade_active:
        reasons.append("suppressed_by_no_trade_assessment")
        if no_trade_reason:
            reasons.append(str(no_trade_reason).strip().upper())
        return _classification(
            candidate,
            bucket="SUPPRESSED_CANDIDATE",
            executable_candidate=False,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            hard_blockers=hard_blockers,
            evidence_flags=evidence_flags,
        )

    if hard_blockers or has_hard_blocker(blockers) or candidate.status == "BLOCKED_CANDIDATE":
        reasons.append("hard_blocked_or_blocked_status")
        reasons.extend(hard_blockers)
        return _classification(
            candidate,
            bucket="SUPPRESSED_CANDIDATE",
            executable_candidate=False,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            hard_blockers=hard_blockers,
            evidence_flags=evidence_flags,
        )

    if candidate.executable_eligible:
        reasons.append("validated_without_hard_blockers")
        return _classification(
            candidate,
            bucket="EXECUTABLE_CANDIDATE",
            executable_candidate=True,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            hard_blockers=hard_blockers,
            evidence_flags=evidence_flags,
        )

    if candidate.status == "RAW_CANDIDATE" and not blockers:
        reasons.append("raw_candidate_needs_confirmation")
        return _classification(
            candidate,
            bucket="NEAR_EXECUTABLE_CANDIDATE",
            executable_candidate=False,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            hard_blockers=hard_blockers,
            evidence_flags=evidence_flags,
        )

    reasons.append("informational_or_soft_blocked_candidate")
    return _classification(
        candidate,
        bucket="ADVISORY_CANDIDATE",
        executable_candidate=False,
        reasons=reasons,
        blockers=blockers,
        warnings=warnings,
        hard_blockers=hard_blockers,
        evidence_flags=evidence_flags,
    )


def _classification(
    candidate: StrategyCandidate,
    *,
    bucket: CandidateBucket,
    executable_candidate: bool,
    reasons: Iterable[str],
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    hard_blockers: tuple[str, ...],
    evidence_flags: tuple[str, ...],
) -> CandidateClassification:
    return CandidateClassification(
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        movement_type=candidate.movement_type,
        candidate_status=candidate.status,
        bucket=bucket,
        executable_candidate=bool(executable_candidate),
        reasons=tuple(sorted(set(str(reason).strip() for reason in reasons if str(reason).strip()))),
        blockers=blockers,
        warnings=warnings,
        hard_blockers=hard_blockers,
        evidence_flags=evidence_flags,
    )


def _resolve_no_trade_state(
    *,
    no_trade_assessment: NoTradeAssessment | None,
    no_trade_active: bool | None,
    no_trade_reason: str | None,
) -> tuple[bool, str | None]:
    if no_trade_assessment is not None:
        return bool(no_trade_assessment.no_trade), str(no_trade_assessment.primary_reason or "") or None
    return bool(no_trade_active), (str(no_trade_reason).strip().upper() if no_trade_reason else None)


def _is_no_trade_candidate(candidate: StrategyCandidate) -> bool:
    return candidate.direction == "NO_TRADE" or candidate.status == "NO_TRADE" or str(candidate.movement_type).startswith("NO_TRADE")


def _evidence_flags(blockers: tuple[str, ...], warnings: tuple[str, ...]) -> tuple[str, ...]:
    texts = tuple(item.lower() for item in blockers + warnings)
    flags: set[str] = set()
    if "FALLBACK_QUOTE_ONLY" in blockers or any(token in text for text in texts for token in FALLBACK_WARNING_TOKENS):
        flags.add("fallback_data")
    if "STALE_OPTION_LTP" in blockers or any(token in text for text in texts for token in STALE_WARNING_TOKENS):
        flags.add("stale_feed")
    if {"WIDE_SPREAD", "MISSING_DEPTH"}.intersection(blockers) or any(
        token in text for text in texts for token in LIQUIDITY_WARNING_TOKENS
    ):
        flags.add("liquidity_risk")
    if "OPTION_CONFIRMATION_MISSING" in blockers:
        flags.add("weak_option_confirmation")
    if any(str(blocker).startswith("NO_TRADE") for blocker in blockers):
        flags.add("no_trade_suppression")
    return tuple(sorted(flags))


__all__ = [
    "CLASSIFICATION_SCHEMA_VERSION",
    "SUPPRESSION_BLOCKERS",
    "CandidateBucket",
    "CandidateClassification",
    "CandidateClassificationReport",
    "classify_candidate",
    "classify_candidates",
]
