"""Agent work request contract.

This module defines the local, read-only contract that external or local agents
(GSD, Hermes, Grill Me, Codex, ChatGPT, Claude, Gemini, etc.) must use before any
future scope guard, approval engine, evidence writer, CLI, API, or webhook can
process their work.

It is deliberately not an execution layer. It does not place orders, call broker
APIs, mutate runtime state, approve patches, or wire any dashboard/API behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


AGENT_WORK_SCHEMA_VERSION = 1
AGENT_WORK_CONTRACT_VALID = "AGENT_WORK_CONTRACT_VALID"
AGENT_WORK_CONTRACT_BLOCKED = "AGENT_WORK_CONTRACT_BLOCKED"


class AgentSource(str, Enum):
    """Known agent sources allowed to submit engineering work requests."""

    GSD = "gsd"
    HERMES = "hermes"
    GRILL_ME = "grill_me"
    CODEX = "codex"
    CHATGPT = "chatgpt"
    CLAUDE = "claude"
    GEMINI = "gemini"
    MANUAL = "manual"


class AgentAction(str, Enum):
    """Known agent work actions.

    Dangerous trading actions are intentionally modeled here so contract
    validation can reject them explicitly instead of treating them as unknown.
    """

    CRITIQUE_SCOPE = "CRITIQUE_SCOPE"
    REVIEW_PR = "REVIEW_PR"
    AUDIT_RISK = "AUDIT_RISK"
    FIND_FAKE_PROGRESS = "FIND_FAKE_PROGRESS"
    DESIGN_ARCHITECTURE = "DESIGN_ARCHITECTURE"
    DEFINE_CONTRACT = "DEFINE_CONTRACT"
    MAP_WORKFLOW = "MAP_WORKFLOW"
    CREATE_ACCEPTANCE_GATES = "CREATE_ACCEPTANCE_GATES"
    PLAN_PR = "PLAN_PR"
    GENERATE_TESTS = "GENERATE_TESTS"
    GENERATE_PATCH = "GENERATE_PATCH"
    FIX_TEST_FAILURE = "FIX_TEST_FAILURE"
    UPDATE_DOCS = "UPDATE_DOCS"

    # Explicitly forbidden trading/runtime actions.
    PLACE_ORDER = "PLACE_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    EXIT_ORDER = "EXIT_ORDER"
    ENABLE_LIVE = "ENABLE_LIVE"
    DISABLE_RISK_GATE = "DISABLE_RISK_GATE"
    DISABLE_KILL_SWITCH = "DISABLE_KILL_SWITCH"
    DISABLE_FEED_FRESHNESS_GATE = "DISABLE_FEED_FRESHNESS_GATE"
    CHANGE_BROKER_CONFIG = "CHANGE_BROKER_CONFIG"
    CHANGE_CREDENTIALS = "CHANGE_CREDENTIALS"


FORBIDDEN_AGENT_ACTIONS = frozenset(
    {
        AgentAction.PLACE_ORDER.value,
        AgentAction.MODIFY_ORDER.value,
        AgentAction.CANCEL_ORDER.value,
        AgentAction.EXIT_ORDER.value,
        AgentAction.ENABLE_LIVE.value,
        AgentAction.DISABLE_RISK_GATE.value,
        AgentAction.DISABLE_KILL_SWITCH.value,
        AgentAction.DISABLE_FEED_FRESHNESS_GATE.value,
        AgentAction.CHANGE_BROKER_CONFIG.value,
        AgentAction.CHANGE_CREDENTIALS.value,
    }
)

KNOWN_AGENT_SOURCES = frozenset(source.value for source in AgentSource)
KNOWN_AGENT_ACTIONS = frozenset(action.value for action in AgentAction)


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_text(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _action_text(value: Any) -> str:
    return _text(value).upper().replace("-", "_").replace(" ", "_")


def _tuple_of_text(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = _text(value)
        return (text,) if text else ()
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = _text(item)
            if text:
                out.append(text)
        return tuple(out)
    return ()


def _bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _stable_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


@dataclass(frozen=True)
class AgentWorkRequest:
    schema_version: int
    source_agent: str
    action: str
    title: str
    scope: str
    requested_paths: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    requires_human_approval: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requested_paths"] = list(self.requested_paths)
        payload["allowed_paths"] = list(self.allowed_paths)
        payload["forbidden_paths"] = list(self.forbidden_paths)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class AgentWorkContractDecision:
    schema_version: int
    state: str
    accepted: bool
    work_id: str | None
    source_agent: str | None
    action: str | None
    read_only: bool
    is_order_action: bool
    broker_api_called: bool
    live_mode_touched: bool
    allowed_for_patch: bool
    allowed_for_runtime_wiring: bool
    allowed_for_live_execution: bool
    requires_human_approval: bool
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


def normalize_agent_work_request(payload: Mapping[str, Any]) -> AgentWorkRequest:
    """Normalize an untrusted agent work payload into a stable request object."""

    metadata = payload.get("metadata")
    return AgentWorkRequest(
        schema_version=_as_int(payload.get("schema_version"), default=AGENT_WORK_SCHEMA_VERSION),
        source_agent=_source_text(payload.get("source_agent")),
        action=_action_text(payload.get("action")),
        title=_text(payload.get("title")),
        scope=_text(payload.get("scope")),
        requested_paths=_tuple_of_text(payload.get("requested_paths")),
        allowed_paths=_tuple_of_text(payload.get("allowed_paths")),
        forbidden_paths=_tuple_of_text(payload.get("forbidden_paths")),
        requires_human_approval=_bool(payload.get("requires_human_approval"), default=True),
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


def build_agent_work_id(request: AgentWorkRequest) -> str:
    """Build a deterministic id from request identity fields only."""

    return _stable_id(
        {
            "schema_version": request.schema_version,
            "source_agent": request.source_agent,
            "action": request.action,
            "title": request.title,
            "scope": request.scope,
            "requested_paths": request.requested_paths,
        }
    )


def validate_agent_work_contract(request: AgentWorkRequest) -> AgentWorkContractDecision:
    """Validate the base agent work contract shape.

    This function validates identity, action, and minimum request fields. Path
    authorization, risk classification, and human approval belong to later layers
    and must not be hidden inside this contract PR.
    """

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if request.schema_version != AGENT_WORK_SCHEMA_VERSION:
        blockers.append("AGENT_WORK_SCHEMA_VERSION_UNSUPPORTED")

    if not request.source_agent:
        blockers.append("SOURCE_AGENT_MISSING")
    elif request.source_agent not in KNOWN_AGENT_SOURCES:
        blockers.append("SOURCE_AGENT_UNKNOWN")

    if not request.action:
        blockers.append("ACTION_MISSING")
    elif request.action not in KNOWN_AGENT_ACTIONS:
        blockers.append("ACTION_UNKNOWN")
    elif request.action in FORBIDDEN_AGENT_ACTIONS:
        blockers.append("ACTION_FORBIDDEN")

    if not request.title:
        blockers.append("TITLE_MISSING")

    if not request.scope:
        blockers.append("SCOPE_MISSING")

    if not request.requested_paths:
        blockers.append("REQUESTED_PATHS_MISSING")

    if not request.allowed_paths:
        warnings.append("ALLOWED_PATHS_EMPTY")

    if not request.forbidden_paths:
        warnings.append("FORBIDDEN_PATHS_EMPTY")

    accepted = not blockers
    work_id = build_agent_work_id(request) if accepted else None

    if accepted:
        state = AGENT_WORK_CONTRACT_VALID
        reasons.append("agent_work_contract_valid")
    else:
        state = AGENT_WORK_CONTRACT_BLOCKED
        reasons.append("agent_work_contract_preconditions_failed")

    return AgentWorkContractDecision(
        schema_version=AGENT_WORK_SCHEMA_VERSION,
        state=state,
        accepted=accepted,
        work_id=work_id,
        source_agent=request.source_agent or None,
        action=request.action or None,
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        live_mode_touched=False,
        allowed_for_patch=False,
        allowed_for_runtime_wiring=False,
        allowed_for_live_execution=False,
        requires_human_approval=True,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        reasons=_dedupe(reasons),
        metadata={
            "contract": "agent_work_contract_v1",
            "scope": "contract_validation_only_no_scope_approval_no_execution",
            "known_sources": sorted(KNOWN_AGENT_SOURCES),
            "forbidden_actions": sorted(FORBIDDEN_AGENT_ACTIONS),
        },
    )


__all__ = [
    "AGENT_WORK_CONTRACT_BLOCKED",
    "AGENT_WORK_CONTRACT_VALID",
    "AGENT_WORK_SCHEMA_VERSION",
    "FORBIDDEN_AGENT_ACTIONS",
    "KNOWN_AGENT_ACTIONS",
    "KNOWN_AGENT_SOURCES",
    "AgentAction",
    "AgentSource",
    "AgentWorkContractDecision",
    "AgentWorkRequest",
    "build_agent_work_id",
    "normalize_agent_work_request",
    "validate_agent_work_contract",
]
