"""Final read-only edge readiness report for EDGE-97.

This module consumes EDGE-96 live-pilot risk throttle evidence and emits a final
readiness verdict for controlled review. It is evidence-only: no brokers, no
order lifecycle changes, no runtime wiring, no ranking changes, no strategy
changes, and no dashboard behavior.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.live_pilot_risk_throttle import LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE, LIVE_PILOT_THROTTLE_PASSED

FINAL_EDGE_READINESS_SCHEMA_VERSION = 1
FINAL_EDGE_READINESS_SOURCE = "final_edge_readiness_report_v1"

FINAL_EDGE_READINESS_PASSED = "FINAL_EDGE_READINESS_PASSED"
FINAL_EDGE_READINESS_BLOCKED = "FINAL_EDGE_READINESS_BLOCKED"

FINAL_EDGE_CANDIDATE_READY = "EDGE_READY_FOR_CONTROLLED_REVIEW"
FINAL_EDGE_CANDIDATE_BLOCKED = "EDGE_READINESS_BLOCKED"

REASON_THROTTLE_MISSING = "LIVE_PILOT_THROTTLE_MISSING"
REASON_THROTTLE_BLOCKED = "LIVE_PILOT_THROTTLE_BLOCKED"
REASON_NO_REVIEW_ALLOWED_CANDIDATES = "NO_REVIEW_ALLOWED_CANDIDATES"
REASON_CANDIDATE_NOT_REVIEW_ALLOWED = "CANDIDATE_NOT_REVIEW_ALLOWED"
REASON_ACTION_EVIDENCE_NOT_ALLOWED = "ACTION_EVIDENCE_NOT_ALLOWED"
REASON_BROKER_EVIDENCE_NOT_ALLOWED = "BROKER_EVIDENCE_NOT_ALLOWED"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class FinalEdgeCandidateReadiness:
    """Per-candidate final edge readiness result."""

    candidate_id: str
    status: str
    ready: bool
    reasons: tuple[str, ...]
    throttle_status: str
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
            "ready": self.ready,
            "reasons": list(self.reasons),
            "throttle_status": self.throttle_status,
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class FinalEdgeReadinessReport:
    """Top-level read-only EDGE-97 final readiness report."""

    schema_version: int
    source: str
    status: str
    candidate_count: int
    ready_candidate_count: int
    blocked_candidate_count: int
    reasons: tuple[str, ...]
    candidates: tuple[FinalEdgeCandidateReadiness, ...]
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
            "status": self.status,
            "candidate_count": self.candidate_count,
            "ready_candidate_count": self.ready_candidate_count,
            "blocked_candidate_count": self.blocked_candidate_count,
            "reasons": list(self.reasons),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


def build_final_edge_readiness_report(
    live_pilot_throttle: Any | Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> FinalEdgeReadinessReport:
    """Build the final EDGE readiness verdict from EDGE-96 throttle evidence."""

    throttle_payload = _payload(live_pilot_throttle)
    report_reasons: list[str] = []
    if throttle_payload is None:
        report_reasons.append(REASON_THROTTLE_MISSING)

    throttle_status = str((throttle_payload or {}).get("status") or "MISSING")
    if throttle_payload is not None and throttle_status != LIVE_PILOT_THROTTLE_PASSED:
        report_reasons.append(REASON_THROTTLE_BLOCKED)
    if throttle_payload is not None and _contains_action_or_broker_boundary(throttle_payload):
        report_reasons.extend((REASON_ACTION_EVIDENCE_NOT_ALLOWED, REASON_BROKER_EVIDENCE_NOT_ALLOWED))

    candidates = tuple(sorted(_candidate_payloads(throttle_payload), key=_candidate_sort_key))
    decisions = tuple(
        _candidate_readiness(candidate, throttle_status=throttle_status, report_reasons=tuple(report_reasons))
        for candidate in candidates
    )

    if not any(candidate.ready for candidate in decisions):
        report_reasons.append(REASON_NO_REVIEW_ALLOWED_CANDIDATES)

    reasons = _dedupe((*report_reasons, *(reason for decision in decisions for reason in decision.reasons)))
    ready_count = sum(1 for decision in decisions if decision.ready)
    blocked_count = sum(1 for decision in decisions if not decision.ready)
    status = FINAL_EDGE_READINESS_PASSED if decisions and ready_count == len(decisions) and not reasons else FINAL_EDGE_READINESS_BLOCKED

    return FinalEdgeReadinessReport(
        schema_version=FINAL_EDGE_READINESS_SCHEMA_VERSION,
        source=FINAL_EDGE_READINESS_SOURCE,
        status=status,
        candidate_count=len(decisions),
        ready_candidate_count=ready_count,
        blocked_candidate_count=blocked_count,
        reasons=reasons,
        candidates=decisions,
        metadata={
            "evidence_only": True,
            "final_edge_report": True,
            "controlled_review_only": True,
            "requires_live_pilot_throttle_passed": True,
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


def _candidate_readiness(
    candidate: Mapping[str, Any],
    *,
    throttle_status: str,
    report_reasons: tuple[str, ...],
) -> FinalEdgeCandidateReadiness:
    reasons = list(report_reasons)
    review_allowed = _candidate_review_allowed(candidate)
    if throttle_status != LIVE_PILOT_THROTTLE_PASSED:
        reasons.append(REASON_THROTTLE_BLOCKED)
    if not review_allowed:
        reasons.append(REASON_CANDIDATE_NOT_REVIEW_ALLOWED)
    if _contains_action_or_broker_boundary(candidate):
        reasons.extend((REASON_ACTION_EVIDENCE_NOT_ALLOWED, REASON_BROKER_EVIDENCE_NOT_ALLOWED))

    clean_reasons = _dedupe(reasons)
    ready = review_allowed and throttle_status == LIVE_PILOT_THROTTLE_PASSED and not clean_reasons
    return FinalEdgeCandidateReadiness(
        candidate_id=_candidate_id(candidate),
        status=FINAL_EDGE_CANDIDATE_READY if ready else FINAL_EDGE_CANDIDATE_BLOCKED,
        ready=ready,
        reasons=clean_reasons,
        throttle_status=throttle_status,
        metadata={
            "strategy_id": _metadata_value(candidate, "strategy_id"),
            "symbol": _metadata_value(candidate, "symbol"),
            "direction": _metadata_value(candidate, "direction"),
            "source_candidate_status": candidate.get("status"),
            "review_allowed": review_allowed,
            "controlled_review_only": True,
            "evidence_only": True,
        },
    )


def _candidate_payloads(throttle_payload: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(throttle_payload, Mapping):
        return ()
    raw_candidates = throttle_payload.get("candidates")
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


def _candidate_review_allowed(candidate: Mapping[str, Any]) -> bool:
    if isinstance(candidate.get("review_allowed"), bool):
        return bool(candidate.get("review_allowed"))
    return str(candidate.get("status") or "") == LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("candidate_id") or candidate.get("trade_key") or candidate.get("id")
    return str(value or "UNKNOWN_CANDIDATE").strip() or "UNKNOWN_CANDIDATE"


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _candidate_id(candidate),
        str(_metadata_value(candidate, "strategy_id") or ""),
        str(_metadata_value(candidate, "symbol") or ""),
    )


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
    "FINAL_EDGE_CANDIDATE_BLOCKED",
    "FINAL_EDGE_CANDIDATE_READY",
    "FINAL_EDGE_READINESS_BLOCKED",
    "FINAL_EDGE_READINESS_PASSED",
    "FINAL_EDGE_READINESS_SCHEMA_VERSION",
    "FINAL_EDGE_READINESS_SOURCE",
    "REASON_CANDIDATE_NOT_REVIEW_ALLOWED",
    "REASON_NO_REVIEW_ALLOWED_CANDIDATES",
    "REASON_THROTTLE_BLOCKED",
    "REASON_THROTTLE_MISSING",
    "FinalEdgeCandidateReadiness",
    "FinalEdgeReadinessReport",
    "build_final_edge_readiness_report",
]
