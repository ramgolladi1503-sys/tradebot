from __future__ import annotations

import operator
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from .contracts import (
    AgentAction,
    AgentActionType,
    AgentMode,
    Assertion,
    ClaimKind,
    Finding,
    FindingProposal,
    FindingStatus,
    Severity,
    ToolRequest,
    ToolResult,
    VerificationResult,
)
from .evidence import EvidenceLedger

ToolHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class Reasoner(Protocol):
    def next_action(self, context: Mapping[str, Any]) -> AgentAction: ...


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    handler: ToolHandler
    read_only: bool
    description: str


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, handler: ToolHandler, *, read_only: bool = True, description: str = "") -> None:
        clean = str(name).strip()
        if not clean:
            raise ValueError("tool_name_required")
        if clean in self._tools:
            raise ValueError(f"tool_already_registered:{clean}")
        self._tools[clean] = RegisteredTool(clean, handler, bool(read_only), str(description))

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"name": item.name, "read_only": item.read_only, "description": item.description}
            for item in sorted(self._tools.values(), key=lambda row: row.name)
        ]

    def execute(self, request: ToolRequest, *, mode: AgentMode, ledger: EvidenceLedger, session_id: str) -> ToolResult:
        tool = self._tools.get(request.tool_name)
        if tool is None:
            return ToolResult(request.tool_name, False, {}, error_code="UNKNOWN_TOOL")
        if mode == AgentMode.LIVE_OBSERVE and not tool.read_only:
            return ToolResult(request.tool_name, False, {}, error_code="LIVE_MODE_WRITE_TOOL_BLOCKED")
        try:
            payload = dict(tool.handler(dict(request.arguments)) or {})
        except Exception as exc:
            failure = {"error_type": type(exc).__name__, "error": str(exc)[:500], "arguments": dict(request.arguments)}
            ref = ledger.append("tool_error", {"tool_name": request.tool_name, **failure}, session_id=session_id)
            return ToolResult(request.tool_name, False, failure, evidence_ref=ref, error_code="TOOL_EXECUTION_FAILED")
        ref = ledger.append(
            "tool_result",
            {"tool_name": request.tool_name, "arguments": dict(request.arguments), "payload": payload},
            session_id=session_id,
        )
        return ToolResult(request.tool_name, True, payload, evidence_ref=ref)


class ScriptedReasoner:
    """Deterministic reasoner for tests, simulation certification and offline replay."""

    def __init__(self, actions: list[AgentAction]):
        self.actions = list(actions)

    def next_action(self, context: Mapping[str, Any]) -> AgentAction:
        if not self.actions:
            return AgentAction(AgentActionType.STOP, stop_reason="script_exhausted")
        return self.actions.pop(0)


class AssertionVerifier:
    _OPS = {
        "eq": operator.eq,
        "ne": operator.ne,
        "gt": operator.gt,
        "ge": operator.ge,
        "lt": operator.lt,
        "le": operator.le,
        "contains": lambda actual, expected: expected in actual,
        "not_contains": lambda actual, expected: expected not in actual,
        "truthy": lambda actual, expected: bool(actual) is bool(expected),
        "is_none": lambda actual, expected: (actual is None) is bool(expected),
    }

    def verify(self, proposal: FindingProposal, ledger: EvidenceLedger) -> VerificationResult:
        reasons: list[str] = []
        if not proposal.evidence_ids:
            return VerificationResult(FindingStatus.INSUFFICIENT_EVIDENCE, ("finding_missing_evidence_ids",), 0, 0)
        have_all, missing = ledger.require(proposal.evidence_ids)
        if not have_all:
            return VerificationResult(
                FindingStatus.INSUFFICIENT_EVIDENCE,
                tuple(f"missing_evidence:{item}" for item in missing),
                len(proposal.assertions),
                0,
            )
        if proposal.claim_kind == ClaimKind.DETERMINISTIC_FACT and not proposal.assertions:
            return VerificationResult(FindingStatus.INSUFFICIENT_EVIDENCE, ("deterministic_fact_requires_assertions",), 0, 0)
        passed = 0
        for index, assertion in enumerate(proposal.assertions):
            payload = ledger.payload(assertion.evidence_id)
            if payload is None:
                reasons.append(f"assertion_{index}:evidence_payload_missing")
                continue
            actual, found = _resolve_path(payload, assertion.path)
            if not found:
                reasons.append(f"assertion_{index}:path_missing:{assertion.path}")
                continue
            op = self._OPS.get(assertion.operator)
            if op is None:
                reasons.append(f"assertion_{index}:operator_unknown:{assertion.operator}")
                continue
            try:
                ok = bool(op(actual, assertion.expected))
            except Exception:
                ok = False
            if ok:
                passed += 1
            else:
                reasons.append(f"assertion_{index}:failed:{assertion.path}:{assertion.operator}")
        if reasons:
            return VerificationResult(FindingStatus.REJECTED, tuple(reasons), len(proposal.assertions), passed)
        return VerificationResult(FindingStatus.CONFIRMED, (), len(proposal.assertions), passed)


