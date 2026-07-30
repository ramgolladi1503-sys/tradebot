"""Canonical, immutable execution-decision contract.

This module is intentionally additive and feed-agnostic.  It wraps the existing
executable-truth classifier and converts fragmented legacy status fields into one
conservative decision.  It does not place orders or mutate candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from core.executable_truth import classify_executable_truth


class ExecutionState(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    BLOCKED = "BLOCKED"


_ADVISORY_REASONS = {
    "planning_only",
    "advisory_only",
    "data_not_live",
    "degraded_data",
    "debug_candidate",
}
_EXPLICIT_BLOCK_VALUES = {"BLOCK", "BLOCKED", "REJECT", "REJECTED"}
_NON_EXECUTABLE_VALUES = {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK", "BLOCKED"}
_MISSING = (None, "", "None")


@dataclass(frozen=True)
class CanonicalExecutionDecision:
    state: ExecutionState
    allowed: bool
    primary_reason: str
    blockers: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    legacy_signals: Mapping[str, Any] = field(default_factory=dict)
    truth_context: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    is_order_action: bool = False

    def __post_init__(self) -> None:
        if self.allowed != (self.state is ExecutionState.EXECUTABLE):
            raise ValueError("canonical_execution_decision_allowed_state_mismatch")
        if not self.primary_reason:
            raise ValueError("canonical_execution_decision_primary_reason_missing")
        if self.is_order_action:
            raise ValueError("canonical_execution_decision_cannot_be_order_action")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "allowed": self.allowed,
            "primary_reason": self.primary_reason,
            "blockers": list(self.blockers),
            "contradictions": list(self.contradictions),
            "legacy_signals": dict(self.legacy_signals),
            "truth_context": dict(self.truth_context),
            "is_order_action": False,
        }


def _get(candidate: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(field_name, default)
    return getattr(candidate, field_name, default)


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in _MISSING:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0.0
    except (TypeError, ValueError):
        return False


def _legacy_signals(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_status": _get(candidate, "candidate_status"),
        "execution_status": _get(candidate, "execution_status"),
        "execution_entry_status": _get(candidate, "execution_entry_status"),
        "permission": _get(candidate, "permission"),
        "final_action": _get(candidate, "final_action"),
        "readiness": _get(candidate, "readiness"),
        "execution_allowed": _truthy(_get(candidate, "execution_allowed")),
        "eligible_for_execution": _truthy(
            _get(candidate, "eligible_for_execution", _get(candidate, "execution_allowed"))
        ),
        "tradable": _truthy(_get(candidate, "tradable")),
        "execution_blocked": _truthy(_get(candidate, "execution_blocked")),
        "execution_entry_present": _positive_number(_get(candidate, "execution_entry")),
        "hard_blockers": tuple(str(v) for v in (_get(candidate, "hard_blockers", ()) or ()) if str(v)),
        "blockers": tuple(str(v) for v in (_get(candidate, "blockers", ()) or ()) if str(v)),
    }


def _legacy_contradictions(signals: Mapping[str, Any]) -> tuple[str, ...]:
    contradictions: list[str] = []
    positive = bool(
        signals["execution_allowed"]
        or signals["eligible_for_execution"]
        or _upper(signals["execution_status"]) == "EXECUTABLE"
        or _upper(signals["execution_entry_status"]) == "EXECUTABLE"
        or _upper(signals["permission"]) == "EXECUTE"
        or _upper(signals["final_action"]) == "EXECUTE"
        or _upper(signals["readiness"]) == "READY"
    )
    negative = bool(
        signals["execution_blocked"]
        or signals["hard_blockers"]
        or signals["blockers"]
        or _upper(signals["candidate_status"]) in _NON_EXECUTABLE_VALUES
        or _upper(signals["execution_status"]) in _NON_EXECUTABLE_VALUES
        or _upper(signals["permission"]) in _NON_EXECUTABLE_VALUES
        or _upper(signals["final_action"]) in _NON_EXECUTABLE_VALUES
        or _upper(signals["readiness"]) in _NON_EXECUTABLE_VALUES
    )
    if positive and negative:
        contradictions.append("legacy_positive_and_negative_execution_signals")
    if signals["execution_allowed"] and not signals["execution_entry_present"]:
        contradictions.append("execution_allowed_without_execution_entry")
    if _upper(signals["execution_entry_status"]) == "EXECUTABLE" and not signals["execution_entry_present"]:
        contradictions.append("executable_entry_status_without_execution_entry")
    if _upper(signals["final_action"]) == "EXECUTE" and _upper(signals["permission"]) in _NON_EXECUTABLE_VALUES:
        contradictions.append("execute_action_with_non_executable_permission")
    if _upper(signals["readiness"]) == "READY" and signals["execution_blocked"]:
        contradictions.append("ready_while_execution_blocked")
    return tuple(contradictions)


def derive_canonical_execution_decision(candidate: Any) -> CanonicalExecutionDecision:
    """Derive a fail-closed decision without mutating the candidate."""
    truth = classify_executable_truth(candidate)
    signals = _legacy_signals(candidate)
    contradictions = _legacy_contradictions(signals)

    truth_reasons = tuple(str(reason) for reason in (truth.reasons or ()) if str(reason))
    explicit_blockers = tuple(
        dict.fromkeys(
            truth_reasons
            + tuple(signals["hard_blockers"])
            + tuple(signals["blockers"])
        )
    )

    explicit_block = bool(
        signals["execution_blocked"]
        or signals["hard_blockers"]
        or signals["blockers"]
        or _upper(signals["candidate_status"]) in _EXPLICIT_BLOCK_VALUES
        or _upper(signals["execution_status"]) in _EXPLICIT_BLOCK_VALUES
        or _upper(signals["permission"]) in _EXPLICIT_BLOCK_VALUES
        or _upper(signals["final_action"]) in _EXPLICIT_BLOCK_VALUES
        or _upper(signals["readiness"]) in _EXPLICIT_BLOCK_VALUES
    )

    execution_fields_complete = bool(
        signals["execution_allowed"]
        and signals["eligible_for_execution"]
        and signals["tradable"]
        and signals["execution_entry_present"]
        and _upper(signals["execution_entry_status"]) == "EXECUTABLE"
    )
    lifecycle_allows_execution = bool(
        _upper(signals["permission"]) not in _NON_EXECUTABLE_VALUES
        and _upper(signals["final_action"]) not in _NON_EXECUTABLE_VALUES
        and _upper(signals["readiness"]) not in _NON_EXECUTABLE_VALUES
        and _upper(signals["candidate_status"]) not in _NON_EXECUTABLE_VALUES
    )

    if truth.execution_allowed and execution_fields_complete and lifecycle_allows_execution and not contradictions:
        return CanonicalExecutionDecision(
            state=ExecutionState.EXECUTABLE,
            allowed=True,
            primary_reason="ok",
            blockers=(),
            contradictions=(),
            legacy_signals=signals,
            truth_context=dict(truth.context or {}),
        )

    advisory_only = bool(
        not explicit_block
        and truth_reasons
        and set(truth_reasons).issubset(_ADVISORY_REASONS)
    )
    if advisory_only:
        state = ExecutionState.ADVISORY_ONLY
        primary_reason = truth.reason_code or "advisory_only"
    else:
        state = ExecutionState.BLOCKED
        if contradictions:
            primary_reason = contradictions[0]
        elif explicit_blockers:
            primary_reason = explicit_blockers[0]
        elif not execution_fields_complete:
            primary_reason = "execution_contract_incomplete"
        else:
            primary_reason = truth.reason_code or "execution_blocked"

    blockers = tuple(dict.fromkeys(explicit_blockers + contradictions + (() if state is ExecutionState.ADVISORY_ONLY else (primary_reason,))))
    return CanonicalExecutionDecision(
        state=state,
        allowed=False,
        primary_reason=primary_reason,
        blockers=blockers,
        contradictions=contradictions,
        legacy_signals=signals,
        truth_context=dict(truth.context or {}),
    )


def compare_legacy_and_canonical(candidate: Any) -> dict[str, Any]:
    decision = derive_canonical_execution_decision(candidate)
    legacy_allowed = _truthy(_get(candidate, "execution_allowed"))
    return {
        "legacy_allowed": legacy_allowed,
        "canonical_allowed": decision.allowed,
        "match": legacy_allowed == decision.allowed,
        "decision": decision.to_payload(),
    }


__all__ = [
    "CanonicalExecutionDecision",
    "ExecutionState",
    "compare_legacy_and_canonical",
    "derive_canonical_execution_decision",
]
