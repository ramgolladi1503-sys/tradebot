"""Read-only end-to-end edge acceptance suite for EDGE-94.

This module composes existing proof/gate evidence into deterministic candidate-level
acceptance reports. It does not generate candidates, rank candidates, mutate runtime
state, call brokers, place orders, write artifacts, or wire dashboard behavior.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.final_executable_quality_gate import FINAL_EXECUTABLE_QUALITY_PASSED
from core.strategy_replay_proof_pack import STRATEGY_REPLAY_PROOF_PASSED

END_TO_END_EDGE_ACCEPTANCE_SCHEMA_VERSION = 1
END_TO_END_EDGE_ACCEPTANCE_SOURCE = "end_to_end_edge_acceptance_suite_v1"

EDGE_ACCEPTANCE_SUITE_PASSED = "EDGE_ACCEPTANCE_SUITE_PASSED"
EDGE_ACCEPTANCE_SUITE_BLOCKED = "EDGE_ACCEPTANCE_SUITE_BLOCKED"

EDGE_CANDIDATE_ACCEPTED = "ACCEPTED"
EDGE_CANDIDATE_REJECTED = "REJECTED"

REASON_OK = "OK"
REASON_NO_CANDIDATES = "NO_CANDIDATES"
REASON_MISSING_CANDIDATE_ID = "MISSING_CANDIDATE_ID"
REASON_MISSING_STAGE_EVIDENCE = "MISSING_STAGE_EVIDENCE"
REASON_STAGE_BLOCKED = "STAGE_BLOCKED"

_STAGE_CANDIDATE_INTENT = "candidate_intent"
_STAGE_CANDIDATE_POOL = "candidate_pool"
_STAGE_STRATEGY_GENERATOR = "strategy_generator"
_STAGE_OPTION_CHAIN_CONFIRMATION = "option_chain_confirmation"
_STAGE_EXIT_MODEL = "exit_model"
_STAGE_CONFLICT_CONSENSUS = "conflict_consensus"
_STAGE_NO_TRADE_ORACLE = "no_trade_oracle"
_STAGE_FINAL_QUALITY_GATE = "final_quality_gate"
_STAGE_REPLAY_PROOF_PACK = "replay_proof_pack"

REQUIRED_EDGE_ACCEPTANCE_STAGES: tuple[str, ...] = (
    _STAGE_CANDIDATE_INTENT,
    _STAGE_CANDIDATE_POOL,
    _STAGE_STRATEGY_GENERATOR,
    _STAGE_OPTION_CHAIN_CONFIRMATION,
    _STAGE_EXIT_MODEL,
    _STAGE_CONFLICT_CONSENSUS,
    _STAGE_NO_TRADE_ORACLE,
    _STAGE_FINAL_QUALITY_GATE,
    _STAGE_REPLAY_PROOF_PACK,
)

_PASS_VALUES = {
    "PASS",
    "PASSED",
    "OK",
    "VALID",
    "CONFIRMED",
    "ACCEPTED",
    "APPROVED",
    "EXECUTABLE",
    "ELIGIBLE",
    "ALLOW",
    "ALLOWED",
    "READY",
    "HEALTHY",
    "SCORE_ELIGIBLE",
    "FINAL_EXECUTABLE_QUALITY_PASSED",
    "STRATEGY_REPLAY_PROOF_PASSED",
}
_BLOCK_VALUES = {
    "BLOCK",
    "BLOCKED",
    "FAIL",
    "FAILED",
    "INVALID",
    "REJECTED",
    "DENIED",
    "UNSAFE",
    "NO_TRADE_REQUIRED",
    "FINAL_EXECUTABLE_QUALITY_BLOCKED",
    "STRATEGY_REPLAY_PROOF_BLOCKED",
}

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class EdgeAcceptanceStageEvidence:
    """Normalized read-only stage evidence used by the EDGE-94 suite."""

    stage: str
    status: str
    passed: bool
    reasons: tuple[str, ...]
    evidence: Mapping[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False

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
            "stage": self.stage,
            "status": self.status,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class EdgeCandidateAcceptance:
    """Per-candidate end-to-end acceptance result."""

    candidate_id: str
    status: str
    accepted: bool
    reasons: tuple[str, ...]
    stage_evidence: tuple[EdgeAcceptanceStageEvidence, ...]
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
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "stage_evidence": [stage.to_payload() for stage in self.stage_evidence],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class EndToEndEdgeAcceptanceReport:
    """Top-level read-only EDGE-94 acceptance suite report."""

    schema_version: int
    source: str
    status: str
    candidate_count: int
    accepted_candidate_count: int
    rejected_candidate_count: int
    reasons: tuple[str, ...]
    candidates: tuple[EdgeCandidateAcceptance, ...]
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
            "accepted_candidate_count": self.accepted_candidate_count,
            "rejected_candidate_count": self.rejected_candidate_count,
            "reasons": list(self.reasons),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


def build_end_to_end_edge_acceptance_report(
    candidates: Iterable[Any] | Any | None,
    *,
    candidate_intent: Iterable[Any] | Any | None = None,
    candidate_pool: Iterable[Any] | Any | None = None,
    strategy_generator: Iterable[Any] | Any | None = None,
    option_chain_confirmation: Iterable[Any] | Any | None = None,
    exit_model: Iterable[Any] | Any | None = None,
    conflict_consensus: Iterable[Any] | Any | None = None,
    no_trade_oracle: Iterable[Any] | Any | None = None,
    final_quality_gate: Iterable[Any] | Any | None = None,
    replay_proof_pack: Iterable[Any] | Any | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EndToEndEdgeAcceptanceReport:
    """Build deterministic candidate-level end-to-end edge acceptance evidence.

    Inputs are already-computed evidence payloads/reports. This suite intentionally
    performs no candidate generation, ranking, execution, runtime writes, broker
    calls, or dashboard wiring.
    """

    candidate_payloads = tuple(_payload(item) for item in _as_sequence(candidates))
    normalized_candidates = tuple(payload for payload in candidate_payloads if payload is not None)

    evidence_by_stage = {
        _STAGE_CANDIDATE_INTENT: _index_evidence(candidate_intent),
        _STAGE_CANDIDATE_POOL: _index_evidence(candidate_pool),
        _STAGE_STRATEGY_GENERATOR: _index_evidence(strategy_generator),
        _STAGE_OPTION_CHAIN_CONFIRMATION: _index_evidence(option_chain_confirmation),
        _STAGE_EXIT_MODEL: _index_evidence(exit_model),
        _STAGE_CONFLICT_CONSENSUS: _index_evidence(conflict_consensus),
        _STAGE_NO_TRADE_ORACLE: _index_evidence(no_trade_oracle),
        _STAGE_FINAL_QUALITY_GATE: _index_evidence(final_quality_gate),
        _STAGE_REPLAY_PROOF_PACK: _index_evidence(replay_proof_pack),
    }

    acceptances = tuple(
        _build_candidate_acceptance(candidate, evidence_by_stage)
        for candidate in sorted(normalized_candidates, key=_candidate_sort_key)
    )
    accepted_count = sum(1 for item in acceptances if item.accepted)
    rejected_count = sum(1 for item in acceptances if not item.accepted)
    reasons = _report_reasons(acceptances, no_candidates=not acceptances)
    status = EDGE_ACCEPTANCE_SUITE_PASSED if acceptances and rejected_count == 0 and not reasons else EDGE_ACCEPTANCE_SUITE_BLOCKED

    return EndToEndEdgeAcceptanceReport(
        schema_version=END_TO_END_EDGE_ACCEPTANCE_SCHEMA_VERSION,
        source=END_TO_END_EDGE_ACCEPTANCE_SOURCE,
        status=status,
        candidate_count=len(acceptances),
        accepted_candidate_count=accepted_count,
        rejected_candidate_count=rejected_count,
        reasons=reasons,
        candidates=acceptances,
        metadata={
            "evidence_only": True,
            "fail_closed_on_missing_stage_evidence": True,
            "required_stages": REQUIRED_EDGE_ACCEPTANCE_STAGES,
            "does_not_generate_candidates": True,
            "does_not_rank_candidates": True,
            "does_not_change_strategies": True,
            "does_not_change_execution": True,
            "does_not_call_brokers": True,
            "does_not_wire_runtime": True,
            "does_not_wire_dashboard": True,
            **dict(metadata or {}),
        },
    )


def _build_candidate_acceptance(
    candidate: Mapping[str, Any],
    evidence_by_stage: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> EdgeCandidateAcceptance:
    candidate_id = _candidate_id(candidate)
    candidate_reasons: list[str] = []
    if not candidate_id:
        candidate_reasons.append(REASON_MISSING_CANDIDATE_ID)
    stage_evidence: list[EdgeAcceptanceStageEvidence] = []
    for stage in REQUIRED_EDGE_ACCEPTANCE_STAGES:
        evidence = _matching_stage_evidence(candidate, evidence_by_stage[stage])
        normalized = _stage_evidence(stage=stage, evidence=evidence)
        stage_evidence.append(normalized)
        if not normalized.passed:
            candidate_reasons.extend(f"{stage}:{reason}" for reason in normalized.reasons)
    reasons = _dedupe(candidate_reasons)
    accepted = bool(candidate_id) and not reasons and all(stage.passed for stage in stage_evidence)
    return EdgeCandidateAcceptance(
        candidate_id=candidate_id or "UNKNOWN_CANDIDATE",
        status=EDGE_CANDIDATE_ACCEPTED if accepted else EDGE_CANDIDATE_REJECTED,
        accepted=accepted,
        reasons=reasons,
        stage_evidence=tuple(stage_evidence),
        metadata={
            "strategy_id": candidate.get("strategy_id") or candidate.get("strategy"),
            "symbol": candidate.get("symbol"),
            "direction": candidate.get("direction"),
            "movement_type": candidate.get("movement_type"),
            "evidence_only": True,
        },
    )


def _stage_evidence(stage: str, evidence: Mapping[str, Any] | None) -> EdgeAcceptanceStageEvidence:
    if evidence is None:
        return EdgeAcceptanceStageEvidence(
            stage=stage,
            status="MISSING",
            passed=False,
            reasons=(REASON_MISSING_STAGE_EVIDENCE,),
            evidence={},
        )

    passed = _stage_passed(stage, evidence)
    reasons = () if passed else _stage_reasons(stage, evidence)
    return EdgeAcceptanceStageEvidence(
        stage=stage,
        status=str(evidence.get("status") or ("PASSED" if passed else "BLOCKED")),
        passed=passed,
        reasons=reasons,
        evidence=_evidence_summary(evidence),
    )


def _stage_passed(stage: str, evidence: Mapping[str, Any]) -> bool:
    if _has_truthy(evidence, "is_order_action") or _has_truthy(evidence, "broker_api_called"):
        return False
    if _has_truthy(evidence, "live_order_action") or _has_truthy(evidence, "broker_order_action"):
        return False

    if stage == _STAGE_NO_TRADE_ORACLE:
        if _has_truthy(evidence, "no_trade_required"):
            return False
        if _has_truthy(evidence, "should_block") or _has_truthy(evidence, "blocked"):
            return False
        return _status_allows(evidence)

    if stage == _STAGE_FINAL_QUALITY_GATE:
        if evidence.get("status") == FINAL_EXECUTABLE_QUALITY_PASSED:
            return True
        if _has_truthy(evidence, "executable_quality_passed"):
            return True
        return _status_allows(evidence)

    if stage == _STAGE_REPLAY_PROOF_PACK:
        if evidence.get("status") == STRATEGY_REPLAY_PROOF_PASSED:
            return True
        return _status_allows(evidence)

    if _has_truthy(evidence, "passed") or _has_truthy(evidence, "valid") or _has_truthy(evidence, "confirmed"):
        return not _has_block_signal(evidence)
    if _has_truthy(evidence, "execution_allowed") or _has_truthy(evidence, "score_eligible"):
        return not _has_block_signal(evidence)
    return _status_allows(evidence)


def _stage_reasons(stage: str, evidence: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for key in ("reason", "reason_code", "primary_reason", "block_reason"):
        value = evidence.get(key)
        if _is_reason(value):
            reasons.append(str(value))
    for key in ("reasons", "blockers", "safety_flags", "errors", "warnings"):
        reasons.extend(_string_values(evidence.get(key)))
    if _has_truthy(evidence, "is_order_action"):
        reasons.append("ORDER_ACTION_EVIDENCE_NOT_ALLOWED")
    if _has_truthy(evidence, "broker_api_called"):
        reasons.append("BROKER_API_CALL_EVIDENCE_NOT_ALLOWED")
    if _has_truthy(evidence, "live_order_action"):
        reasons.append("LIVE_ORDER_ACTION_EVIDENCE_NOT_ALLOWED")
    if _has_truthy(evidence, "broker_order_action"):
        reasons.append("BROKER_ORDER_ACTION_EVIDENCE_NOT_ALLOWED")
    if not reasons:
        status = str(evidence.get("status") or "").strip()
        reasons.append(f"{REASON_STAGE_BLOCKED}:{status or stage}")
    return _dedupe(reasons)


def _evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "candidate_id",
        "trade_key",
        "strategy_id",
        "strategy",
        "symbol",
        "direction",
        "movement_type",
        "status",
        "passed",
        "valid",
        "confirmed",
        "execution_allowed",
        "executable_quality_passed",
        "no_trade_required",
        "primary_reason",
        "reason_code",
        "reason",
    ):
        if key in evidence:
            summary[key] = evidence.get(key)
    return summary


def _index_evidence(value: Iterable[Any] | Any | None) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    fallback_items: list[Mapping[str, Any]] = []
    for raw_item in _as_sequence(value):
        payload = _payload(raw_item)
        if payload is None:
            continue
        candidates = payload.get("candidates")
        if isinstance(candidates, Iterable) and not isinstance(candidates, (str, bytes, Mapping)):
            for nested in candidates:
                nested_payload = _payload(nested)
                if nested_payload is not None:
                    _add_indexed(indexed, fallback_items, nested_payload)
            continue
        strategy_summaries = payload.get("strategy_summaries")
        if isinstance(strategy_summaries, Iterable) and not isinstance(strategy_summaries, (str, bytes, Mapping)):
            for nested in strategy_summaries:
                nested_payload = _payload(nested)
                if nested_payload is not None:
                    merged = {**payload, **nested_payload}
                    _add_indexed(indexed, fallback_items, merged)
            continue
        _add_indexed(indexed, fallback_items, payload)
    if len(fallback_items) == 1:
        indexed["*"] = fallback_items[0]
    return indexed


def _add_indexed(
    indexed: dict[str, Mapping[str, Any]],
    fallback_items: list[Mapping[str, Any]],
    payload: Mapping[str, Any],
) -> None:
    candidate_id = _candidate_id(payload)
    if candidate_id:
        indexed[candidate_id] = payload
    else:
        fallback_items.append(payload)


def _matching_stage_evidence(
    candidate: Mapping[str, Any],
    indexed: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    candidate_id = _candidate_id(candidate)
    if candidate_id and candidate_id in indexed:
        return indexed[candidate_id]
    for payload in indexed.values():
        if payload is indexed.get("*"):
            continue
        if _identity_matches(candidate, payload):
            return payload
    return indexed.get("*")


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


def _as_sequence(value: Iterable[Any] | Any | None) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    if _payload(value) is not None:
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _candidate_id(payload: Mapping[str, Any]) -> str:
    value = payload.get("candidate_id") or payload.get("trade_key") or payload.get("id")
    return str(value or "").strip()


def _identity_matches(candidate: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    strategy = str(candidate.get("strategy_id") or candidate.get("strategy") or "").strip()
    symbol = str(candidate.get("symbol") or "").strip()
    direction = str(candidate.get("direction") or "").strip()
    movement = str(candidate.get("movement_type") or "").strip()
    if not (strategy and symbol):
        return False
    payload_strategy = str(payload.get("strategy_id") or payload.get("strategy") or "").strip()
    payload_symbol = str(payload.get("symbol") or "").strip()
    payload_direction = str(payload.get("direction") or "").strip()
    payload_movement = str(payload.get("movement_type") or "").strip()
    return bool(
        strategy == payload_strategy
        and symbol == payload_symbol
        and (not direction or not payload_direction or direction == payload_direction)
        and (not movement or not payload_movement or movement == payload_movement)
    )


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _candidate_id(candidate),
        str(candidate.get("strategy_id") or candidate.get("strategy") or ""),
        str(candidate.get("symbol") or ""),
        str(candidate.get("direction") or ""),
    )


def _report_reasons(candidates: tuple[EdgeCandidateAcceptance, ...], *, no_candidates: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if no_candidates:
        reasons.append(REASON_NO_CANDIDATES)
    for candidate in candidates:
        reasons.extend(candidate.reasons)
    return _dedupe(reasons)


def _status_allows(evidence: Mapping[str, Any]) -> bool:
    if _has_block_signal(evidence):
        return False
    status = str(evidence.get("status") or evidence.get("decision") or "").strip().upper()
    if not status:
        return False
    if status in _BLOCK_VALUES or status.endswith("_BLOCKED") or status.endswith("_FAILED") or status.endswith("_REJECTED"):
        return False
    return status in _PASS_VALUES or status.endswith("_PASSED") or status.endswith("_ACCEPTED")


def _has_block_signal(evidence: Mapping[str, Any]) -> bool:
    if _has_truthy(evidence, "blocked") or _has_truthy(evidence, "should_block"):
        return True
    if _has_truthy(evidence, "reject") or _has_truthy(evidence, "rejected"):
        return True
    if _has_truthy(evidence, "unsafe") or _has_truthy(evidence, "no_trade_required"):
        return True
    status = str(evidence.get("status") or evidence.get("decision") or "").strip().upper()
    return status in _BLOCK_VALUES or status.endswith("_BLOCKED") or status.endswith("_FAILED") or status.endswith("_REJECTED")


def _has_truthy(evidence: Mapping[str, Any], key: str) -> bool:
    value = evidence.get(key)
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ok", "blocked", "required", "allowed"}


def _string_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if _is_reason(value) else ()
    if isinstance(value, Mapping):
        return ()
    try:
        values = tuple(value)
    except TypeError:
        return (str(value),) if _is_reason(value) else ()
    return tuple(str(item).strip() for item in values if _is_reason(item))


def _is_reason(reason: Any) -> bool:
    text = str(reason or "").strip()
    return bool(text) and text.upper() not in {REASON_OK, "NONE", "NULL"}


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if _is_reason(value)}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "EDGE_ACCEPTANCE_SUITE_BLOCKED",
    "EDGE_ACCEPTANCE_SUITE_PASSED",
    "EDGE_CANDIDATE_ACCEPTED",
    "EDGE_CANDIDATE_REJECTED",
    "END_TO_END_EDGE_ACCEPTANCE_SCHEMA_VERSION",
    "END_TO_END_EDGE_ACCEPTANCE_SOURCE",
    "REQUIRED_EDGE_ACCEPTANCE_STAGES",
    "REASON_MISSING_STAGE_EVIDENCE",
    "REASON_NO_CANDIDATES",
    "EdgeAcceptanceStageEvidence",
    "EdgeCandidateAcceptance",
    "EndToEndEdgeAcceptanceReport",
    "build_end_to_end_edge_acceptance_report",
]
