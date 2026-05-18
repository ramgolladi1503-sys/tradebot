from __future__ import annotations

from core.agent_scope_guard import (
    AGENT_SCOPE_APPROVED_FOR_PATCH,
    AGENT_SCOPE_BLOCKED,
    AGENT_SCOPE_WAITING_HUMAN_APPROVAL,
    assess_agent_scope,
)
from core.agent_work_contract import AGENT_WORK_SCHEMA_VERSION, normalize_agent_work_request


def _request(**overrides):
    payload = {
        "schema_version": AGENT_WORK_SCHEMA_VERSION,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add scope guard tests",
        "scope": "Add behavior tests proving the agent scope guard blocks unsafe work.",
        "requested_paths": ["tests/test_agent_scope_guard.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return normalize_agent_work_request(payload)


def test_gsd_can_generate_tests_inside_allowed_path_without_human_approval():
    decision = assess_agent_scope(_request())

    assert decision.state == AGENT_SCOPE_APPROVED_FOR_PATCH
    assert decision.accepted is True
    assert decision.risk_level == "LOW"
    assert decision.allowed_for_patch is True
    assert decision.requires_human_approval is False
    assert decision.is_order_action is False
    assert decision.broker_api_called is False
    assert decision.live_mode_touched is False
    assert decision.allowed_for_runtime_wiring is False
    assert decision.allowed_for_live_execution is False
    assert decision.blockers == ()
    assert "LOW_RISK_SCOPE_APPROVED_FOR_PATCH" in decision.reasons


def test_docs_only_work_is_low_risk_patch_approved_for_hermes_docs_update():
    decision = assess_agent_scope(
        _request(
            source_agent="hermes",
            action="UPDATE_DOCS",
            requested_paths=["docs/AGENT_WORKFLOW.md"],
            allowed_paths=["docs/"],
        )
    )

    assert decision.state == AGENT_SCOPE_APPROVED_FOR_PATCH
    assert decision.risk_level == "LOW"
    assert decision.allowed_for_patch is True
    assert decision.requires_human_approval is False


def test_grill_me_cannot_generate_patch_even_inside_allowed_path():
    decision = assess_agent_scope(
        _request(
            source_agent="grill_me",
            action="GENERATE_PATCH",
            requested_paths=["tests/test_agent_scope_guard.py"],
            allowed_paths=["tests/"],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert decision.accepted is False
    assert decision.allowed_for_patch is False
    assert "ACTION_NOT_ALLOWED_FOR_SOURCE_AGENT" in decision.blockers


def test_hermes_cannot_request_execution_patch():
    decision = assess_agent_scope(
        _request(
            source_agent="hermes",
            action="GENERATE_PATCH",
            requested_paths=["core/execution_router.py"],
            allowed_paths=["core/execution_router.py"],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "ACTION_NOT_ALLOWED_FOR_SOURCE_AGENT" in decision.blockers
    assert decision.allowed_for_live_execution is False


def test_forbidden_contract_action_stays_blocked_by_scope_guard():
    decision = assess_agent_scope(_request(action="PLACE_ORDER"))

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert decision.accepted is False
    assert "ACTION_FORBIDDEN" in decision.blockers
    assert "CONTRACT_DECISION_NOT_ACCEPTED" in decision.blockers
    assert decision.work_id is None


def test_requested_path_outside_allowed_paths_blocks():
    decision = assess_agent_scope(
        _request(
            requested_paths=["core/agent_scope_guard.py"],
            allowed_paths=["tests/"],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "REQUESTED_PATH_OUTSIDE_ALLOWED_PATHS" in decision.blockers


def test_explicitly_forbidden_path_blocks():
    decision = assess_agent_scope(
        _request(
            requested_paths=["core/broker/client.py"],
            allowed_paths=["core/broker/"],
            forbidden_paths=["core/broker"],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "REQUESTED_PATH_EXPLICITLY_FORBIDDEN" in decision.blockers
    assert "FORBIDDEN_PATH_REQUESTED" not in decision.blockers


def test_credentials_path_blocks_even_if_allowed_path_claims_it():
    decision = assess_agent_scope(
        _request(
            requested_paths=["credentials.py"],
            allowed_paths=["credentials.py"],
            forbidden_paths=[],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "FORBIDDEN_PATH_REQUESTED" in decision.blockers
    assert decision.allowed_for_patch is False


def test_dot_env_path_blocks_even_if_allowed_path_claims_it():
    decision = assess_agent_scope(
        _request(
            requested_paths=[".env"],
            allowed_paths=[".env"],
            forbidden_paths=[],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "FORBIDDEN_PATH_REQUESTED" in decision.blockers


def test_parent_directory_escape_blocks():
    decision = assess_agent_scope(
        _request(
            requested_paths=["tests/../credentials.py"],
            allowed_paths=["tests/"],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "REQUESTED_PATH_UNSAFE" in decision.blockers


def test_absolute_path_blocks():
    decision = assess_agent_scope(
        _request(
            requested_paths=["/tmp/evil.py"],
            allowed_paths=["/tmp/"],
        )
    )

    assert decision.state == AGENT_SCOPE_BLOCKED
    assert "REQUESTED_PATH_UNSAFE" in decision.blockers


def test_high_risk_runtime_path_requires_human_approval_but_does_not_approve_patch():
    decision = assess_agent_scope(
        _request(
            source_agent="gsd",
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
        )
    )

    assert decision.state == AGENT_SCOPE_WAITING_HUMAN_APPROVAL
    assert decision.accepted is True
    assert decision.risk_level == "HIGH"
    assert decision.allowed_for_patch is False
    assert decision.requires_human_approval is True
    assert decision.allowed_for_runtime_wiring is False
    assert decision.allowed_for_live_execution is False
    assert "HIGH_RISK_PATH_REQUIRES_HUMAN_APPROVAL" in decision.warnings


def test_medium_risk_agent_core_path_requires_human_approval():
    decision = assess_agent_scope(
        _request(
            source_agent="gsd",
            action="GENERATE_PATCH",
            requested_paths=["core/agent_work_contract.py"],
            allowed_paths=["core/agent_"],
            forbidden_paths=["credentials.py", ".env"],
        )
    )

    assert decision.state == AGENT_SCOPE_WAITING_HUMAN_APPROVAL
    assert decision.risk_level == "MEDIUM"
    assert decision.allowed_for_patch is False
    assert decision.requires_human_approval is True
    assert "MEDIUM_RISK_PATH_REQUIRES_HUMAN_APPROVAL" in decision.warnings


def test_low_risk_request_with_explicit_human_approval_waits_for_approval():
    decision = assess_agent_scope(
        _request(
            requested_paths=["tests/test_agent_scope_guard.py"],
            allowed_paths=["tests/"],
            requires_human_approval=True,
        )
    )

    assert decision.state == AGENT_SCOPE_WAITING_HUMAN_APPROVAL
    assert decision.risk_level == "LOW"
    assert decision.allowed_for_patch is False
    assert decision.requires_human_approval is True
    assert "HUMAN_APPROVAL_REQUESTED" in decision.warnings


def test_to_dict_is_json_friendly_and_stable():
    decision = assess_agent_scope(_request())
    payload = decision.to_dict()

    assert payload["schema_version"] == AGENT_WORK_SCHEMA_VERSION
    assert payload["state"] == AGENT_SCOPE_APPROVED_FOR_PATCH
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_mode_touched"] is False
    assert payload["allowed_for_live_execution"] is False
    assert payload["requested_paths"] == ["tests/test_agent_scope_guard.py"]
    assert payload["allowed_paths"] == ["tests"]
    assert payload["forbidden_paths"] == ["credentials.py", ".env", "core/broker"]
    assert payload["blockers"] == []
    assert payload["metadata"]["contract"] == "agent_scope_guard_v1"
