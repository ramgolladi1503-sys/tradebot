"""Read-only hard downgrade engine for classified candidates.

This module applies deterministic safety downgrades after candidate classification
and before future scoring/ranking work. It never mutates candidates, ranks rows,
submits orders, calls brokers, touches depth subscriptions, or changes dashboard
behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.candidate_classifier import (
    CandidateBucket,
    CandidateClassification,
    CandidateClassificationReport,
    SUPPRESSION_BLOCKERS,
)

DOWNGRADE_SCHEMA_VERSION = 1

BLOCKER_TO_REASON: dict[str, str] = {
    "FALLBACK_QUOTE_ONLY": "fallback_quote_data",
    "STALE_OPTION_LTP": "stale_option_ltp",
    "WIDE_SPREAD": "wide_spread",
    "MISSING_DEPTH": "missing_depth",
    "UNRESOLVED_CONTRACT": "unresolved_contract",
    "OPTION_CONFIRMATION_MISSING": "weak_option_confirmation",
    "NO_TRADE_CHOP": "no_trade_suppression",
    "QUOTE_SOURCE_UNTRUSTED": "untrusted_quote_source",
    "CONFLICTING_TRAP_SIGNAL": "conflicting_trap_signal",
    "BROKER_UNAVAILABLE": "broker_unavailable",
    "MARKET_CLOSED": "market_closed",
}

EVIDENCE_FLAG_TO_REASON: dict[str, str] = {
    "fallback_data": "fallback_quote_data",
    "stale_feed": "stale_option_ltp",
    "liquidity_risk": "liquidity_quality_failure",
    "weak_option_confirmation": "weak_option_confirmation",
    "no_trade_suppression": "no_trade_suppression",
}

BUCKET_ORDER: dict[str, int] = {
    "NO_TRADE_CANDIDATE": 0,
    "SUPPRESSED_CANDIDATE": 1,
    "ADVISORY_CANDIDATE": 2,
    "NEAR_EXECUTABLE_CANDIDATE": 3,
    "EXECUTABLE_CANDIDATE": 4,
}


@dataclass(frozen=True)
class HardDowngradeDecision:
    """Audit record for one hard downgrade decision."""

    strategy_id: str
    symbol: str
    direction: str
    movement_type: str
    original_bucket: str
    downgraded_bucket: str
    downgraded: bool
    executable_candidate: bool
    downgrade_reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    hard_blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    evidence_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "movement_type": self.movement_type,
            "original_bucket": self.original_bucket,
            "downgraded_bucket": self.downgraded_bucket,
            "downgraded": self.downgraded,
            "executable_candidate": self.executable_candidate,
            "downgrade_reasons": list(self.downgrade_reasons),
            "blockers": list(self.blockers),
            "hard_blockers": list(self.hard_blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "evidence_flags": list(self.evidence_flags),
        }


@dataclass(frozen=True)
class HardDowngradeReport:
    """Read-only report for deterministic safety downgrades."""

    schema_version: int
    read_only: bool
    is_order_action: bool
    append: bool
    candidate_count: int
    downgraded_count: int
    suppressed_count: int
    no_trade_count: int
    executable_after_downgrade_count: int
    decisions: tuple[HardDowngradeDecision, ...]
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
            "candidate_count": self.candidate_count,
            "downgraded_count": self.downgraded_count,
            "suppressed_count": self.suppressed_count,
            "no_trade_count": self.no_trade_count,
            "executable_after_downgrade_count": self.executable_after_downgrade_count,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def apply_hard_downgrades(
    classifications: CandidateClassificationReport | Iterable[CandidateClassification],
    *,
    no_trade_active: bool | None = None,
    no_trade_reason: str | None = None,
) -> HardDowngradeReport:
    """Apply deterministic hard downgrades to classified candidates."""

    items, source_metadata = _coerce_classifications(classifications)
    active_no_trade = bool(source_metadata.get("no_trade_active")) if no_trade_active is None else bool(no_trade_active)
    active_no_trade_reason = (
        str(source_metadata.get("no_trade_reason") or "").strip().upper() or None
        if no_trade_reason is None
        else str(no_trade_reason).strip().upper()
    )

    decisions = tuple(
        downgrade_classification(
            item,
            no_trade_active=active_no_trade,
            no_trade_reason=active_no_trade_reason,
        )
        for item in items
    )

    blockers = tuple(sorted(set(blocker for decision in decisions for blocker in decision.blockers)))
    warnings = tuple(sorted(set(warning for decision in decisions for warning in decision.warnings)))
    safety_flags = tuple(sorted(set(flag for decision in decisions for flag in decision.safety_flags)))

    return HardDowngradeReport(
        schema_version=DOWNGRADE_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        candidate_count=len(decisions),
        downgraded_count=sum(1 for decision in decisions if decision.downgraded),
        suppressed_count=sum(1 for decision in decisions if decision.downgraded_bucket == "SUPPRESSED_CANDIDATE"),
        no_trade_count=sum(1 for decision in decisions if decision.downgraded_bucket == "NO_TRADE_CANDIDATE"),
        executable_after_downgrade_count=sum(1 for decision in decisions if decision.executable_candidate),
        decisions=decisions,
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        metadata={
            "downgrade_engine": "hard_downgrade_engine_v1",
            "scope": "read_only_no_execution_no_ranking",
            "no_trade_active": active_no_trade,
            "no_trade_reason": active_no_trade_reason,
            "source_classifier": source_metadata.get("classifier"),
        },
    )


def downgrade_classification(
    classification: CandidateClassification,
    *,
    no_trade_active: bool = False,
    no_trade_reason: str | None = None,
) -> HardDowngradeDecision:
    if not isinstance(classification, CandidateClassification):
        raise TypeError("hard_downgrade_expected_candidate_classification")

    original_bucket = str(classification.bucket)
    blockers = _upper_tuple(classification.blockers)
    hard_blockers = tuple(sorted(set(_upper_tuple(classification.hard_blockers)).union(_hard_blockers_from_blockers(blockers))))
    warnings = tuple(sorted(set(str(item).strip() for item in classification.warnings if str(item).strip())))
    evidence_flags = tuple(sorted(set(str(item).strip() for item in classification.evidence_flags if str(item).strip())))
    reasons = set(str(item).strip() for item in classification.reasons if str(item).strip())
    downgrade_reasons: set[str] = set()
    safety_flags: set[str] = set(evidence_flags)

    for blocker in hard_blockers:
        downgrade_reasons.add(BLOCKER_TO_REASON.get(blocker, blocker.lower()))
    for flag in evidence_flags:
        downgrade_reasons.add(EVIDENCE_FLAG_TO_REASON.get(flag, flag))

    if no_trade_active and original_bucket != "NO_TRADE_CANDIDATE":
        downgrade_reasons.add("global_no_trade_active")
        safety_flags.add("no_trade_suppression")
        if no_trade_reason:
            downgrade_reasons.add(str(no_trade_reason).strip().lower())

    if original_bucket == "NO_TRADE_CANDIDATE":
        target_bucket = "NO_TRADE_CANDIDATE"
        executable = False
        downgrade_reasons.add("candidate_is_no_trade_signal")
        safety_flags.add("no_trade_suppression")
    elif no_trade_active or hard_blockers:
        target_bucket = "SUPPRESSED_CANDIDATE"
        executable = False
    elif original_bucket == "EXECUTABLE_CANDIDATE" and _has_soft_safety_risk(evidence_flags, warnings):
        target_bucket = "NEAR_EXECUTABLE_CANDIDATE"
        executable = False
        downgrade_reasons.add("soft_safety_evidence_requires_confirmation")
    else:
        target_bucket = original_bucket
        executable = bool(classification.executable_candidate and target_bucket == "EXECUTABLE_CANDIDATE")

    downgraded = _bucket_rank(target_bucket) < _bucket_rank(original_bucket)
    if not downgraded and target_bucket == original_bucket and downgrade_reasons:
        reasons.update(downgrade_reasons)

    return HardDowngradeDecision(
        strategy_id=classification.strategy_id,
        symbol=classification.symbol,
        direction=classification.direction,
        movement_type=classification.movement_type,
        original_bucket=original_bucket,
        downgraded_bucket=target_bucket,
        downgraded=downgraded,
        executable_candidate=bool(executable),
        downgrade_reasons=tuple(sorted(downgrade_reasons or reasons)),
        blockers=blockers,
        hard_blockers=hard_blockers,
        warnings=warnings,
        safety_flags=tuple(sorted(safety_flags)),
        evidence_flags=evidence_flags,
    )


def _coerce_classifications(
    classifications: CandidateClassificationReport | Iterable[CandidateClassification],
) -> tuple[tuple[CandidateClassification, ...], dict[str, Any]]:
    if isinstance(classifications, CandidateClassificationReport):
        return tuple(classifications.classifications), dict(classifications.metadata or {})
    items = tuple(classifications or ())
    for item in items:
        if not isinstance(item, CandidateClassification):
            raise TypeError("hard_downgrade_expected_candidate_classification")
    return items, {}


def _hard_blockers_from_blockers(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(blocker for blocker in blockers if blocker in SUPPRESSION_BLOCKERS)))


def _upper_tuple(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(str(item).strip().upper() for item in values if str(item).strip())))


def _has_soft_safety_risk(evidence_flags: tuple[str, ...], warnings: tuple[str, ...]) -> bool:
    texts = tuple(str(item).lower() for item in evidence_flags + warnings)
    soft_tokens = ("stale", "fallback", "spread", "depth", "liquidity", "untrusted")
    return any(token in text for text in texts for token in soft_tokens)


def _bucket_rank(bucket: str) -> int:
    return BUCKET_ORDER.get(str(bucket), -1)


__all__ = [
    "BLOCKER_TO_REASON",
    "DOWNGRADE_SCHEMA_VERSION",
    "EVIDENCE_FLAG_TO_REASON",
    "HardDowngradeDecision",
    "HardDowngradeReport",
    "apply_hard_downgrades",
    "downgrade_classification",
]
