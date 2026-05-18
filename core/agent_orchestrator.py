"""Agent review orchestrator.

This module enforces the local multi-agent review workflow that should happen
before agent-assisted patch work reaches the human owner.

It does not call external agents. It records and evaluates their review outputs.
It does not create network routes, merge code, edit files, call brokers, or touch
trading runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from core.agent_approval import approve_agent_scope
from core.agent_scope_guard import assess_agent_scope
from core.agent_work_contract import (
    AGENT_WORK_SCHEMA_VERSION,
    AgentWorkRequest,
    normalize_agent_work_request,
    validate_agent_work_contract,
)


AGENT_ORCHESTRATION_SCHEMA_VERSION = 1


class AgentReviewStage(str, Enum):
    GRILL_ME = "GRILL_ME"
    HERMES = "HERMES"
    GSD = "GSD"
    HUMAN = "HUMAN"


class AgentReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    READY = "READY"
    REWRITE = "REWRITE"
    REJECT = "REJECT"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class AgentOrchestrationState(str, Enum):
    APPROVED_FOR_PATCH = "AGENT_ORCHESTRATION_APPROVED_FOR_PATCH"
    WAITING_HUMAN_APPROVAL = "AGENT_ORCHESTRATION_WAITING_HUMAN_APPROVAL"
    REVIEW_REQUIRED = "AGENT_ORCHESTRATION_REVIEW_REQUIRED"
    REWRITE_REQUIRED = "AGENT_ORCHESTRATION_REWRITE_REQUIRED"
    REJECTED = "AGENT_ORCHESTRATION_REJECTED"
    BLOCKED = "AGENT_ORCHESTRATION_BLOCKED"


REQUIRED_REVIEW_STAGES = (
    AgentReviewStage.GRILL_ME.value,
    AgentReviewStage.HERMES.value,
    AgentReviewStage.GSD.value,
)

APPROVAL_DECISIONS = {
    AgentReviewDecision.APPROVE.value,
    AgentReviewDecision.READY.value,
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _stage_text(value: object) -> str:
    return _text(value).upper().replace("-", "_").replace(" ", "_")


def _decision_text(value: object) -> str:
    return _text(value).upper().replace("-", "_").replace(" ", "_")


def _tuple_text(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = _text(value)
        return (text,) if text else ()
    if isinstance(value, Iterable):
        return tuple(_text(item) for item in value if _text(item))
    return ()


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class AgentReviewRecord:
    schema_version: int
    stage: str
    reviewer: str
    decision: str
    summary: str
    risks: tuple[str, ...]
    required_changes: tuple[str, ...]
    approved_paths: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risks"] = list(self.risks)
        payload["required_changes"] = list(self.required_changes)
        payload["approved_paths"] = list(self.approved_paths)
        payload["blocked_paths"] = list(self.blocked_paths)
        payload["evidence"] = dict(self.evidence)
        return payload


@dataclass(frozen=True)
class AgentOrchestrationDecision:
    schema_version: int
    state: str
    accepted: bool
    work_id: str | None
    read_only: bool
    is_order_action: bool
    broker_api_called: bool
    live_mode_touched: bool
    allowed_for_patch: bool
    allowed_for_runtime_wiring: bool
    allowed_for_live_execution: bool
    required_stages: tuple[str, ...]
    completed_stages: tuple[str, ...]
    missing_stages: tuple[str, ...]
    contract_decision: dict[str, Any]
    scope_decision: dict[str, Any]
    approval_decision: dict[str, Any]
    reviews: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_stages"] = list(self.required_stages)
        payload["completed_stages"] = list(self.completed_stages)
        payload["missing_stages"] = list(self.missing_stages)
        payload["reviews"] = list(self.reviews)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def normalize_agent_review_record(payload: Mapping[str, Any]) -> AgentReviewRecord:
    return AgentReviewRecord(
        schema_version=int(payload.get("schema_version") or AGENT_ORCHESTRATION_SCHEMA_VERSION),
        stage=_stage_text(payload.get("stage")),
        reviewer=_text(payload.get("reviewer")),
        decision=_decision_text(payload.get("decision")),
        summary=_text(payload.get("summary")),
        risks=_tuple_text(payload.get("risks")),
        required_changes=_tuple_text(payload.get("required_changes")),
        approved_paths=_tuple_text(payload.get("approved_paths")),
        blocked_paths=_tuple_text(payload.get("blocked_paths")),
        evidence=_dict(payload.get("evidence")),
    )


def _review_validation_blockers(review: AgentReviewRecord) -> list[str]:
    blockers: list[str] = []
    if review.schema_version != AGENT_ORCHESTRATION_SCHEMA_VERSION:
        blockers.append("REVIEW_SCHEMA_VERSION_UNSUPPORTED")
    if review.stage not in {stage.value for stage in AgentReviewStage}:
        blockers.append("REVIEW_STAGE_UNKNOWN")
    if not review.reviewer:
        blockers.append("REVIEWER_MISSING")
    if review.decision not in {decision.value for decision in AgentReviewDecision}:
        blockers.append("REVIEW_DECISION_UNKNOWN")
    if not review.summary:
        blockers.append("REVIEW_SUMMARY_MISSING")
    return blockers


def _latest_reviews_by_stage(reviews: Iterable[AgentReviewRecord]) -> dict[str, AgentReviewRecord]:
    by_stage: dict[str, AgentReviewRecord] = {}
    for review in reviews:
        by_stage[review.stage] = review
    return by_stage


def _paths_conflict(request: AgentWorkRequest, reviews: Iterable[AgentReviewRecord]) -> tuple[str, ...]:
    conflicts: list[str] = []
    requested = set(request.requested_paths)
    for review in reviews:
        blocked = set(review.blocked_paths)
        if requested.intersection(blocked):
            conflicts.append(f"REVIEW_BLOCKED_REQUESTED_PATH:{review.stage}")
    return _dedupe(conflicts)


def evaluate_agent_review_orchestration(
    work_payload: Mapping[str, Any],
    review_payloads: Iterable[Mapping[str, Any]],
    *,
    human_approved: bool = False,
    approved_by: str | None = None,
) -> AgentOrchestrationDecision:
    """Evaluate whether agent-assisted work passed the required review chain."""

    request = normalize_agent_work_request(work_payload)
    contract_decision = validate_agent_work_contract(request)
    scope_decision = assess_agent_scope(request, contract_decision=contract_decision)
    approval_decision = approve_agent_scope(
        scope_decision,
        human_approved=human_approved,
        approved_by=approved_by,
    )

    reviews = tuple(normalize_agent_review_record(payload) for payload in review_payloads)
    by_stage = _latest_reviews_by_stage(reviews)

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    blockers.extend(contract_decision.blockers)
    blockers.extend(scope_decision.blockers)
    warnings.extend(contract_decision.warnings)
    warnings.extend(scope_decision.warnings)

    for review in reviews:
        blockers.extend(_review_validation_blockers(review))

    completed_stages = tuple(stage for stage in REQUIRED_REVIEW_STAGES if stage in by_stage)
    missing_stages = tuple(stage for stage in REQUIRED_REVIEW_STAGES if stage not in by_stage)
    if missing_stages:
        blockers.append("REQUIRED_AGENT_REVIEW_MISSING")
        reasons.append("required_agent_reviews_missing")

    blockers.extend(_paths_conflict(request, reviews))

    rejected_stages = tuple(stage for stage, review in by_stage.items() if review.decision == AgentReviewDecision.REJECT.value)
    rewrite_stages = tuple(stage for stage, review in by_stage.items() if review.decision == AgentReviewDecision.REWRITE.value)
    human_needed_stages = tuple(stage for stage, review in by_stage.items() if review.decision == AgentReviewDecision.NEEDS_HUMAN.value)

    if rejected_stages:
        blockers.append("AGENT_REVIEW_REJECTED")
        reasons.append("agent_review_rejected")
    if rewrite_stages:
        blockers.append("AGENT_REVIEW_REWRITE_REQUIRED")
        reasons.append("agent_review_rewrite_required")
    if human_needed_stages:
        warnings.append("AGENT_REVIEW_NEEDS_HUMAN")
        reasons.append("agent_review_needs_human")

    non_approving_required = tuple(
        stage
        for stage in REQUIRED_REVIEW_STAGES
        if stage in by_stage and by_stage[stage].decision not in APPROVAL_DECISIONS
    )
    if non_approving_required and not rejected_stages and not rewrite_stages:
        blockers.append("REQUIRED_AGENT_REVIEW_NOT_APPROVED")
        reasons.append("required_agent_review_not_approved")

    if blockers:
        if "AGENT_REVIEW_REJECTED" in blockers:
            state = AgentOrchestrationState.REJECTED.value
        elif "AGENT_REVIEW_REWRITE_REQUIRED" in blockers:
            state = AgentOrchestrationState.REWRITE_REQUIRED.value
        elif "REQUIRED_AGENT_REVIEW_MISSING" in blockers:
            state = AgentOrchestrationState.REVIEW_REQUIRED.value
        else:
            state = AgentOrchestrationState.BLOCKED.value
        accepted = False
        allowed_for_patch = False
        work_id = None
    elif not approval_decision.approved:
        state = AgentOrchestrationState.WAITING_HUMAN_APPROVAL.value
        accepted = False
        allowed_for_patch = False
        work_id = None
        blockers.extend(approval_decision.blockers)
        warnings.extend(approval_decision.warnings)
        reasons.append("agent_orchestration_waiting_human_approval")
    else:
        state = AgentOrchestrationState.APPROVED_FOR_PATCH.value
        accepted = True
        allowed_for_patch = True
        work_id = approval_decision.work_id
        reasons.append("agent_reviews_approved_for_patch_only")

    return AgentOrchestrationDecision(
        schema_version=AGENT_ORCHESTRATION_SCHEMA_VERSION,
        state=state,
        accepted=accepted,
        work_id=work_id,
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        live_mode_touched=False,
        allowed_for_patch=allowed_for_patch,
        allowed_for_runtime_wiring=False,
        allowed_for_live_execution=False,
        required_stages=REQUIRED_REVIEW_STAGES,
        completed_stages=completed_stages,
        missing_stages=missing_stages,
        contract_decision=contract_decision.to_dict(),
        scope_decision=scope_decision.to_dict(),
        approval_decision=approval_decision.to_dict(),
        reviews=tuple(review.to_dict() for review in reviews),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        reasons=_dedupe(reasons),
        metadata={
            "contract": "agent_orchestrator_v1",
            "scope": "local_review_orchestration_only_no_external_agent_calls",
            "required_review_stages": list(REQUIRED_REVIEW_STAGES),
        },
    )


__all__ = [
    "AGENT_ORCHESTRATION_SCHEMA_VERSION",
    "APPROVAL_DECISIONS",
    "REQUIRED_REVIEW_STAGES",
    "AgentOrchestrationDecision",
    "AgentOrchestrationState",
    "AgentReviewDecision",
    "AgentReviewRecord",
    "AgentReviewStage",
    "evaluate_agent_review_orchestration",
    "normalize_agent_review_record",
]
