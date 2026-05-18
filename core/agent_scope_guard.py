"""Agent scope guard.

This module authorizes the *engineering scope* of an agent work request after
`core.agent_work_contract` has validated the base request shape.

It is still not an execution layer. It does not approve runtime wiring, write
evidence, create webhooks, place orders, call brokers, or change trading state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import posixpath
from typing import Any

from core.agent_work_contract import (
    AGENT_WORK_SCHEMA_VERSION,
    AgentAction,
    AgentSource,
    AgentWorkContractDecision,
    AgentWorkRequest,
    validate_agent_work_contract,
)


AGENT_SCOPE_APPROVED_FOR_PATCH = "AGENT_SCOPE_APPROVED_FOR_PATCH"
AGENT_SCOPE_WAITING_HUMAN_APPROVAL = "AGENT_SCOPE_WAITING_HUMAN_APPROVAL"
AGENT_SCOPE_BLOCKED = "AGENT_SCOPE_BLOCKED"


class AgentScopeRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


SOURCE_ALLOWED_ACTIONS = {
    AgentSource.GRILL_ME.value: frozenset(
        {
            AgentAction.CRITIQUE_SCOPE.value,
            AgentAction.REVIEW_PR.value,
            AgentAction.AUDIT_RISK.value,
            AgentAction.FIND_FAKE_PROGRESS.value,
        }
    ),
    AgentSource.HERMES.value: frozenset(
        {
            AgentAction.DESIGN_ARCHITECTURE.value,
            AgentAction.DEFINE_CONTRACT.value,
            AgentAction.MAP_WORKFLOW.value,
            AgentAction.CREATE_ACCEPTANCE_GATES.value,
            AgentAction.UPDATE_DOCS.value,
        }
    ),
    AgentSource.GSD.value: frozenset(
        {
            AgentAction.PLAN_PR.value,
            AgentAction.GENERATE_TESTS.value,
            AgentAction.GENERATE_PATCH.value,
            AgentAction.FIX_TEST_FAILURE.value,
            AgentAction.UPDATE_DOCS.value,
        }
    ),
    AgentSource.CODEX.value: frozenset(
        {
            AgentAction.PLAN_PR.value,
            AgentAction.GENERATE_TESTS.value,
            AgentAction.GENERATE_PATCH.value,
            AgentAction.FIX_TEST_FAILURE.value,
            AgentAction.UPDATE_DOCS.value,
            AgentAction.REVIEW_PR.value,
        }
    ),
    AgentSource.CHATGPT.value: frozenset(
        {
            AgentAction.CRITIQUE_SCOPE.value,
            AgentAction.REVIEW_PR.value,
            AgentAction.AUDIT_RISK.value,
            AgentAction.DESIGN_ARCHITECTURE.value,
            AgentAction.DEFINE_CONTRACT.value,
            AgentAction.MAP_WORKFLOW.value,
            AgentAction.CREATE_ACCEPTANCE_GATES.value,
            AgentAction.PLAN_PR.value,
            AgentAction.GENERATE_TESTS.value,
            AgentAction.UPDATE_DOCS.value,
        }
    ),
    AgentSource.CLAUDE.value: frozenset(
        {
            AgentAction.REVIEW_PR.value,
            AgentAction.DESIGN_ARCHITECTURE.value,
            AgentAction.DEFINE_CONTRACT.value,
            AgentAction.PLAN_PR.value,
            AgentAction.GENERATE_TESTS.value,
            AgentAction.GENERATE_PATCH.value,
            AgentAction.FIX_TEST_FAILURE.value,
            AgentAction.UPDATE_DOCS.value,
        }
    ),
    AgentSource.GEMINI.value: frozenset(
        {
            AgentAction.REVIEW_PR.value,
            AgentAction.DESIGN_ARCHITECTURE.value,
            AgentAction.DEFINE_CONTRACT.value,
            AgentAction.PLAN_PR.value,
            AgentAction.GENERATE_TESTS.value,
            AgentAction.UPDATE_DOCS.value,
        }
    ),
    AgentSource.MANUAL.value: frozenset(action.value for action in AgentAction),
}

LOW_RISK_PREFIXES = (
    "docs/",
    "tests/",
)

MEDIUM_RISK_PREFIXES = (
    "core/agent_",
    "scripts/",
)

HIGH_RISK_PREFIXES = (
    "main.py",
    "run_live.sh",
    "config/",
    "core/execution",
    "core/broker",
    "core/order",
    "core/orders",
    "core/risk",
    "core/feed",
    "core/freshness",
    "core/option_token_resolver.py",
    "core/runtime_safety_boot_guard.py",
    "strategies/",
    ".github/workflows/",
)

FORBIDDEN_PATH_PREFIXES = (
    ".env",
    "credentials.py",
    "config/secrets",
    "secrets",
    "runtime/live",
    "logs/broker",
)


@dataclass(frozen=True)
class AgentScopeDecision:
    schema_version: int
    state: str
    accepted: bool
    work_id: str | None
    source_agent: str | None
    action: str | None
    risk_level: str
    read_only: bool
    is_order_action: bool
    broker_api_called: bool
    live_mode_touched: bool
    allowed_for_patch: bool
    allowed_for_runtime_wiring: bool
    allowed_for_live_execution: bool
    requires_human_approval: bool
    requested_paths: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requested_paths"] = list(self.requested_paths)
        payload["allowed_paths"] = list(self.allowed_paths)
        payload["forbidden_paths"] = list(self.forbidden_paths)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _path_text(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    normalized = posixpath.normpath(raw) if raw else ""
    return "" if normalized == "." else normalized


def _is_unsafe_path_shape(path: str) -> bool:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return True
    if text.startswith("/"):
        return True
    parts = [part for part in text.split("/") if part]
    return any(part == ".." for part in parts)


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    normalized = _path_text(path)
    for prefix in prefixes:
        clean_prefix = _path_text(prefix)
        if not clean_prefix:
            continue
        if clean_prefix.endswith("/"):
            base = clean_prefix.rstrip("/")
            if normalized == base or normalized.startswith(f"{base}/"):
                return True
        elif normalized == clean_prefix or normalized.startswith(f"{clean_prefix}/"):
            return True
    return False


def _within_any_allowed_path(path: str, allowed_paths: tuple[str, ...]) -> bool:
    if not allowed_paths:
        return False
    return _matches_prefix(path, allowed_paths)


def _risk_for_paths(paths: tuple[str, ...]) -> str:
    if any(_matches_prefix(path, HIGH_RISK_PREFIXES) for path in paths):
        return AgentScopeRiskLevel.HIGH.value
    if all(_matches_prefix(path, LOW_RISK_PREFIXES) for path in paths):
        return AgentScopeRiskLevel.LOW.value
    if any(_matches_prefix(path, MEDIUM_RISK_PREFIXES) for path in paths):
        return AgentScopeRiskLevel.MEDIUM.value
    return AgentScopeRiskLevel.MEDIUM.value


def assess_agent_scope(
    request: AgentWorkRequest,
    *,
    contract_decision: AgentWorkContractDecision | None = None,
) -> AgentScopeDecision:
    """Assess whether an agent request is allowed to proceed as patch work.

    This function authorizes source/action pairing and requested path scope. It
    does not create approvals, write evidence, or execute changes.
    """

    contract = contract_decision or validate_agent_work_contract(request)

    blockers: list[str] = list(contract.blockers)
    warnings: list[str] = list(contract.warnings)
    reasons: list[str] = []

    requested_paths = tuple(_path_text(path) for path in request.requested_paths)
    allowed_paths = tuple(_path_text(path) for path in request.allowed_paths)
    forbidden_paths = tuple(_path_text(path) for path in request.forbidden_paths)

    if not contract.accepted:
        blockers.append("CONTRACT_DECISION_NOT_ACCEPTED")

    source = request.source_agent
    action = request.action

    allowed_actions = SOURCE_ALLOWED_ACTIONS.get(source)
    if allowed_actions is None:
        blockers.append("SOURCE_AGENT_SCOPE_POLICY_MISSING")
    elif action not in allowed_actions:
        blockers.append("ACTION_NOT_ALLOWED_FOR_SOURCE_AGENT")

    for path in request.requested_paths:
        normalized = _path_text(path)
        if _is_unsafe_path_shape(path):
            blockers.append("REQUESTED_PATH_UNSAFE")
            continue
        if _matches_prefix(normalized, FORBIDDEN_PATH_PREFIXES):
            blockers.append("FORBIDDEN_PATH_REQUESTED")
        if forbidden_paths and _matches_prefix(normalized, forbidden_paths):
            blockers.append("REQUESTED_PATH_EXPLICITLY_FORBIDDEN")
        if not _within_any_allowed_path(normalized, allowed_paths):
            blockers.append("REQUESTED_PATH_OUTSIDE_ALLOWED_PATHS")

    risk_level = AgentScopeRiskLevel.BLOCKED.value if blockers else _risk_for_paths(requested_paths)

    if blockers:
        state = AGENT_SCOPE_BLOCKED
        accepted = False
        allowed_for_patch = False
        requires_human_approval = True
        reasons.append("agent_scope_blocked")
    elif risk_level == AgentScopeRiskLevel.LOW.value and not request.requires_human_approval:
        state = AGENT_SCOPE_APPROVED_FOR_PATCH
        accepted = True
        allowed_for_patch = True
        requires_human_approval = False
        reasons.append("low_risk_scope_approved_for_patch")
    else:
        state = AGENT_SCOPE_WAITING_HUMAN_APPROVAL
        accepted = True
        allowed_for_patch = False
        requires_human_approval = True
        if risk_level == AgentScopeRiskLevel.HIGH.value:
            warnings.append("HIGH_RISK_PATH_REQUIRES_HUMAN_APPROVAL")
            reasons.append("high_risk_scope_requires_human_approval")
        elif risk_level == AgentScopeRiskLevel.MEDIUM.value:
            warnings.append("MEDIUM_RISK_PATH_REQUIRES_HUMAN_APPROVAL")
            reasons.append("medium_risk_scope_requires_human_approval")
        else:
            warnings.append("HUMAN_APPROVAL_REQUESTED")
            reasons.append("human_approval_requested")

    return AgentScopeDecision(
        schema_version=AGENT_WORK_SCHEMA_VERSION,
        state=state,
        accepted=accepted,
        work_id=contract.work_id if accepted else None,
        source_agent=contract.source_agent,
        action=contract.action,
        risk_level=risk_level,
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        live_mode_touched=False,
        allowed_for_patch=allowed_for_patch,
        allowed_for_runtime_wiring=False,
        allowed_for_live_execution=False,
        requires_human_approval=requires_human_approval,
        requested_paths=requested_paths,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        reasons=_dedupe(reasons),
        metadata={
            "contract": "agent_scope_guard_v1",
            "scope": "source_action_path_authorization_only_no_approval_no_execution",
            "contract_state": contract.state,
            "low_risk_prefixes": list(LOW_RISK_PREFIXES),
            "medium_risk_prefixes": list(MEDIUM_RISK_PREFIXES),
            "high_risk_prefixes": list(HIGH_RISK_PREFIXES),
            "forbidden_path_prefixes": list(FORBIDDEN_PATH_PREFIXES),
        },
    )


__all__ = [
    "AGENT_SCOPE_APPROVED_FOR_PATCH",
    "AGENT_SCOPE_BLOCKED",
    "AGENT_SCOPE_WAITING_HUMAN_APPROVAL",
    "FORBIDDEN_PATH_PREFIXES",
    "HIGH_RISK_PREFIXES",
    "LOW_RISK_PREFIXES",
    "MEDIUM_RISK_PREFIXES",
    "SOURCE_ALLOWED_ACTIONS",
    "AgentScopeDecision",
    "AgentScopeRiskLevel",
    "assess_agent_scope",
]
