"""Read-only paper-only edge gate for EDGE-95.

This module consumes EDGE-94 acceptance evidence and determines whether accepted
candidates are eligible for paper-only progression. It does not call brokers,
change runtime state, generate candidates, rank candidates, execute trades, write
artifacts, or wire dashboard behavior.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.end_to_end_edge_acceptance_suite import EDGE_ACCEPTANCE_SUITE_PASSED, EDGE_CANDIDATE_ACCEPTED

PAPER_EDGE_GATE_SCHEMA_VERSION = 1
PAPER_EDGE_GATE_SOURCE = "paper_only_edge_gate_v1"

PAPER_EDGE_GATE_PASSED = "PAPER_EDGE_GATE_PASSED"
PAPER_EDGE_GATE_BLOCKED = "PAPER_EDGE_GATE_BLOCKED"

PAPER_CANDIDATE_ELIGIBLE = "PAPER_ELIGIBLE"
PAPER_CANDIDATE_BLOCKED = "PAPER_BLOCKED"

PAPER_MODE = "PAPER"

REASON_EDGE_ACCEPTANCE_MISSING = "EDGE_ACCEPTANCE_MISSING"
REASON_EDGE_ACCEPTANCE_BLOCKED = "EDGE_ACCEPTANCE_BLOCKED"
REASON_NO_ACCEPTED_CANDIDATES = "NO_ACCEPTED_CANDIDATES"
REASON_NOT_PAPER_MODE = "NOT_PAPER_MODE"
REASON_CANDIDATE_NOT_ACCEPTED = "CANDIDATE_NOT_ACCEPTED"
REASON_ACTION_EVIDENCE_NOT_ALLOWED = "ACTION_EVIDENCE_NOT_ALLOWED"
REASON_BROKER_EVIDENCE_NOT_ALLOWED = "BROKER_EVIDENCE_NOT_ALLOWED"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class PaperEdgeCandidateDecision:
    """Per-candidate paper-only gate decision."""

    candidate_id: str
    status: str
    paper_allowed: bool
    reasons: tuple[str, ...]
    edge_acceptance_status: str
    read_only: bool = True
    append: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "paper_allowed": self.paper_allowed,
            "reasons": list(self.reasons),
            "edge_acceptance_status": self.edge_acceptance_status,
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class PaperOnlyEdgeGateReport:
    """Top-level read-only EDGE-95 paper-only gate report."""

    schema_version: int
    source: str
    mode: str
    status: str
    candidate_count: int
    paper_allowed_count: int
    paper_blocked_count: int
    reasons: tuple[str, ...]
    candidates: tuple[PaperEdgeCandidateDecision, ...]
    read_only: bool = True
    append: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "mode": self.mode,
            "status": self.status,
            "candidate_count": self.candidate_count,
            "paper_allowed_count": self.paper_allowed_count,
            "paper_blocked_count": self.paper_blocked_count,
            "reasons": list(self.reasons),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


def build_paper_only_edge_gate_report(
    edge_acceptance: Any | Mapping[str, Any] | None,
    *,
    mode: str,
    metadata: Mapping[str, Any] | None = None,
) -> PaperOnlyEdgeGateReport:
    """Build paper-only eligibility from EDGE-94 acceptance evidence.

    The gate fails closed unless mode is explicitly PAPER and EDGE-94 acceptance
    evidence is present, passed, and candidate-level acceptance is true.
    """

    normalized_mode = str(mode or "").strip().upper()
    acceptance_payload = _payload(edge_acceptance)
    report_reasons: list[str] = []

    if normalized_mode != PAPER_MODE:
        report_reasons.append(REASON_NOT_PAPER_MODE)
    if acceptance_payload is None:
        report_reasons.append(REASON_EDGE_ACCEPTANCE_MISSING)

    acceptance_status = str((acceptance_payload or {}).get("status") or "MISSING")
    if acceptance_payload is not None and acceptance_status != EDGE_ACCEPTANCE_SUITE_PASSED:
        report_reasons.append(REASON_EDGE_ACCEPTANCE_BLOCKED)
    if acceptance_payload is not None and _contains_action_or_broker_boundary(acceptance_payload):
        report_reasons.extend((REASON_ACTION_EVIDENCE_NOT_ALLOWED, REASON_BROKER_EVIDENCE_NOT_ALLOWED))

    candidate_payloads = _candidate_payloads(acceptance_payload)
    decisions = tuple(
        _candidate_decision(
            candidate,
            mode=normalized_mode,
            acceptance_status=acceptance_status,
            report_reasons=tuple(report_reasons),
        )
        for candidate in sorted(candidate_payloads, key=_candidate_sort_key)
    )

    if not any(candidate.paper_allowed for candidate in decisions):
        report_reasons.append(REASON_NO_ACCEPTED_CANDIDATES)

    reasons = _dedupe((*report_reasons, *(reason for decision in decisions for reason in decision.reasons)))
    allowed_count = sum(1 for decision in decisions if decision.paper_allowed)
    blocked_count = sum(1 for decision in decisions if not decision.paper_allowed)
    status = PAPER_EDGE_GATE_PASSED if decisions and allowed_count == len(decisions) and not reasons else PAPER_EDGE_GATE_BLOCKED

    return PaperOnlyEdgeGateReport(
        schema_version=PAPER_EDGE_GATE_SCHEMA_VERSION,
        source=PAPER_EDGE_GATE_SOURCE,
        mode=normalized_mode,
        status=status,
        candidate_count=len(decisions),
        paper_allowed_count=allowed_count,
        paper_blocked_count=blocked_count,
        reasons=reasons,
        candidates=decisions,
        metadata={
            "evidence_only": True,
            "paper_only": True,
            "requires_edge_acceptance_passed": True,
            "fail_closed_on_missing_acceptance": True,
            "does_not_call_brokers": True,
            "does_not_create_live_orders": True,
            "does_not_generate_candidates": True,
            "does_not_rank_candidates": True,
            "does_not_change_strategies": True,
            "does_not_wire_runtime": True,
            "does_not_wire_dashboard": True,
            **dict(metadata or {}),
        },
    )


def _candidate_decision(
    candidate: Mapping[str, Any],
    *,
    mode: str,
    acceptance_status: str,
    report_reasons: tuple[str, ...],
) -> PaperEdgeCandidateDecision:
    reasons: list[str] = list(report_reasons)
    accepted = bool(candidate.get("accepted")) or str(candidate.get("status") or "") == EDGE_CANDIDATE_ACCEPTED
    if mode != PAPER_MODE:
        reasons.append(REASON_NOT_PAPER_MODE)
    if acceptance_status != EDGE_ACCEPTANCE_SUITE_PASSED:
        reasons.append(REASON_EDGE_ACCEPTANCE_BLOCKED)
    if not accepted:
        reasons.append(REASON_CANDIDATE_NOT_ACCEPTED)
    if _contains_action_or_broker_boundary(candidate):
        reasons.extend((REASON_ACTION_EVIDENCE_NOT_ALLOWED, REASON_BROKER_EVIDENCE_NOT_ALLOWED))

    clean_reasons = _dedupe(reasons)
    paper_allowed = accepted and mode == PAPER_MODE and acceptance_status == EDGE_ACCEPTANCE_SUITE_PASSED and not clean_reasons
    return PaperEdgeCandidateDecision(
        candidate_id=_candidate_id(candidate),
        status=PAPER_CANDIDATE_ELIGIBLE if paper_allowed else PAPER_CANDIDATE_BLOCKED,
        paper_allowed=paper_allowed,
        reasons=clean_reasons,
        edge_acceptance_status=acceptance_status,
        metadata={
            "source_candidate_status": candidate.get("status"),
            "strategy_id": _metadata_value(candidate, "strategy_id"),
            "symbol": _metadata_value(candidate, "symbol"),
            "direction": _metadata_value(candidate, "direction"),
            "paper_only": True,
            "evidence_only": True,
        },
    )


def _candidate_payloads(acceptance_payload: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(acceptance_payload, Mapping):
        return ()
    raw_candidates = acceptance_payload.get("candidates")
    if not isinstance(raw_candidates, Iterable) or isinstance(raw_candidates, (str, bytes, Mapping)):
        return ()
    return tuple(payload for item in raw_candidates if (payload := _payload(item)) is not None)


def _payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    for method_name in ("to_payload", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            out = method()
            return dict(out) if isinstance(out, Mapping) else None
    return None


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("candidate_id") or candidate.get("trade_key") or candidate.get("id")
    return str(value or "UNKNOWN_CANDIDATE").strip() or "UNKNOWN_CANDIDATE"


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str]:
    return (_candidate_id(candidate), str(_metadata_value(candidate, "strategy_id") or ""))


def _metadata_value(candidate: Mapping[str, Any], key: str) -> Any:
    if key in candidate:
        return candidate.get(key)
    metadata = candidate.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _contains_action_or_broker_boundary(payload: Mapping[str, Any]) -> bool:
    if _has_truthy(payload, _ACTION_KEY) or _has_truthy(payload, _BROKER_KEY):
        return True
    if _has_truthy(payload, "live_order_action") or _has_truthy(payload, "broker_order_action"):
        return True
    for key in ("candidates", "stage_evidence"):
        nested = payload.get(key)
        if isinstance(nested, Iterable) and not isinstance(nested, (str, bytes, Mapping)):
            for item in nested:
                nested_payload = _payload(item)
                if nested_payload is not None and _contains_action_or_broker_boundary(nested_payload):
                    return True
    return False


def _has_truthy(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "required", "blocked"}


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "PAPER_CANDIDATE_BLOCKED",
    "PAPER_CANDIDATE_ELIGIBLE",
    "PAPER_EDGE_GATE_BLOCKED",
    "PAPER_EDGE_GATE_PASSED",
    "PAPER_EDGE_GATE_SCHEMA_VERSION",
    "PAPER_EDGE_GATE_SOURCE",
    "PAPER_MODE",
    "REASON_CANDIDATE_NOT_ACCEPTED",
    "REASON_EDGE_ACCEPTANCE_BLOCKED",
    "REASON_EDGE_ACCEPTANCE_MISSING",
    "REASON_NO_ACCEPTED_CANDIDATES",
    "REASON_NOT_PAPER_MODE",
    "PaperEdgeCandidateDecision",
    "PaperOnlyEdgeGateReport",
    "build_paper_only_edge_gate_report",
]
