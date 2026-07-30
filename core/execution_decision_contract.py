from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class ExecutionState(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    BLOCKED = "BLOCKED"


_EXECUTABLE_BLOCKING_STATES = {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK", "BLOCKED"}
_SYNTHETIC_ORIGINS = {
    "fallback",
    "fallback_min_breadth",
    "invalid_snapshot",
    "planning_only",
    "pre_builder_gate",
    "softened",
    "softened_builder_path",
}
_FALLBACK_SOURCES = {
    "fallback",
    "rest_fallback",
    "rest_recovery",
    "subscription_failed",
}


def _value(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _codes(values: Iterable[Any] | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_text(value) for value in (values or ()) if _text(value)))


@dataclass(frozen=True)
class ExecutionDecision:
    state: ExecutionState
    allowed: bool
    primary_reason: str
    blockers: tuple[str, ...]
    legacy_conflicts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "allowed": self.allowed,
            "primary_reason": self.primary_reason,
            "blockers": list(self.blockers),
            "legacy_conflicts": list(self.legacy_conflicts),
        }


def infer_execution_decision(candidate: Any) -> ExecutionDecision:
    """Infer one immutable execution decision without mutating the candidate.

    This contract is shadow-only. It intentionally uses conservative semantics:
    any fallback, synthetic origin, blocker, stale/untrusted quote, unresolved
    contract, or contradictory legacy state prevents EXECUTABLE classification.
    """

    source_flags = _value(candidate, "source_flags", {})
    if not isinstance(source_flags, Mapping):
        source_flags = {}

    blockers = list(
        _codes(
            tuple(_value(candidate, "hard_blockers", ()) or ())
            + tuple(_value(candidate, "blockers", ()) or ())
            + tuple(_value(candidate, "execution_truth_blockers", ()) or ())
            + tuple(_value(candidate, "tradable_reasons_blocking", ()) or ())
        )
    )

    origin = _text(
        _value(candidate, "candidate_origin")
        or source_flags.get("candidate_origin")
        or source_flags.get("origin")
    ).lower()
    row_kind = _text(_value(candidate, "row_kind")).lower()
    trade_id = _text(_value(candidate, "trade_id")).lower()
    quote_sources = {
        _text(_value(candidate, "quote_source") or source_flags.get("quote_source")).lower(),
        _text(_value(candidate, "option_ltp_source") or source_flags.get("option_ltp_source")).lower(),
    }
    quote_status = _text(
        _value(candidate, "quote_validation_status")
        or source_flags.get("quote_validation_status")
    ).upper()

    synthetic = (
        origin in _SYNTHETIC_ORIGINS
        or row_kind in {"recovered_fallback", "soft_reject"}
        or trade_id.startswith(("softrej_", "tbsoft_"))
        or bool(source_flags.get("recovered_fallback"))
        or bool(source_flags.get("fallback_candidate"))
    )
    if synthetic:
        blockers.append("synthetic_or_fallback_candidate")
    if quote_sources & _FALLBACK_SOURCES:
        blockers.append("fallback_quote_source")
    if quote_status in {"STALE_OPTION_LTP", "PRICE_MISMATCH", "UNTRUSTED", "SUBSCRIPTION_FAILED"}:
        blockers.append(quote_status.lower())
    if bool(_value(candidate, "unresolved_contract", False)):
        blockers.append("unresolved_contract")
    if bool(_value(candidate, "execution_blocked", False)):
        blockers.append("execution_blocked")
    if bool(_value(candidate, "execution_truth_blocked", False)):
        blockers.append("execution_truth_blocked")

    blockers = list(_codes(blockers))

    permission = _text(_value(candidate, "permission")).upper()
    final_action = _text(_value(candidate, "final_action")).upper()
    readiness = _text(_value(candidate, "readiness")).upper()
    execution_status = _text(_value(candidate, "execution_status")).upper()
    entry_status = _text(_value(candidate, "execution_entry_status")).upper()
    execution_allowed = bool(_value(candidate, "execution_allowed", False))
    eligible = bool(_value(candidate, "eligible_for_execution", execution_allowed))
    execution_entry = _value(candidate, "execution_entry")

    positive_signals = {
        "execution_allowed": execution_allowed,
        "eligible_for_execution": eligible,
        "permission_execute": permission == "EXECUTE",
        "final_action_execute": final_action == "EXECUTE",
        "readiness_ready": readiness == "READY",
        "execution_status_executable": execution_status == "EXECUTABLE",
        "entry_status_executable": entry_status == "EXECUTABLE",
        "execution_entry_present": execution_entry not in (None, "", "None"),
    }
    negative_signals = {
        "permission": permission in _EXECUTABLE_BLOCKING_STATES,
        "final_action": final_action in _EXECUTABLE_BLOCKING_STATES,
        "readiness": readiness in _EXECUTABLE_BLOCKING_STATES,
        "execution_status": execution_status in _EXECUTABLE_BLOCKING_STATES,
    }

    conflicts: list[str] = []
    if any(positive_signals.values()) and any(negative_signals.values()):
        conflicts.append("positive_and_negative_legacy_execution_signals")
    if execution_allowed and not eligible:
        conflicts.append("execution_allowed_but_not_eligible")
    if execution_allowed and execution_entry in (None, "", "None"):
        conflicts.append("execution_allowed_without_execution_entry")
    if blockers and any(positive_signals.values()):
        conflicts.append("blocked_candidate_has_positive_execution_signals")

    executable = (
        not blockers
        and not conflicts
        and execution_allowed
        and eligible
        and execution_entry not in (None, "", "None")
        and entry_status == "EXECUTABLE"
        and execution_status == "EXECUTABLE"
        and permission not in _EXECUTABLE_BLOCKING_STATES
        and final_action not in _EXECUTABLE_BLOCKING_STATES
        and readiness not in _EXECUTABLE_BLOCKING_STATES
    )
    if executable:
        return ExecutionDecision(
            state=ExecutionState.EXECUTABLE,
            allowed=True,
            primary_reason="execution_contract_satisfied",
            blockers=(),
            legacy_conflicts=(),
        )

    advisory_markers = {
        permission,
        final_action,
        readiness,
        execution_status,
    } & {"ADVISORY_ONLY", "QUEUE_ONLY", "SCORED", "RANKED"}
    state = ExecutionState.ADVISORY_ONLY if advisory_markers or synthetic else ExecutionState.BLOCKED
    reasons = tuple(blockers) + tuple(conflicts)
    primary_reason = reasons[0] if reasons else "execution_contract_incomplete"
    return ExecutionDecision(
        state=state,
        allowed=False,
        primary_reason=primary_reason,
        blockers=tuple(blockers),
        legacy_conflicts=tuple(conflicts),
    )


__all__ = ["ExecutionDecision", "ExecutionState", "infer_execution_decision"]