class ReliabilityAgent:
    """Bounded observe-hypothesize-tool-verify loop with fail-closed findings."""

    def __init__(
        self,
        *,
        session_id: str,
        mode: AgentMode,
        reasoner: Reasoner,
        tools: ToolRegistry,
        ledger: EvidenceLedger,
        verifier: AssertionVerifier | None = None,
        max_steps: int = 12,
        max_tool_calls: int = 8,
    ):
        if max_steps <= 0 or max_tool_calls < 0:
            raise ValueError("invalid_agent_budget")
        self.session_id = str(session_id)
        self.mode = mode
        self.reasoner = reasoner
        self.tools = tools
        self.ledger = ledger
        self.verifier = verifier or AssertionVerifier()
        self.max_steps = int(max_steps)
        self.max_tool_calls = int(max_tool_calls)

    def run(self, objective: str, *, initial_observations: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state: dict[str, Any] = {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "objective": str(objective),
            "initial_observations": dict(initial_observations or {}),
            "tool_schemas": self.tools.schemas(),
            "tool_results": [],
            "findings": [],
            "rejected_findings": [],
        }
        tool_calls = 0
        stop_reason = "budget_exhausted"
        for step in range(self.max_steps):
            state["step"] = step
            action = self.reasoner.next_action(_safe_context(state))
            if not isinstance(action, AgentAction):
                stop_reason = "reasoner_returned_invalid_action"
                break
            if action.action_type == AgentActionType.STOP:
                stop_reason = action.stop_reason or "reasoner_stopped"
                break
            if action.action_type == AgentActionType.TOOL:
                if action.tool_request is None:
                    stop_reason = "tool_action_missing_request"
                    break
                if tool_calls >= self.max_tool_calls:
                    stop_reason = "tool_budget_exhausted"
                    break
                result = self.tools.execute(action.tool_request, mode=self.mode, ledger=self.ledger, session_id=self.session_id)
                tool_calls += 1
                state["tool_results"].append(result.to_dict())
                continue
            if action.action_type == AgentActionType.PROPOSE_FINDING:
                if action.finding is None:
                    stop_reason = "finding_action_missing_proposal"
                    break
                verification = self.verifier.verify(action.finding, self.ledger)
                finding = Finding(
                    finding_id=f"F-{uuid.uuid4().hex}",
                    session_id=self.session_id,
                    proposal=action.finding,
                    verification=verification,
                    created_at=datetime.now(tz=timezone.utc).isoformat(),
                )
                event_type = "finding_confirmed" if verification.status == FindingStatus.CONFIRMED else "finding_rejected"
                self.ledger.append(event_type, finding.to_dict(), session_id=self.session_id)
                target = "findings" if verification.status == FindingStatus.CONFIRMED else "rejected_findings"
                state[target].append(finding.to_dict())
                continue
            stop_reason = "unsupported_action"
            break
        chain = self.ledger.verify()
        return {
            **state,
            "stop_reason": stop_reason,
            "tool_calls": tool_calls,
            "evidence_chain_valid": chain.valid,
            "evidence_chain_errors": list(chain.errors),
        }


def _resolve_path(payload: Mapping[str, Any], path: str) -> tuple[Any, bool]:
    current: Any = payload
    for part in str(path).split("."):
        if not part:
            continue
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return None, False
    return current, True


def _safe_context(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "session_id": state.get("session_id"),
        "mode": state.get("mode"),
        "objective": state.get("objective"),
        "initial_observations": state.get("initial_observations"),
        "tool_schemas": state.get("tool_schemas"),
        "tool_results": list(state.get("tool_results") or [])[-8:],
        "findings": list(state.get("findings") or []),
        "rejected_findings": list(state.get("rejected_findings") or []),
        "step": state.get("step"),
    }
