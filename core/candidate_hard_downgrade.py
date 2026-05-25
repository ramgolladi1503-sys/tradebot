"""Read-only hard downgrade contract for EDGE-72.

This module consumes EDGE-71 classified candidate metadata and converts unsafe
metadata states into explicit candidate decisions. It does not rank candidates,
score edge, select strategies, wire runtime behavior, call brokers, or create
order intent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.strategy_candidate_classification import (
    CLASSIFICATION_EVIDENCE_INCOMPLETE,
    CLASSIFICATION_UNKNOWN_DIRECTION,
    CLASSIFICATION_UNKNOWN_FAMILY,
    CLASSIFICATION_UNKNOWN_REGIME,
    CandidateClassificationReport,
    ClassifiedStrategyCandidate,
)

CANDIDATE_HARD_DOWNGRADE_SCHEMA_VERSION = 1
CANDIDATE_HARD_DOWNGRADE_SOURCE = "candidate_hard_downgrade_v1"

HARD_DOWNGRADE_EMPTY_INPUT = "candidate_hard_downgrade_empty_input"
HARD_DOWNGRADE_CLASSIFICATION_INVALID = "candidate_hard_downgrade_classification_invalid"
HARD_DOWNGRADE_MALFORMED_CANDIDATE = "candidate_hard_downgrade_malformed_candidate"
HARD_DOWNGRADE_CLASSIFICATION_BLOCKED = "candidate_hard_downgrade_classification_blocked"
HARD_DOWNGRADE_UNKNOWN_DIRECTION = "candidate_hard_downgrade_unknown_direction"
HARD_DOWNGRADE_UNKNOWN_REGIME = "candidate_hard_downgrade_unknown_regime"
HARD_DOWNGRADE_UNKNOWN_FAMILY = "candidate_hard_downgrade_unknown_family"
HARD_DOWNGRADE_EVIDENCE_INCOMPLETE = "candidate_hard_downgrade_evidence_incomplete"

DOWNGRADE_DECISION_CANDIDATE_READY = "CANDIDATE_READY"
DOWNGRADE_DECISION_ADVISORY_ONLY = "ADVISORY_ONLY"
DOWNGRADE_DECISION_BLOCKED = "BLOCKED"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_WARNING_TO_DOWNGRADE_REASON = {
    CLASSIFICATION_UNKNOWN_DIRECTION: HARD_DOWNGRADE_UNKNOWN_DIRECTION,
    CLASSIFICATION_UNKNOWN_REGIME: HARD_DOWNGRADE_UNKNOWN_REGIME,
    CLASSIFICATION_UNKNOWN_FAMILY: HARD_DOWNGRADE_UNKNOWN_FAMILY,
    CLASSIFICATION_EVIDENCE_INCOMPLETE: HARD_DOWNGRADE_EVIDENCE_INCOMPLETE,
}


@dataclass(frozen=True)
class CandidateHardDowngradeDecision:
    canonical_candidate_id: str
    strategy_id: str
    decision: str
    hard_downgraded: bool
    candidate_ready: bool
    advisory_only: bool
    blocked: bool
    reasons: tuple[str, ...]
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    labels: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = CANDIDATE_HARD_DOWNGRADE_SOURCE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blocked

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "canonical_candidate_id": self.canonical_candidate_id,
            "strategy_id": self.strategy_id,
            "decision": self.decision,
            "hard_downgraded": self.hard_downgraded,
            "candidate_ready": self.candidate_ready,
            "advisory_only": self.advisory_only,
            "blocked": self.blocked,
            "valid": self.valid,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "labels": list(self.labels),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class CandidateHardDowngradeReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    decisions: tuple[CandidateHardDowngradeDecision, ...]
    blocked_decisions: tuple[CandidateHardDowngradeDecision, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers

    @property
    def candidate_ready_ids(self) -> tuple[str, ...]:
        return tuple(
            decision.canonical_candidate_id
            for decision in self.decisions
            if decision.candidate_ready
        )

    @property
    def advisory_only_ids(self) -> tuple[str, ...]:
        return tuple(
            decision.canonical_candidate_id
            for decision in self.decisions
            if decision.advisory_only
        )

    @property
    def blocked_ids(self) -> tuple[str, ...]:
        return tuple(decision.canonical_candidate_id for decision in self.blocked_decisions)

    def get(self, canonical_candidate_id: str) -> CandidateHardDowngradeDecision | None:
        wanted = _candidate_key(canonical_candidate_id)
        for decision in (*self.decisions, *self.blocked_decisions):
            if decision.canonical_candidate_id == wanted:
                return decision
        return None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "decision_count": len(self.decisions),
            "blocked_count": len(self.blocked_decisions),
            "candidate_ready_ids": list(self.candidate_ready_ids),
            "advisory_only_ids": list(self.advisory_only_ids),
            "blocked_ids": list(self.blocked_ids),
            "decisions": [decision.to_payload() for decision in self.decisions],
            "blocked_decisions": [decision.to_payload() for decision in self.blocked_decisions],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def apply_candidate_hard_downgrades(
    candidates: CandidateClassificationReport | Iterable[ClassifiedStrategyCandidate | Mapping[str, Any]],
    *,
    source: str = CANDIDATE_HARD_DOWNGRADE_SOURCE,
) -> CandidateHardDowngradeReport:
    """Apply hard downgrade decisions to classified candidates without scoring."""

    classification_invalid = isinstance(candidates, CandidateClassificationReport) and not candidates.valid
    classified, classification_blocked, classification_blockers = _resolve_candidates(candidates)
    report_blockers = _dedupe_sorted(
        (
            *((HARD_DOWNGRADE_EMPTY_INPUT,) if not classified and not classification_blocked else ()),
            *((HARD_DOWNGRADE_CLASSIFICATION_INVALID,) if classification_invalid else ()),
            *(_prefixed_classification_blockers(classification_blockers) if classification_invalid else ()),
        )
    )

    blocked_decisions = tuple(
        sorted(
            (
                *(
                    _blocked_from_candidate(
                        _coerce_candidate(candidate),
                        forced_blockers=report_blockers,
                    )
                    for candidate in classified
                    if report_blockers
                ),
                *(
                    _blocked_from_candidate(
                        _coerce_candidate(candidate),
                        forced_blockers=(HARD_DOWNGRADE_CLASSIFICATION_BLOCKED, *report_blockers),
                    )
                    for candidate in classification_blocked
                ),
            ),
            key=lambda item: item.canonical_candidate_id,
        )
    )
    if report_blockers:
        return CandidateHardDowngradeReport(
            schema_version=CANDIDATE_HARD_DOWNGRADE_SCHEMA_VERSION,
            read_only=True,
            append=False,
            source=source,
            decisions=(),
            blocked_decisions=blocked_decisions,
            blockers=report_blockers,
            warnings=(),
            metadata=_metadata(),
        )

    decisions: list[CandidateHardDowngradeDecision] = []
    blocked: list[CandidateHardDowngradeDecision] = list(blocked_decisions)
    for raw in classified:
        candidate = _coerce_candidate(raw)
        decision = _decision_from_candidate(candidate)
        if decision.blocked:
            blocked.append(decision)
        else:
            decisions.append(decision)

    warnings = _dedupe_sorted(
        warning for decision in (*decisions, *blocked) for warning in decision.warnings
    )
    return CandidateHardDowngradeReport(
        schema_version=CANDIDATE_HARD_DOWNGRADE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        decisions=tuple(sorted(decisions, key=lambda item: item.canonical_candidate_id)),
        blocked_decisions=tuple(sorted(blocked, key=lambda item: item.canonical_candidate_id)),
        blockers=(),
        warnings=warnings,
        metadata=_metadata(),
    )


def _resolve_candidates(
    candidates: CandidateClassificationReport | Iterable[ClassifiedStrategyCandidate | Mapping[str, Any]],
) -> tuple[
    tuple[ClassifiedStrategyCandidate | Mapping[str, Any], ...],
    tuple[ClassifiedStrategyCandidate | Mapping[str, Any], ...],
    tuple[str, ...],
]:
    if isinstance(candidates, CandidateClassificationReport):
        return tuple(candidates.classified_candidates), tuple(candidates.blocked_candidates), tuple(candidates.blockers)
    if candidates is None:
        return (), (), ()
    return tuple(candidates), (), ()


def _decision_from_candidate(candidate: ClassifiedStrategyCandidate) -> CandidateHardDowngradeDecision:
    blockers = _candidate_blockers(candidate)
    if blockers:
        return _blocked_from_candidate(candidate, forced_blockers=blockers)

    downgrade_reasons = _downgrade_reasons(candidate)
    advisory_only = bool(downgrade_reasons)
    decision = DOWNGRADE_DECISION_ADVISORY_ONLY if advisory_only else DOWNGRADE_DECISION_CANDIDATE_READY
    return CandidateHardDowngradeDecision(
        canonical_candidate_id=_candidate_key(candidate.canonical_candidate_id),
        strategy_id=_candidate_key(candidate.strategy_id),
        decision=decision,
        hard_downgraded=advisory_only,
        candidate_ready=not advisory_only,
        advisory_only=advisory_only,
        blocked=False,
        reasons=downgrade_reasons,
        blockers=(),
        warnings=tuple(candidate.warnings),
        labels=tuple(candidate.labels),
        metadata={
            "source_candidate_source": candidate.source,
            "source_candidate_valid": candidate.valid,
            "source_candidate_read_only": candidate.read_only,
            "source_candidate_append": candidate.append,
        },
    )


def _blocked_from_candidate(
    candidate: ClassifiedStrategyCandidate,
    *,
    forced_blockers: Iterable[str],
) -> CandidateHardDowngradeDecision:
    blockers = _dedupe_sorted((*forced_blockers, *_candidate_blockers(candidate)))
    return CandidateHardDowngradeDecision(
        canonical_candidate_id=_candidate_key(candidate.canonical_candidate_id),
        strategy_id=_candidate_key(candidate.strategy_id),
        decision=DOWNGRADE_DECISION_BLOCKED,
        hard_downgraded=True,
        candidate_ready=False,
        advisory_only=False,
        blocked=True,
        reasons=blockers,
        blockers=blockers,
        warnings=tuple(candidate.warnings),
        labels=tuple(candidate.labels),
        metadata={
            "source_candidate_source": candidate.source,
            "source_candidate_valid": candidate.valid,
            "source_candidate_blockers": list(candidate.blockers),
        },
    )


def _candidate_blockers(candidate: ClassifiedStrategyCandidate) -> tuple[str, ...]:
    required = (candidate.canonical_candidate_id, candidate.strategy_id, candidate.decision if hasattr(candidate, "decision") else "ok")
    if not all(str(value or "").strip() for value in required[:2]):
        return (HARD_DOWNGRADE_MALFORMED_CANDIDATE,)
    if candidate.blockers:
        return _dedupe_sorted((HARD_DOWNGRADE_CLASSIFICATION_BLOCKED, *candidate.blockers))
    return ()


def _downgrade_reasons(candidate: ClassifiedStrategyCandidate) -> tuple[str, ...]:
    return _dedupe_sorted(
        _WARNING_TO_DOWNGRADE_REASON[warning]
        for warning in candidate.warnings
        if warning in _WARNING_TO_DOWNGRADE_REASON
    )


def _coerce_candidate(candidate: ClassifiedStrategyCandidate | Mapping[str, Any]) -> ClassifiedStrategyCandidate:
    if isinstance(candidate, ClassifiedStrategyCandidate):
        return candidate
    if not isinstance(candidate, Mapping):
        return ClassifiedStrategyCandidate(
            canonical_candidate_id="",
            strategy_id="",
            instrument="",
            regime="",
            direction="",
            family="",
            direction_class="",
            regime_class="",
            family_class="",
            instrument_class="",
            evidence_class="",
            labels=(),
            blockers=(HARD_DOWNGRADE_MALFORMED_CANDIDATE,),
            metadata={"coercion_error": type(candidate).__name__},
        )
    return ClassifiedStrategyCandidate(
        canonical_candidate_id=str(candidate.get("canonical_candidate_id") or ""),
        strategy_id=str(candidate.get("strategy_id") or ""),
        instrument=str(candidate.get("instrument") or ""),
        regime=str(candidate.get("regime") or ""),
        direction=str(candidate.get("direction") or ""),
        family=str(candidate.get("family") or ""),
        direction_class=str(candidate.get("direction_class") or ""),
        regime_class=str(candidate.get("regime_class") or ""),
        family_class=str(candidate.get("family_class") or ""),
        instrument_class=str(candidate.get("instrument_class") or ""),
        evidence_class=str(candidate.get("evidence_class") or ""),
        labels=_tuple(candidate.get("labels") or ()),
        blockers=_tuple(candidate.get("blockers") or ()),
        warnings=_tuple(candidate.get("warnings") or ()),
        metadata=_safe_dict(candidate.get("metadata")),
    )


def _prefixed_classification_blockers(blockers: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"classification:{blocker}" for blocker in blockers if str(blocker or "").strip())


def _metadata() -> dict[str, Any]:
    return {
        "model": CANDIDATE_HARD_DOWNGRADE_SOURCE,
        "scope": "candidate_hard_downgrade_no_runtime_wiring_no_ranking_no_scoring",
        "does_not_import_strategy_modules": True,
        "does_not_execute_strategy_callables": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
        "does_not_select_candidates": True,
        "does_not_allocate_capital": True,
    }


def _candidate_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Iterable):
        values = tuple(value)
    else:
        values = (value,)
    return tuple(str(item).strip() for item in values if str(item).strip())


def _safe_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _safe_json_value(item) for key, item in value.items()}


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


__all__ = [
    "CANDIDATE_HARD_DOWNGRADE_SCHEMA_VERSION",
    "CANDIDATE_HARD_DOWNGRADE_SOURCE",
    "CandidateHardDowngradeDecision",
    "CandidateHardDowngradeReport",
    "DOWNGRADE_DECISION_ADVISORY_ONLY",
    "DOWNGRADE_DECISION_BLOCKED",
    "DOWNGRADE_DECISION_CANDIDATE_READY",
    "HARD_DOWNGRADE_CLASSIFICATION_BLOCKED",
    "HARD_DOWNGRADE_CLASSIFICATION_INVALID",
    "HARD_DOWNGRADE_EMPTY_INPUT",
    "HARD_DOWNGRADE_EVIDENCE_INCOMPLETE",
    "HARD_DOWNGRADE_MALFORMED_CANDIDATE",
    "HARD_DOWNGRADE_UNKNOWN_DIRECTION",
    "HARD_DOWNGRADE_UNKNOWN_FAMILY",
    "HARD_DOWNGRADE_UNKNOWN_REGIME",
    "apply_candidate_hard_downgrades",
]
