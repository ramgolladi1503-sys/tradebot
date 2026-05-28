"""Read-only live-pilot review risk throttle for EDGE-96.

The throttle consumes EDGE-95 paper-only gate evidence and decides whether
paper-eligible candidates are permitted to enter live-pilot review. It is a
non-action evidence layer only: no brokers, no order lifecycle changes, no
runtime wiring, no ranking changes, and no strategy changes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.paper_only_edge_gate import PAPER_CANDIDATE_ELIGIBLE, PAPER_EDGE_GATE_PASSED, PAPER_MODE

LIVE_PILOT_RISK_THROTTLE_SCHEMA_VERSION = 1
LIVE_PILOT_RISK_THROTTLE_SOURCE = "live_pilot_risk_throttle_v1"

LIVE_PILOT_THROTTLE_PASSED = "LIVE_PILOT_THROTTLE_PASSED"
LIVE_PILOT_THROTTLE_BLOCKED = "LIVE_PILOT_THROTTLE_BLOCKED"

LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE = "LIVE_PILOT_REVIEW_ELIGIBLE"
LIVE_PILOT_CANDIDATE_BLOCKED = "LIVE_PILOT_BLOCKED"

REASON_PAPER_GATE_MISSING = "PAPER_GATE_MISSING"
REASON_PAPER_GATE_BLOCKED = "PAPER_GATE_BLOCKED"
REASON_NOT_PAPER_MODE = "NOT_PAPER_MODE"
REASON_NO_PAPER_ALLOWED_CANDIDATES = "NO_PAPER_ALLOWED_CANDIDATES"
REASON_CANDIDATE_NOT_PAPER_ALLOWED = "CANDIDATE_NOT_PAPER_ALLOWED"
REASON_MAX_CANDIDATES_EXCEEDED = "MAX_CANDIDATES_EXCEEDED"
REASON_MAX_PER_STRATEGY_EXCEEDED = "MAX_PER_STRATEGY_EXCEEDED"
REASON_SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
REASON_SYMBOL_BLOCKED = "SYMBOL_BLOCKED"
REASON_INVALID_THROTTLE_LIMIT = "INVALID_THROTTLE_LIMIT"
REASON_ACTION_EVIDENCE_NOT_ALLOWED = "ACTION_EVIDENCE_NOT_ALLOWED"
REASON_BROKER_EVIDENCE_NOT_ALLOWED = "BROKER_EVIDENCE_NOT_ALLOWED"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class LivePilotCandidateThrottleDecision:
    """Per-candidate live-pilot review throttle decision."""

    candidate_id: str
    status: str
    review_allowed: bool
    reasons: tuple[str, ...]
    paper_gate_status: str
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
            "review_allowed": self.review_allowed,
            "reasons": list(self.reasons),
            "paper_gate_status": self.paper_gate_status,
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class LivePilotRiskThrottleReport:
    """Top-level read-only EDGE-96 live-pilot review throttle report."""

    schema_version: int
    source: str
    status: str
    candidate_count: int
    review_allowed_count: int
    review_blocked_count: int
    reasons: tuple[str, ...]
    candidates: tuple[LivePilotCandidateThrottleDecision, ...]
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
            "review_allowed_count": self.review_allowed_count,
            "review_blocked_count": self.review_blocked_count,
            "reasons": list(self.reasons),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


def build_live_pilot_risk_throttle_report(
    paper_gate: Any | Mapping[str, Any] | None,
    *,
    max_candidates: int = 1,
    max_per_strategy: int = 1,
    allowed_symbols: Iterable[str] | None = None,
    blocked_symbols: Iterable[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> LivePilotRiskThrottleReport:
    """Build read-only live-pilot review eligibility from EDGE-95 evidence.

    The throttle fails closed unless EDGE-95 evidence is present, passed, PAPER
    mode, and each candidate remains within deterministic throttle limits.
    """

    paper_payload = _payload(paper_gate)
    report_reasons: list[str] = []
    if max_candidates < 1 or max_per_strategy < 1:
        report_reasons.append(REASON_INVALID_THROTTLE_LIMIT)
    if paper_payload is None:
        report_reasons.append(REASON_PAPER_GATE_MISSING)

    paper_status = str((paper_payload or {}).get("status") or "MISSING")
    paper_mode = str((paper_payload or {}).get("mode") or "").strip().upper()
    if paper_payload is not None and paper_status != PAPER_EDGE_GATE_PASSED:
        report_reasons.append(REASON_PAPER_GATE_BLOCKED)
    if paper_payload is not None and paper_mode != PAPER_MODE:
        report_reasons.append(REASON_NOT_PAPER_MODE)
    if paper_payload is not None and _contains_action_or_broker_boundary(paper_payload):
        report_reasons.extend((REASON_ACTION_EVIDENCE_NOT_ALLOWED, REASON_BROKER_EVIDENCE_NOT_ALLOWED))

    allowed_symbol_set = _symbol_set(allowed_symbols)
    blocked_symbol_set = _symbol_set(blocked_symbols)
    candidates = tuple(sorted(_candidate_payloads(paper_payload), key=_candidate_sort_key))
    eligible_seen = 0
    strategy_seen: dict[str, int] = {}
    decisions: list[LivePilotCandidateThrottleDecision] = []

    for candidate in candidates:
        candidate_id = _candidate_id(candidate)
        strategy_id = _strategy_id(candidate)
        symbol = _symbol(candidate)
        candidate_reasons = list(report_reasons)
        paper_allowed = _candidate_paper_allowed(candidate)
        if not paper_allowed:
            candidate_reasons.append(REASON_CANDIDATE_NOT_PAPER_ALLOWED)
        if allowed_symbol_set and symbol and symbol not in allowed_symbol_set:
            candidate_reasons.append(REASON_SYMBOL_NOT_ALLOWED)
        if symbol and symbol in blocked_symbol_set:
            candidate_reasons.append(REASON_SYMBOL_BLOCKED)
        if _contains_action_or_broker_boundary(candidate):
            candidate_reasons.extend((REASON_ACTION_EVIDENCE_NOT_ALLOWED, REASON_BROKER_EVIDENCE_NOT_ALLOWED))

        would_count = paper_allowed and not candidate_reasons
        if would_count:
            if eligible_seen >= max_candidates:
                candidate_reasons.append(REASON_MAX_CANDIDATES_EXCEEDED)
            strategy_count = strategy_seen.get(strategy_id, 0)
            if strategy_count >= max_per_strategy:
                candidate_reasons.append(REASON_MAX_PER_STRATEGY_EXCEEDED)

        clean_reasons = _dedupe(candidate_reasons)
        review_allowed = paper_allowed and not clean_reasons
        if review_allowed:
            eligible_seen += 1
            strategy_seen[strategy_id] = strategy_seen.get(strategy_id, 0) + 1
        decisions.append(
            LivePilotCandidateThrottleDecision(
                candidate_id=candidate_id,
                status=LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE if review_allowed else LIVE_PILOT_CANDIDATE_BLOCKED,
                review_allowed=review_allowed,
                reasons=clean_reasons,
                paper_gate_status=paper_status,
                metadata={
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "direction": _metadata_value(candidate, "direction"),
                    "source_candidate_status": candidate.get("status"),
                    "paper_allowed": paper_allowed,
                    "review_only": True,
                    "evidence_only": True,
                },
            )
        )

    if not any(candidate.review_allowed for candidate in decisions):
        report_reasons.append(REASON_NO_PAPER_ALLOWED_CANDIDATES)

    reasons = _dedupe((*report_reasons, *(reason for decision in decisions for reason in decision.reasons)))
    review_allowed_count = sum(1 for decision in decisions if decision.review_allowed)
    review_blocked_count = sum(1 for decision in decisions if not decision.review_allowed)
    status = (
        LIVE_PILOT_THROTTLE_PASSED
        if decisions and review_allowed_count == len(decisions) and not reasons
        else LIVE_PILOT_THROTTLE_BLOCKED
    )

    return LivePilotRiskThrottleReport(
        schema_version=LIVE_PILOT_RISK_THROTTLE_SCHEMA_VERSION,
        source=LIVE_PILOT_RISK_THROTTLE_SOURCE,
        status=status,
        candidate_count=len(decisions),
        review_allowed_count=review_allowed_count,
        review_blocked_count=review_blocked_count,
        reasons=reasons,
        candidates=tuple(decisions),
        metadata={
            "evidence_only": True,
            "review_only": True,
            "live_pilot_review_only": True,
            "requires_paper_gate_passed": True,
            "max_candidates": max_candidates,
            "max_per_strategy": max_per_strategy,
            "allowed_symbols": tuple(sorted(allowed_symbol_set)),
            "blocked_symbols": tuple(sorted(blocked_symbol_set)),
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


def _candidate_payloads(paper_payload: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(paper_payload, Mapping):
        return ()
    raw_candidates = paper_payload.get("candidates")
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


def _candidate_paper_allowed(candidate: Mapping[str, Any]) -> bool:
    if isinstance(candidate.get("paper_allowed"), bool):
        return bool(candidate.get("paper_allowed"))
    return str(candidate.get("status") or "") == PAPER_CANDIDATE_ELIGIBLE


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("candidate_id") or candidate.get("trade_key") or candidate.get("id")
    return str(value or "UNKNOWN_CANDIDATE").strip() or "UNKNOWN_CANDIDATE"


def _strategy_id(candidate: Mapping[str, Any]) -> str:
    value = _metadata_value(candidate, "strategy_id") or "UNKNOWN_STRATEGY"
    return str(value).strip() or "UNKNOWN_STRATEGY"


def _symbol(candidate: Mapping[str, Any]) -> str:
    value = _metadata_value(candidate, "symbol") or ""
    return str(value).strip().upper()


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str, str]:
    return (_candidate_id(candidate), _strategy_id(candidate), _symbol(candidate))


def _metadata_value(candidate: Mapping[str, Any], key: str) -> Any:
    if key in candidate:
        return candidate.get(key)
    metadata = candidate.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _symbol_set(values: Iterable[str] | None) -> frozenset[str]:
    if values is None:
        return frozenset()
    return frozenset(str(value).strip().upper() for value in values if str(value or "").strip())


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
    "LIVE_PILOT_CANDIDATE_BLOCKED",
    "LIVE_PILOT_CANDIDATE_REVIEW_ELIGIBLE",
    "LIVE_PILOT_RISK_THROTTLE_SCHEMA_VERSION",
    "LIVE_PILOT_RISK_THROTTLE_SOURCE",
    "LIVE_PILOT_THROTTLE_BLOCKED",
    "LIVE_PILOT_THROTTLE_PASSED",
    "REASON_CANDIDATE_NOT_PAPER_ALLOWED",
    "REASON_INVALID_THROTTLE_LIMIT",
    "REASON_MAX_CANDIDATES_EXCEEDED",
    "REASON_MAX_PER_STRATEGY_EXCEEDED",
    "REASON_NO_PAPER_ALLOWED_CANDIDATES",
    "REASON_NOT_PAPER_MODE",
    "REASON_PAPER_GATE_BLOCKED",
    "REASON_PAPER_GATE_MISSING",
    "REASON_SYMBOL_BLOCKED",
    "REASON_SYMBOL_NOT_ALLOWED",
    "LivePilotCandidateThrottleDecision",
    "LivePilotRiskThrottleReport",
    "build_live_pilot_risk_throttle_report",
]
