"""Authoritative execution-selection and operator-view cutover.

This module converts fragmented candidate fields into one immutable authority
answer. It is feed-agnostic: it reads existing quote/feed evidence but never
subscribes, reconnects, places orders, or mutates MEG state.
"""
from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass
from typing import Any, Iterable, Mapping

from config import config as cfg
from core.canonical_execution_decision import (
    ExecutionState,
    derive_canonical_execution_decision,
)
from core.live_fallback_execution_contract import (
    enforce_live_fallback_execution_contract,
    is_fallback_execution_candidate,
)

AUTHORITY_SCHEMA_VERSION = 1
_AUTHORITY_EVIDENCE_FIELDS = {
    "authority_state",
    "authority_allowed",
    "canonical_execution_decision",
    "execution_allowed",
    "eligible_for_execution",
    "execution_entry_status",
    "execution_blocked",
    "permission",
    "final_action",
}


def _get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _mapping(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        return dict(candidate)
    if is_dataclass(candidate):
        row = {
            item.name: getattr(candidate, item.name)
            for item in fields(candidate)
        }
        # Frozen dataclasses used by the runtime are not slotted. Authority
        # evidence is attached to a shallow copy via object.__setattr__, so
        # include those dynamic attributes when the router reads the object.
        try:
            row.update(vars(candidate))
        except Exception:
            pass
        return row
    try:
        return dict(vars(candidate))
    except Exception:
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return float(default)
    return float(default) if number != number else number


def _mode(mode: str | None) -> str:
    return str(
        mode or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM"
    ).strip().upper()


def _diagnostic_score(row: Mapping[str, Any]) -> float:
    for field in (
        "diagnostic_score",
        "opportunity_score",
        "final_score",
        "priority_score",
        "rank_score",
        "confidence_final",
        "confidence",
        "confidence_raw",
    ):
        value = row.get(field)
        if value not in (None, "", "None"):
            return max(0.0, _safe_float(value))
    return 0.0


def _selection_score(row: Mapping[str, Any]) -> float:
    for field in (
        "selection_score",
        "priority_score",
        "final_score",
        "opportunity_score",
        "execution_score",
        "rank_score",
        "confidence_final",
        "confidence",
    ):
        value = row.get(field)
        if value not in (None, "", "None"):
            return max(0.0, _safe_float(value))
    return 0.0


def has_runtime_authority_evidence(candidate: Any) -> bool:
    row = _mapping(candidate)
    return any(field in row for field in _AUTHORITY_EVIDENCE_FIELDS)


def _operator_bucket(
    row: Mapping[str, Any], state: ExecutionState
) -> str:
    if state is ExecutionState.EXECUTABLE:
        return "TOP_EXECUTABLE"
    # Fallback rows remain visible as advisory evidence, never as executable.
    if is_fallback_execution_candidate(row):
        return "ADVISORY_ONLY"
    if state is ExecutionState.ADVISORY_ONLY:
        return "ADVISORY_ONLY"
    return "BLOCKED_DEBUG"


def authority_payload(
    candidate: Any, *, mode: str | None = None
) -> dict[str, Any]:
    runtime_mode = _mode(mode)
    row = _mapping(candidate)
    if runtime_mode in {"LIVE", "REAL"}:
        row = enforce_live_fallback_execution_contract(row, runtime_mode)
    decision = derive_canonical_execution_decision(row)
    diagnostic = _diagnostic_score(row)
    opportunity = max(
        0.0,
        _safe_float(row.get("opportunity_score"), diagnostic),
    )
    selection = _selection_score(row) if decision.allowed else 0.0
    bucket = _operator_bucket(row, decision.state)
    return {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "mode": runtime_mode,
        "state": decision.state.value,
        "allowed": bool(decision.allowed),
        "primary_reason": decision.primary_reason,
        "blockers": list(decision.blockers),
        "contradictions": list(decision.contradictions),
        "operator_bucket": bucket,
        "diagnostic_score": diagnostic,
        "opportunity_score": opportunity,
        "selection_score": selection,
        "decision": decision.to_payload(),
        "is_order_action": False,
    }


def _updates(candidate: Any, *, mode: str | None = None) -> dict[str, Any]:
    row = _mapping(candidate)
    runtime_mode = _mode(mode)
    payload = authority_payload(row, mode=runtime_mode)
    allowed = bool(payload["allowed"])
    state = str(payload["state"])
    bucket = str(payload["operator_bucket"])
    updates: dict[str, Any] = {
        "authority_schema_version": AUTHORITY_SCHEMA_VERSION,
        "authority_state": state,
        "authority_allowed": allowed,
        "authority_reason": payload["primary_reason"],
        "authority_blockers": list(payload["blockers"]),
        "operator_bucket": bucket,
        "canonical_execution_decision": dict(payload["decision"]),
        "diagnostic_score": float(payload["diagnostic_score"]),
        "opportunity_score": float(payload["opportunity_score"]),
        "selection_score": float(payload["selection_score"]),
    }
    if not allowed:
        updates.update(
            {
                "execution_allowed": False,
                "eligible_for_execution": False,
                "truth_allows_execution": False,
                "tradable": False,
                "execution_ok": False,
                "execution_blocked": True,
                "selected_for_execution": False,
                "portfolio_optimization_selected": False,
                "capital_assigned": 0.0,
                "allocated_capital": 0.0,
                "position_size_estimate": 0.0,
                "slot_id": None,
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "max_final_action": "QUEUE_ONLY",
                "execution_status": "not_executable",
                "execution_entry_status": "not_executable",
                "candidate_status": (
                    "advisory"
                    if bucket == "ADVISORY_ONLY"
                    else "blocked"
                ),
            }
        )
        # Preserve the legacy display-only reason contract in non-live modes.
        # LIVE/REAL authority continues to fail closed from canonical evidence;
        # this field is diagnostic only and cannot restore execution authority.
        if runtime_mode not in {"LIVE", "REAL"} and _get(row, "reason") in (
            None,
            "",
            "None",
        ):
            selection_reason = str(
                _get(row, "selection_reason") or "not_execution_eligible"
            )
            updates["reason"] = f"opportunity_{selection_reason}"
    return updates


def _stamp_dataclass_copy(
    candidate: Any, updates: Mapping[str, Any]
) -> Any:
    """Stamp a frozen dataclass copy without re-running ``__post_init__``.

    ``dataclasses.replace`` is unsafe for the repository's frozen Trade model:
    its post-init compatibility normalization writes metadata. A shallow copy
    preserves class identity and existing normalized fields; object.__setattr__
    then applies authority truth only to the copy.
    """
    out = copy.copy(candidate)
    deferred: dict[str, Any] = {}
    for key, value in updates.items():
        try:
            object.__setattr__(out, key, value)
        except Exception:
            deferred[key] = value
    if deferred and hasattr(out, "metadata"):
        metadata = dict(getattr(out, "metadata", {}) or {})
        metadata.update(deferred)
        try:
            object.__setattr__(out, "metadata", metadata)
        except Exception:
            pass
    return out


def apply_runtime_authority(
    candidate: Any, *, mode: str | None = None
) -> Any:
    """Return a same-shape candidate stamped with authoritative truth."""
    updates = _updates(candidate, mode=mode)
    if isinstance(candidate, Mapping):
        out = dict(candidate)
        out.update(updates)
        return out
    if is_dataclass(candidate):
        return _stamp_dataclass_copy(candidate, updates)
    try:
        out = copy.copy(candidate)
    except Exception:
        out = candidate
    for key, value in updates.items():
        try:
            setattr(out, key, value)
        except Exception:
            pass
    return out


def authority_allows_execution(candidate: Any) -> bool:
    return bool(_get(candidate, "authority_allowed", False)) and str(
        _get(candidate, "authority_state", "")
    ).upper() == ExecutionState.EXECUTABLE.value


def normalize_selection_result(
    result: Any, *, mode: str | None = None
) -> Any:
    if result is None:
        return None
    if isinstance(result, tuple):
        return tuple(
            normalize_selection_result(item, mode=mode)
            for item in result
        )
    if isinstance(result, list):
        return [apply_runtime_authority(item, mode=mode) for item in result]
    if isinstance(result, Mapping) or hasattr(result, "__dict__"):
        return apply_runtime_authority(result, mode=mode)
    return result


def partition_operator_candidates(
    candidates: Iterable[Any], *, mode: str | None = None
) -> dict[str, list[Any]]:
    stamped = [
        apply_runtime_authority(candidate, mode=mode)
        for candidate in candidates
    ]
    executable = [
        row for row in stamped if authority_allows_execution(row)
    ]
    advisory = [
        row
        for row in stamped
        if _get(row, "operator_bucket") == "ADVISORY_ONLY"
    ]
    blocked = [
        row
        for row in stamped
        if _get(row, "operator_bucket") == "BLOCKED_DEBUG"
    ]
    executable.sort(
        key=lambda row: _safe_float(_get(row, "selection_score")),
        reverse=True,
    )
    advisory.sort(
        key=lambda row: _safe_float(_get(row, "diagnostic_score")),
        reverse=True,
    )
    blocked.sort(
        key=lambda row: _safe_float(_get(row, "diagnostic_score")),
        reverse=True,
    )
    return {
        "top_executable": executable,
        "advisory": advisory,
        "blocked_debug": blocked,
        "all_candidates": stamped,
    }


def preflight_execution_authority(
    candidate: Any, *, mode: str | None = None
) -> dict[str, Any] | None:
    """Final router firewall for cutover-stamped candidates.

    Legacy tests/tools that do not yet carry authority evidence retain their old
    behavior. Every candidate emitted by the cutover is stamped, so runtime
    selection cannot bypass this firewall.
    """
    if not has_runtime_authority_evidence(candidate):
        return None
    payload = authority_payload(candidate, mode=mode)
    return {
        "allowed": bool(payload["allowed"]),
        "state": payload["state"],
        "reason": payload["primary_reason"],
        "blockers": list(payload["blockers"]),
        "selection_score": float(payload["selection_score"]),
        "operator_bucket": payload["operator_bucket"],
    }


__all__ = [
    "AUTHORITY_SCHEMA_VERSION",
    "apply_runtime_authority",
    "authority_allows_execution",
    "authority_payload",
    "has_runtime_authority_evidence",
    "normalize_selection_result",
    "partition_operator_candidates",
    "preflight_execution_authority",
]
