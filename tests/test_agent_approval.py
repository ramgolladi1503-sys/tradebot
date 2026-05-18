from __future__ import annotations

from dataclasses import replace

from core.agent_approval import (
    AGENT_APPROVAL_APPROVED_FOR_PATCH,
    AGENT_APPROVAL_REJECTED,
    approve_agent_scope,
)
from core.agent_scope_guard import assess_agent_scope
from core.agent_work_contract import AGENT_WORK_SCHEMA_VERSION, normalize_agent_work_request


def _request(**overrides):
    payload = {
        "schema_version": AGENT_WORK_SCHEMA_VERSION,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add scope guard tests",
        "scope": "Add behavior tests for agent scope validation.",
        "requested_paths": ["tests/test_agent_scope_guard.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return normalize_agent_work_request(payload)


def test_low_risk_scope_can_be_approved_for_patch_only():
    scope_decision = assess_agent_scope(_request())
    approval = approve_agent_scope(scope_decision)

    assert approval.state == AGENT_APPROVAL_APPROVED_FOR_PATCH
    assert approval.approved is True
    assert approval.work_id == scope_decision.work_id
    assert approval.allowed_for_patch is True
    assert approval.read_only is True
    assert approval.is_order_action is False
    assert approval.broker_api_called is False
    assert approval.live_mode_touched is False
    assert approval.allowed_for_runtime_wiring is False
    assert approval.allowed_for_live_execution is False
    assert approval.blockers == ()
    assert "AGENT_WORK_APPROVED_FOR_PATCH_ONLY" in approval.reasons


def test_high_risk_scope_waits_for_human_approval():
    scope_decision = assess_agent_scope(
        _request(
            source_agent="gsd",
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
        )
    )
    approval = approve_agent_scope(scope_decision)

    assert approval.state == AGENT_APPROVAL_REJECTED
    assert approval.approved is False
    assert approval.allowed_for_patch is False
    assert approval.work_id is None
    assert "HUMAN_APPROVAL_REQUIRED" in approval.blockers


def test_high_risk_scope_can_receive_patch_only_approval_with_approver():
    scope_decision = assess_agent_scope(
        _request(
            source_agent="gsd",
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
        )
    )
    approval = approve_agent_scope(scope_decision, human_approved=True, approved_by="ram")

    assert approval.state == AGENT_APPROVAL_APPROVED_FOR_PATCH
    assert approval.approved is True
    assert approval.approved_by == "ram"
    assert approval.allowed_for_patch is True
    assert approval.allowed_for_runtime_wiring is False
    assert approval.allowed_for_live_execution is False


def test_human_approved_work_requires_approver_id():
    scope_decision = assess_agent_scope(
        _request(
            source_agent="gsd",
            action="GENERATE_PATCH",
            requested_paths=["core/agent_work_contract.py"],
            allowed_paths=["core/agent_"],
            forbidden_paths=["credentials.py", ".env"],
        )
    )
    approval = approve_agent_scope(scope_decision, human_approved=True, approved_by="")

    assert approval.state == AGENT_APPROVAL_REJECTED
    assert approval.approved is False
    assert "APPROVER_ID_REQUIRED" in approval.blockers


def test_blocked_scope_cannot_be_approved_even_with_human_flag():
    scope_decision = assess_agent_scope(_request(source_agent="grill_me", action="GENERATE_PATCH"))
    approval = approve_agent_scope(scope_decision, human_approved=True, approved_by="ram")

    assert approval.state == AGENT_APPROVAL_REJECTED
    assert approval.approved is False
    assert "SCOPE_DECISION_NOT_ACCEPTED" in approval.blockers
    assert "BLOCKED_SCOPE_CANNOT_BE_APPROVED" in approval.blockers
    assert approval.allowed_for_patch is False
    assert approval.work_id is None


def test_escalated_scope_flags_are_rejected_fail_closed():
    scope_decision = assess_agent_scope(_request())
    escalated = replace(
        scope_decision,
        is_order_action=True,
        broker_api_called=True,
        live_mode_touched=True,
        allowed_for_runtime_wiring=True,
        allowed_for_live_execution=True,
    )
    approval = approve_agent_scope(escalated)

    assert approval.state == AGENT_APPROVAL_REJECTED
    assert approval.approved is False
    assert "ORDER_ACTION_FORBIDDEN" in approval.blockers
    assert "BROKER_API_CALL_FORBIDDEN" in approval.blockers
    assert "LIVE_MODE_TOUCH_FORBIDDEN" in approval.blockers
    assert "RUNTIME_WIRING_PERMISSION_FORBIDDEN" in approval.blockers
    assert "LIVE_EXECUTION_PERMISSION_FORBIDDEN" in approval.blockers
    assert approval.is_order_action is False
    assert approval.broker_api_called is False
    assert approval.allowed_for_live_execution is False


def test_to_dict_is_json_friendly_and_stable():
    approval = approve_agent_scope(assess_agent_scope(_request()))
    payload = approval.to_dict()

    assert payload["schema_version"] == AGENT_WORK_SCHEMA_VERSION
    assert payload["state"] == AGENT_APPROVAL_APPROVED_FOR_PATCH
    assert payload["approved"] is True
    assert payload["read_only"] is True
    assert payload["allowed_for_runtime_wiring"] is False
    assert payload["allowed_for_live_execution"] is False
    assert payload["blockers"] == []
    assert payload["metadata"]["contract"] == "agent_approval_v1"
