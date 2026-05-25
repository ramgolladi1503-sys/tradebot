"""Read-only candidate readiness summary contract for EDGE-73.

This module consumes EDGE-72 hard downgrade decisions and produces aggregate
readiness evidence. It does not rank candidates, score edge, select strategies,
wire runtime behavior, call brokers, or create order intent.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_hard_downgrade import (
    DOWNGRADE_DECISION_ADVISORY_ONLY,
    DOWNGRADE_DECISION_BLOCKED,
    DOWNGRADE_DECISION_CANDIDATE_READY,
    CandidateHardDowngradeDecision,
    CandidateHardDowngradeReport,
)

CANDIDATE_READINESS_SUMMARY_SCHEMA_VERSION = 1
CANDIDATE_READINESS_SUMMARY_SOURCE = "candidate_readiness_summary_v1"

READINESS_SUMMARY_EMPTY_INPUT = "candidate_readiness_summary_empty_input"
READINESS_SUMMARY_DOWNGRADE_INVALID = "candidate_readiness_summary_downgrade_invalid"
READINESS_SUMMARY_MALFORMED_DECISION = "candidate_readiness_summary_malformed_decision"
READINESS_SUMMARY_UNKNOWN_DECISION = "candidate_readiness_summary_unknown_decision"

READINESS_STATE_READY = "READY"
READINESS_STATE_ADVISORY_ONLY = "ADVISORY_ONLY"
READINESS_STATE_BLOCKED = "BLOCKED"
READINESS_STATE_INVALID = "INVALID"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class CandidateReadinessSummary:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    readiness_state: str
    total_count: int
    ready_count: int
    advisory_only_count: int
    blocked_count: int
    invalid_count: int
    candidate_ready_ids: tuple[str, ...]
    advisory_only_ids: tuple[str, ...]
    blocked_ids: tuple[str, ...]
    reason_counts: dict[str, int]
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
    def has_ready_candidates(self) -> bool:
        return self.ready_count > 0

    @property
    def has_only_advisory_candidates(self) -> bool:
        return self.ready_count == 0 and self.advisory_only_count > 0 and self.blocked_count == 0

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "readiness_state": self.readiness_state,
            "total_count": self.total_count,
            "ready_count": self.ready_count,
            "advisory_only_count": self.advisory_only_count,
            "blocked_count": self.blocked_count,
            "invalid_count": self.invalid_count,
            "has_ready_candidates": self.has_ready_candidates,
            "has_only_advisory_candidates": self.has_only_advisory_candidates,
            "candidate_ready_ids": list(self.candidate_ready_ids),
            "advisory_only_ids": list(self.advisory_only_ids),
            "blocked_ids": list(self.blocked_ids),
            "reason_counts": dict(sorted(self.reason_counts.items())),
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


def summarize_candidate_readiness(
    decisions: CandidateHardDowngradeReport | Iterable[CandidateHardDowngradeDecision | Mapping[str, Any]],
    *,
    source: str = CANDIDATE_READINESS_SUMMARY_SOURCE,
) -> CandidateReadinessSummary:
    """Summarize EDGE-72 readiness decisions without ranking or selection."""

    downgrade_invalid = isinstance(decisions, CandidateHardDowngradeReport) and not decisions.valid
    active_decisions, blocked_decisions, downgrade_blockers = _resolve_decisions(decisions)
    report_blockers = _dedupe_sorted(
        (
            *((READINESS_SUMMARY_EMPTY_INPUT,) if not active_decisions and not blocked_decisions else ()),
            *((READINESS_SUMMARY_DOWNGRADE_INVALID,) if downgrade_invalid else ()),
            *(_prefixed_downgrade_blockers(downgrade_blockers) if downgrade_invalid else ()),
        )
    )

    coerced_active = tuple(_coerce_decision(decision) for decision in active_decisions)
    coerced_blocked = tuple(_coerce_decision(decision) for decision in blocked_decisions)
    malformed_blockers = _dedupe_sorted(
        READINESS_SUMMARY_MALFORMED_DECISION
        for decision in (*coerced_active, *coerced_blocked)
        if not decision.canonical_candidate_id or not decision.strategy_id
    )
    unknown_decision_warnings = _dedupe_sorted(
        READINESS_SUMMARY_UNKNOWN_DECISION
        for decision in (*coerced_active, *coerced_blocked)
        if decision.decision not in {
            DOWNGRADE_DECISION_CANDIDATE_READY,
            DOWNGRADE_DECISION_ADVISORY_ONLY,
            DOWNGRADE_DECISION_BLOCKED,
        }
    )
    blockers = _dedupe_sorted((*report_blockers, *malformed_blockers))

    ready = tuple(
        decision for decision in coerced_active
        if decision.decision == DOWNGRADE_DECISION_CANDIDATE_READY and not blockers
    )
    advisory = tuple(
        decision for decision in coerced_active
        if decision.decision == DOWNGRADE_DECISION_ADVISORY_ONLY and not blockers
    )
    blocked = tuple(
        decision for decision in (*coerced_blocked, *coerced_active)
        if decision.decision == DOWNGRADE_DECISION_BLOCKED or blockers
    )
    invalid_count = len([decision for decision in (*coerced_active, *coerced_blocked) if decision.decision not in {
        DOWNGRADE_DECISION_CANDIDATE_READY,
        DOWNGRADE_DECISION_ADVISORY_ONLY,
        DOWNGRADE_DECISION_BLOCKED,
    }])

    reason_counts = _reason_counts((*advisory, *blocked))
    readiness_state = _readiness_state(
        blockers=blockers,
        ready_count=len(ready),
        advisory_only_count=len(advisory),
        blocked_count=len(blocked),
    )
    warnings = _dedupe_sorted(
        (
            *unknown_decision_warnings,
            *(warning for decision in (*coerced_active, *coerced_blocked) for warning in decision.warnings),
        )
    )
    return CandidateReadinessSummary(
        schema_version=CANDIDATE_READINESS_SUMMARY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        readiness_state=readiness_state,
        total_count=len(coerced_active) + len(coerced_blocked),
        ready_count=len(ready),
        advisory_only_count=len(advisory),
        blocked_count=len(blocked),
        invalid_count=invalid_count,
        candidate_ready_ids=tuple(sorted(decision.canonical_candidate_id for decision in ready)),
        advisory_only_ids=tuple(sorted(decision.canonical_candidate_id for decision in advisory)),
        blocked_ids=tuple(sorted(decision.canonical_candidate_id for decision in blocked)),
        reason_counts=reason_counts,
        blockers=blockers,
        warnings=warnings,
        metadata=_metadata(),
    )


def _resolve_decisions(
    decisions: CandidateHardDowngradeReport | Iterable[CandidateHardDowngradeDecision | Mapping[str, Any]],
) -> tuple[
    tuple[CandidateHardDowngradeDecision | Mapping[str, Any], ...],
    tuple[CandidateHardDowngradeDecision | Mapping[str, Any], ...],
    tuple[str, ...],
]:
    if isinstance(decisions, CandidateHardDowngradeReport):
        return tuple(decisions.decisions), tuple(decisions.blocked_decisions), tuple(decisions.blockers)
    if decisions is None:
        return (), (), ()
    return tuple(decisions), (), ()


def _coerce_decision(decision: CandidateHardDowngradeDecision | Mapping[str, Any]) -> CandidateHardDowngradeDecision:
    if isinstance(decision, CandidateHardDowngradeDecision):
        return decision
    if not isinstance(decision, Mapping):
        return CandidateHardDowngradeDecision(
            canonical_candidate_id="",
            strategy_id="",
            decision=DOWNGRADE_DECISION_BLOCKED,
            hard_downgraded=True,
            candidate_ready=False,
            advisory_only=False,
            blocked=True,
            reasons=(READINESS_SUMMARY_MALFORMED_DECISION,),
            blockers=(READINESS_SUMMARY_MALFORMED_DECISION,),
            metadata={"coercion_error": type(decision).__name__},
        )
    decision_value = str(decision.get("decision") or "").strip().upper()
    return CandidateHardDowngradeDecision(
        canonical_candidate_id=_candidate_key(decision.get("canonical_candidate_id")),
        strategy_id=_candidate_key(decision.get("strategy_id")),
        decision=decision_value,
        hard_downgraded=_truthy(decision.get("hard_downgraded")),
        candidate_ready=_truthy(decision.get("candidate_ready")),
        advisory_only=_truthy(decision.get("advisory_only")),
        blocked=_truthy(decision.get("blocked")),
        reasons=_tuple(decision.get("reasons") or ()),
        blockers=_tuple(decision.get("blockers") or ()),
        warnings=_tuple(decision.get("warnings") or ()),
        labels=_tuple(decision.get("labels") or ()),
        metadata=_safe_dict(decision.get("metadata")),
    )


def _readiness_state(
    *,
    blockers: tuple[str, ...],
    ready_count: int,
    advisory_only_count: int,
    blocked_count: int,
) -> str:
    if blockers:
        return READINESS_STATE_INVALID
    if ready_count > 0:
        return READINESS_STATE_READY
    if advisory_only_count > 0 and blocked_count == 0:
        return READINESS_STATE_ADVISORY_ONLY
    return READINESS_STATE_BLOCKED


def _reason_counts(decisions: Iterable[CandidateHardDowngradeDecision]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for decision in decisions:
        for reason in (*decision.reasons, *decision.blockers):
            text = str(reason or "").strip()
            if text:
                counter[text] += 1
    return dict(counter)


def _prefixed_downgrade_blockers(blockers: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"downgrade:{blocker}" for blocker in blockers if str(blocker or "").strip())


def _metadata() -> dict[str, Any]:
    return {
        "model": CANDIDATE_READINESS_SUMMARY_SOURCE,
        "scope": "candidate_readiness_summary_no_runtime_wiring_no_ranking_no_scoring",
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


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
    "CANDIDATE_READINESS_SUMMARY_SCHEMA_VERSION",
    "CANDIDATE_READINESS_SUMMARY_SOURCE",
    "CandidateReadinessSummary",
    "READINESS_STATE_ADVISORY_ONLY",
    "READINESS_STATE_BLOCKED",
    "READINESS_STATE_INVALID",
    "READINESS_STATE_READY",
    "READINESS_SUMMARY_DOWNGRADE_INVALID",
    "READINESS_SUMMARY_EMPTY_INPUT",
    "READINESS_SUMMARY_MALFORMED_DECISION",
    "READINESS_SUMMARY_UNKNOWN_DECISION",
    "summarize_candidate_readiness",
]
