"""Agent approval decision layer.

This module converts an Agent Scope Guard decision into a patch-only approval
or rejection. It is deliberately not an execution permission layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.agent_scope_guard import AGENT_SCOPE_BLOCKED, AgentScopeDecision
from core.agent_work_contract import AGENT_WORK_SCHEMA_VERSION


AGENT_APPROVAL_APPROVED_FOR_PATCH = "AGENT_APPROVAL_APPROVED_FOR_PATCH"
AGENT_APPROVAL_REJECTED = "AGENT_APPROVAL_REJECTED"


@dataclass(frozen=True)
class AgentApprovalDecision:
    schema_version: int
    state: str
    approved: bool
    work_id: str | None
    source_agent: str | None
    action: str | None
    risk_level: str
    approved_by: str | None
    human_approved: bool
    read_only: bool
    is_order_action: bool
    broker_api_called: bool
    live_mode_touched: bool
    allowed_for_patch: bool
    allowed_for_runtime_wiring: bool
    allowed_for_live_execution: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _text(value: object) -> str:
    return str(value or "").strip()


def approve_agent_scope(
    scope_decision: AgentScopeDecision,
    *,
    human_approved: bool = False,
    approved_by: str | None = None,
) -> AgentApprovalDecision:
    """Approve a scope decision for patch work only.

    Rules:
    - blocked or unaccepted scope cannot be approved
    - explicit human approval is required when the scope guard requires it
    - human approval requires a non-empty approver id
    - approval never grants runtime wiring or live execution
    """

    blockers: list[str] = []
    warnings: list[str] = list(scope_decision.warnings)
    reasons: list[str] = []
    approver = _text(approved_by) or None

    if not scope_decision.accepted:
        blockers.append("SCOPE_DECISION_NOT_ACCEPTED")
    if scope_decision.state == AGENT_SCOPE_BLOCKED:
        blockers.append("BLOCKED_SCOPE_CANNOT_BE_APPROVED")
    if scope_decision.requires_human_approval and not human_approved:
        blockers.append("HUMAN_APPROVAL_REQUIRED")
    if human_approved and not approver:
        blockers.append("APPROVER_ID_REQUIRED")
    if scope_decision.is_order_action:
        blockers.append("ORDER_ACTION_FORBIDDEN")
    if scope_decision.broker_api_called:
        blockers.append("BROKER_API_CALL_FORBIDDEN")
    if scope_decision.live_mode_touched:
        blockers.append("LIVE_MODE_TOUCH_FORBIDDEN")
    if scope_decision.allowed_for_runtime_wiring:
        blockers.append("RUNTIME_WIRING_PERMISSION_FORBIDDEN")
    if scope_decision.allowed_for_live_execution:
        blockers.append("LIVE_EXECUTION_PERMISSION_FORBIDDEN")

    approved = not blockers
    if approved:
        state = AGENT_APPROVAL_APPROVED_FOR_PATCH
        reasons.append("agent_work_approved_for_patch_only")
    else:
        state = AGENT_APPROVAL_REJECTED
        reasons.append("agent_work_approval_rejected")

    return AgentApprovalDecision(
        schema_version=AGENT_WORK_SCHEMA_VERSION,
        state=state,
        approved=approved,
        work_id=scope_decision.work_id if approved else None,
        source_agent=scope_decision.source_agent,
        action=scope_decision.action,
        risk_level=scope_decision.risk_level,
        approved_by=approver if approved else None,
        human_approved=bool(human_approved),
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        live_mode_touched=False,
        allowed_for_patch=approved,
        allowed_for_runtime_wiring=False,
        allowed_for_live_execution=False,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        reasons=_dedupe(reasons),
        metadata={
            "contract": "agent_approval_v1",
            "scope": "patch_approval_only_no_runtime_no_broker_no_live",
            "scope_state": scope_decision.state,
        },
    )


__all__ = [
    "AGENT_APPROVAL_APPROVED_FOR_PATCH",
    "AGENT_APPROVAL_REJECTED",
    "AgentApprovalDecision",
    "approve_agent_scope",
]
