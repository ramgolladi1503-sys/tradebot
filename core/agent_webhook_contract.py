"""Read-only agent webhook contract.

This module defines how a future local/private webhook envelope should be
validated and evaluated. It deliberately does not register an HTTP route, start a
server, expose a public endpoint, merge code, call brokers, create paper orders,
or touch live configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.agent_approval import approve_agent_scope
from core.agent_scope_guard import assess_agent_scope
from core.agent_work_contract import (
    AGENT_WORK_SCHEMA_VERSION,
    normalize_agent_work_request,
    validate_agent_work_contract,
)


AGENT_WEBHOOK_SCHEMA_VERSION = 1
AGENT_WEBHOOK_ENDPOINT = "/agent/work"

AGENT_WEBHOOK_ACCEPTED_FOR_PATCH = "AGENT_WEBHOOK_ACCEPTED_FOR_PATCH"
AGENT_WEBHOOK_BLOCKED = "AGENT_WEBHOOK_BLOCKED"
AGENT_WEBHOOK_REJECTED = "AGENT_WEBHOOK_REJECTED"
AGENT_WEBHOOK_BAD_REQUEST = "AGENT_WEBHOOK_BAD_REQUEST"


@dataclass(frozen=True)
class AgentWebhookRequest:
    schema_version: int
    endpoint: str
    delivery_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "endpoint": self.endpoint,
            "delivery_id": self.delivery_id,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AgentWebhookResponse:
    schema_version: int
    state: str
    accepted: bool
    status_code: int
    delivery_id: str | None
    work_id: str | None
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
    contract_decision: dict[str, Any] | None
    scope_decision: dict[str, Any] | None
    approval_decision: dict[str, Any] | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def normalize_agent_webhook_request(envelope: Mapping[str, Any]) -> AgentWebhookRequest:
    """Normalize an untrusted future webhook envelope.

    Expected envelope shape:

    ```json
    {
      "schema_version": 1,
      "endpoint": "/agent/work",
      "delivery_id": "unique-id-from-caller",
      "payload": {"source_agent": "gsd", "action": "GENERATE_TESTS", ...},
      "metadata": {"project": "tradebot"}
    }
    ```
    """

    payload = envelope.get("payload")
    metadata = envelope.get("metadata")
    return AgentWebhookRequest(
        schema_version=_as_int(envelope.get("schema_version"), default=AGENT_WEBHOOK_SCHEMA_VERSION),
        endpoint=_text(envelope.get("endpoint")),
        delivery_id=_text(envelope.get("delivery_id")),
        payload=dict(payload) if isinstance(payload, Mapping) else {},
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


def validate_agent_webhook_request(request: AgentWebhookRequest) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if request.schema_version != AGENT_WEBHOOK_SCHEMA_VERSION:
        blockers.append("AGENT_WEBHOOK_SCHEMA_VERSION_UNSUPPORTED")
    if not request.endpoint:
        blockers.append("WEBHOOK_ENDPOINT_MISSING")
    elif request.endpoint != AGENT_WEBHOOK_ENDPOINT:
        blockers.append("WEBHOOK_ENDPOINT_UNSUPPORTED")
    if not request.delivery_id:
        blockers.append("WEBHOOK_DELIVERY_ID_MISSING")
    if not request.payload:
        blockers.append("WEBHOOK_PAYLOAD_MISSING")
    if not request.metadata:
        warnings.append("WEBHOOK_METADATA_EMPTY")

    return not blockers, _dedupe(blockers), _dedupe(warnings)


def evaluate_agent_webhook_request(
    envelope: Mapping[str, Any],
    *,
    human_approved: bool = False,
    approved_by: str | None = None,
) -> AgentWebhookResponse:
    """Evaluate a future webhook envelope through the safe agent pipeline.

    This function is pure contract logic. It does not write evidence and does not
    expose a network listener. A future HTTP adapter may call this function after
    its own authentication and rate limiting checks.
    """

    request = normalize_agent_webhook_request(envelope)
    envelope_ok, envelope_blockers, envelope_warnings = validate_agent_webhook_request(request)

    if not envelope_ok:
        return AgentWebhookResponse(
            schema_version=AGENT_WEBHOOK_SCHEMA_VERSION,
            state=AGENT_WEBHOOK_BAD_REQUEST,
            accepted=False,
            status_code=400,
            delivery_id=request.delivery_id or None,
            work_id=None,
            read_only=True,
            is_order_action=False,
            broker_api_called=False,
            live_mode_touched=False,
            allowed_for_patch=False,
            allowed_for_runtime_wiring=False,
            allowed_for_live_execution=False,
            blockers=envelope_blockers,
            warnings=envelope_warnings,
            reasons=("AGENT_WEBHOOK_ENVELOPE_INVALID",),
            contract_decision=None,
            scope_decision=None,
            approval_decision=None,
            metadata={
                "contract": "agent_webhook_contract_v1",
                "scope": "read_only_envelope_validation_no_http_adapter",
            },
        )

    work_request = normalize_agent_work_request(request.payload)
    contract_decision = validate_agent_work_contract(work_request)
    scope_decision = assess_agent_scope(work_request, contract_decision=contract_decision)
    approval_decision = approve_agent_scope(
        scope_decision,
        human_approved=human_approved,
        approved_by=approved_by,
    )

    blockers: list[str] = list(envelope_blockers)
    warnings: list[str] = list(envelope_warnings)
    reasons: list[str] = []
    status_code = 200

    if not contract_decision.accepted or not scope_decision.accepted:
        state = AGENT_WEBHOOK_BLOCKED
        accepted = False
        blockers.extend(contract_decision.blockers)
        blockers.extend(scope_decision.blockers)
        warnings.extend(contract_decision.warnings)
        warnings.extend(scope_decision.warnings)
        reasons.append("agent_webhook_work_blocked")
        status_code = 422
    elif not approval_decision.approved:
        state = AGENT_WEBHOOK_REJECTED
        accepted = False
        blockers.extend(approval_decision.blockers)
        warnings.extend(scope_decision.warnings)
        warnings.extend(approval_decision.warnings)
        reasons.append("agent_webhook_approval_rejected")
        status_code = 202
    else:
        state = AGENT_WEBHOOK_ACCEPTED_FOR_PATCH
        accepted = True
        warnings.extend(scope_decision.warnings)
        warnings.extend(approval_decision.warnings)
        reasons.append("agent_webhook_accepted_for_patch_only")

    return AgentWebhookResponse(
        schema_version=AGENT_WEBHOOK_SCHEMA_VERSION,
        state=state,
        accepted=accepted,
        status_code=status_code,
        delivery_id=request.delivery_id,
        work_id=approval_decision.work_id if accepted else None,
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        live_mode_touched=False,
        allowed_for_patch=bool(approval_decision.allowed_for_patch and accepted),
        allowed_for_runtime_wiring=False,
        allowed_for_live_execution=False,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        reasons=_dedupe(reasons),
        contract_decision=contract_decision.to_dict(),
        scope_decision=scope_decision.to_dict(),
        approval_decision=approval_decision.to_dict(),
        metadata={
            "contract": "agent_webhook_contract_v1",
            "scope": "read_only_contract_only_no_http_adapter_no_runtime",
            "work_schema_version": AGENT_WORK_SCHEMA_VERSION,
        },
    )


__all__ = [
    "AGENT_WEBHOOK_ACCEPTED_FOR_PATCH",
    "AGENT_WEBHOOK_BAD_REQUEST",
    "AGENT_WEBHOOK_BLOCKED",
    "AGENT_WEBHOOK_ENDPOINT",
    "AGENT_WEBHOOK_REJECTED",
    "AGENT_WEBHOOK_SCHEMA_VERSION",
    "AgentWebhookRequest",
    "AgentWebhookResponse",
    "evaluate_agent_webhook_request",
    "normalize_agent_webhook_request",
    "validate_agent_webhook_request",
]
