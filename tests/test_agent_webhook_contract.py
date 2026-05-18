from __future__ import annotations

import json

from core.agent_webhook_contract import (
    AGENT_WEBHOOK_ACCEPTED_FOR_PATCH,
    AGENT_WEBHOOK_BAD_REQUEST,
    AGENT_WEBHOOK_BLOCKED,
    AGENT_WEBHOOK_ENDPOINT,
    AGENT_WEBHOOK_REJECTED,
    AGENT_WEBHOOK_SCHEMA_VERSION,
    evaluate_agent_webhook_request,
    normalize_agent_webhook_request,
    validate_agent_webhook_request,
)


def _work_payload(**overrides):
    payload = {
        "schema_version": 1,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add webhook contract tests",
        "scope": "Add behavior tests for read-only agent webhook contract evaluation.",
        "requested_paths": ["tests/test_agent_webhook_contract.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return payload


def _envelope(**overrides):
    envelope = {
        "schema_version": AGENT_WEBHOOK_SCHEMA_VERSION,
        "endpoint": AGENT_WEBHOOK_ENDPOINT,
        "delivery_id": "delivery-123",
        "payload": _work_payload(),
        "metadata": {"project": "tradebot"},
    }
    envelope.update(overrides)
    return envelope


def test_normalize_agent_webhook_request_handles_invalid_nested_payload():
    request = normalize_agent_webhook_request(
        {
            "schema_version": "1",
            "endpoint": AGENT_WEBHOOK_ENDPOINT,
            "delivery_id": "delivery-1",
            "payload": "not-an-object",
            "metadata": "not-object",
        }
    )

    assert request.schema_version == AGENT_WEBHOOK_SCHEMA_VERSION
    assert request.endpoint == AGENT_WEBHOOK_ENDPOINT
    assert request.delivery_id == "delivery-1"
    assert request.payload == {}
    assert request.metadata == {}


def test_validate_webhook_request_rejects_bad_envelope():
    request = normalize_agent_webhook_request(
        {
            "schema_version": 999,
            "endpoint": "/wrong",
            "delivery_id": "",
            "payload": {},
            "metadata": {},
        }
    )
    accepted, blockers, warnings = validate_agent_webhook_request(request)

    assert accepted is False
    assert "AGENT_WEBHOOK_SCHEMA_VERSION_UNSUPPORTED" in blockers
    assert "WEBHOOK_ENDPOINT_UNSUPPORTED" in blockers
    assert "WEBHOOK_DELIVERY_ID_MISSING" in blockers
    assert "WEBHOOK_PAYLOAD_MISSING" in blockers
    assert "WEBHOOK_METADATA_EMPTY" in warnings


def test_evaluate_bad_envelope_returns_bad_request_without_pipeline_decisions():
    response = evaluate_agent_webhook_request(_envelope(endpoint="/wrong"))
    payload = response.to_dict()

    assert payload["state"] == AGENT_WEBHOOK_BAD_REQUEST
    assert payload["accepted"] is False
    assert payload["status_code"] == 400
    assert payload["contract_decision"] is None
    assert payload["scope_decision"] is None
    assert payload["approval_decision"] is None
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_mode_touched"] is False
    assert payload["allowed_for_live_execution"] is False
    assert "WEBHOOK_ENDPOINT_UNSUPPORTED" in payload["blockers"]


def test_evaluate_low_risk_payload_accepts_for_patch_only():
    response = evaluate_agent_webhook_request(_envelope())
    payload = response.to_dict()

    assert payload["state"] == AGENT_WEBHOOK_ACCEPTED_FOR_PATCH
    assert payload["accepted"] is True
    assert payload["status_code"] == 200
    assert payload["delivery_id"] == "delivery-123"
    assert payload["work_id"] is not None
    assert payload["allowed_for_patch"] is True
    assert payload["read_only"] is True
    assert payload["allowed_for_runtime_wiring"] is False
    assert payload["allowed_for_live_execution"] is False
    assert payload["contract_decision"]["accepted"] is True
    assert payload["scope_decision"]["accepted"] is True
    assert payload["approval_decision"]["approved"] is True
    json.dumps(payload, sort_keys=True)


def test_evaluate_forbidden_work_payload_is_blocked():
    response = evaluate_agent_webhook_request(_envelope(payload=_work_payload(action="PLACE_ORDER")))
    payload = response.to_dict()

    assert payload["state"] == AGENT_WEBHOOK_BLOCKED
    assert payload["accepted"] is False
    assert payload["status_code"] == 422
    assert payload["work_id"] is None
    assert payload["allowed_for_patch"] is False
    assert "ACTION_FORBIDDEN" in payload["blockers"]
    assert payload["allowed_for_live_execution"] is False


def test_evaluate_high_risk_payload_is_rejected_without_human_approval():
    response = evaluate_agent_webhook_request(
        _envelope(
            payload=_work_payload(
                action="GENERATE_PATCH",
                requested_paths=["core/risk/position_sizing.py"],
                allowed_paths=["core/risk/"],
                forbidden_paths=["credentials.py", ".env"],
            )
        )
    )
    payload = response.to_dict()

    assert payload["state"] == AGENT_WEBHOOK_REJECTED
    assert payload["accepted"] is False
    assert payload["status_code"] == 202
    assert payload["work_id"] is None
    assert "HUMAN_APPROVAL_REQUIRED" in payload["blockers"]
    assert payload["scope_decision"]["requires_human_approval"] is True
    assert payload["approval_decision"]["approved"] is False


def test_evaluate_high_risk_payload_can_be_patch_accepted_with_approver():
    response = evaluate_agent_webhook_request(
        _envelope(
            payload=_work_payload(
                action="GENERATE_PATCH",
                requested_paths=["core/risk/position_sizing.py"],
                allowed_paths=["core/risk/"],
                forbidden_paths=["credentials.py", ".env"],
            )
        ),
        human_approved=True,
        approved_by="ram",
    )
    payload = response.to_dict()

    assert payload["state"] == AGENT_WEBHOOK_ACCEPTED_FOR_PATCH
    assert payload["accepted"] is True
    assert payload["status_code"] == 200
    assert payload["approval_decision"]["approved_by"] == "ram"
    assert payload["allowed_for_patch"] is True
    assert payload["allowed_for_runtime_wiring"] is False
    assert payload["allowed_for_live_execution"] is False


def test_evaluate_grill_me_patch_request_is_blocked():
    response = evaluate_agent_webhook_request(
        _envelope(payload=_work_payload(source_agent="grill_me", action="GENERATE_PATCH"))
    )
    payload = response.to_dict()

    assert payload["state"] == AGENT_WEBHOOK_BLOCKED
    assert payload["accepted"] is False
    assert "ACTION_NOT_ALLOWED_FOR_SOURCE_AGENT" in payload["blockers"]
    assert payload["allowed_for_patch"] is False


def test_response_to_dict_is_json_friendly_for_missing_metadata_warning():
    response = evaluate_agent_webhook_request(_envelope(metadata={}))
    payload = response.to_dict()

    assert payload["accepted"] is True
    assert "WEBHOOK_METADATA_EMPTY" in payload["warnings"]
    assert payload["metadata"]["contract"] == "agent_webhook_contract_v1"
    json.dumps(payload, sort_keys=True)
