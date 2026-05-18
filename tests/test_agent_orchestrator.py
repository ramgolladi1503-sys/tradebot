from __future__ import annotations

import json

from core.agent_orchestrator import (
    AgentOrchestrationState,
    evaluate_agent_review_orchestration,
    normalize_agent_review_record,
)


def _work(**overrides):
    payload = {
        "schema_version": 1,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add orchestrator tests",
        "scope": "Add behavior tests for the local agent review orchestrator.",
        "requested_paths": ["tests/test_agent_orchestrator.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return payload


def _review(stage: str, decision: str = "APPROVE", **overrides):
    payload = {
        "schema_version": 1,
        "stage": stage,
        "reviewer": stage.lower(),
        "decision": decision,
        "summary": f"{stage} reviewed and approved the request.",
        "risks": [],
        "required_changes": [],
        "approved_paths": ["tests/"],
        "blocked_paths": ["credentials.py", ".env", "core/broker"],
        "evidence": {"reviewed": True},
    }
    payload.update(overrides)
    return payload


def _all_reviews(**overrides):
    reviews = [
        _review("GRILL_ME"),
        _review("HERMES"),
        _review("GSD", decision="READY"),
    ]
    for index, patch in overrides.items():
        reviews[int(index)].update(patch)
    return reviews


def test_normalize_review_record_handles_spelling_variants():
    review = normalize_agent_review_record(
        {
            "stage": "grill-me",
            "reviewer": " critic ",
            "decision": "needs human",
            "summary": "Needs owner decision",
            "risks": ["scope creep"],
            "required_changes": ["reduce scope"],
            "approved_paths": ["tests/"],
            "blocked_paths": ["core/risk"],
            "evidence": {"note": "ok"},
        }
    )

    assert review.stage == "GRILL_ME"
    assert review.reviewer == "critic"
    assert review.decision == "NEEDS_HUMAN"
    assert review.risks == ("scope creep",)
    assert review.evidence == {"note": "ok"}


def test_missing_required_reviews_blocks_orchestration():
    decision = evaluate_agent_review_orchestration(_work(), [_review("GRILL_ME")])
    payload = decision.to_dict()

    assert payload["state"] == AgentOrchestrationState.REVIEW_REQUIRED.value
    assert payload["accepted"] is False
    assert payload["allowed_for_patch"] is False
    assert payload["missing_stages"] == ["HERMES", "GSD"]
    assert "REQUIRED_AGENT_REVIEW_MISSING" in payload["blockers"]
    assert payload["read_only"] is True
    assert payload["allowed_for_live_execution"] is False


def test_all_required_reviews_approve_low_risk_work_for_patch_only():
    decision = evaluate_agent_review_orchestration(_work(), _all_reviews())
    payload = decision.to_dict()

    assert payload["state"] == AgentOrchestrationState.APPROVED_FOR_PATCH.value
    assert payload["accepted"] is True
    assert payload["work_id"] is not None
    assert payload["completed_stages"] == ["GRILL_ME", "HERMES", "GSD"]
    assert payload["missing_stages"] == []
    assert payload["allowed_for_patch"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_mode_touched"] is False
    assert payload["allowed_for_runtime_wiring"] is False
    assert payload["allowed_for_live_execution"] is False
    assert payload["blockers"] == []
    assert "AGENT_REVIEWS_APPROVED_FOR_PATCH_ONLY" in payload["reasons"]
    json.dumps(payload, sort_keys=True)


def test_grill_me_rejection_rejects_orchestration():
    reviews = _all_reviews(**{"0": {"decision": "REJECT", "summary": "Fake progress."}})
    decision = evaluate_agent_review_orchestration(_work(), reviews)

    assert decision.state == AgentOrchestrationState.REJECTED.value
    assert decision.accepted is False
    assert "AGENT_REVIEW_REJECTED" in decision.blockers
    assert decision.allowed_for_patch is False


def test_hermes_rewrite_blocks_until_scope_is_fixed():
    reviews = _all_reviews(**{"1": {"decision": "REWRITE", "summary": "Acceptance gates missing."}})
    decision = evaluate_agent_review_orchestration(_work(), reviews)

    assert decision.state == AgentOrchestrationState.REWRITE_REQUIRED.value
    assert decision.accepted is False
    assert "AGENT_REVIEW_REWRITE_REQUIRED" in decision.blockers
    assert "AGENT_REVIEW_REWRITE_REQUIRED" in decision.reasons


def test_gsd_needs_human_does_not_count_as_approval():
    reviews = _all_reviews(**{"2": {"decision": "NEEDS_HUMAN", "summary": "Needs owner choice."}})
    decision = evaluate_agent_review_orchestration(_work(), reviews)

    assert decision.accepted is False
    assert "REQUIRED_AGENT_REVIEW_NOT_APPROVED" in decision.blockers
    assert "AGENT_REVIEW_NEEDS_HUMAN" in decision.warnings


def test_review_blocked_requested_path_blocks_orchestration():
    reviews = _all_reviews(**{"0": {"blocked_paths": ["tests/test_agent_orchestrator.py"]}})
    decision = evaluate_agent_review_orchestration(_work(), reviews)

    assert decision.state == AgentOrchestrationState.BLOCKED.value
    assert decision.accepted is False
    assert "REVIEW_BLOCKED_REQUESTED_PATH:GRILL_ME" in decision.blockers


def test_invalid_review_record_blocks_orchestration():
    reviews = _all_reviews(**{"1": {"reviewer": "", "summary": "", "decision": "MAYBE"}})
    decision = evaluate_agent_review_orchestration(_work(), reviews)

    assert decision.accepted is False
    assert "REVIEWER_MISSING" in decision.blockers
    assert "REVIEW_DECISION_UNKNOWN" in decision.blockers
    assert "REVIEW_SUMMARY_MISSING" in decision.blockers


def test_high_risk_work_waits_for_human_after_reviews_pass():
    decision = evaluate_agent_review_orchestration(
        _work(
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
            requires_human_approval=True,
        ),
        _all_reviews(),
    )

    assert decision.state == AgentOrchestrationState.WAITING_HUMAN_APPROVAL.value
    assert decision.accepted is False
    assert decision.allowed_for_patch is False
    assert "HUMAN_APPROVAL_REQUIRED" in decision.blockers


def test_high_risk_work_can_be_patch_approved_after_reviews_and_human_approval():
    decision = evaluate_agent_review_orchestration(
        _work(
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
            requires_human_approval=True,
        ),
        _all_reviews(),
        human_approved=True,
        approved_by="ram",
    )

    assert decision.state == AgentOrchestrationState.APPROVED_FOR_PATCH.value
    assert decision.accepted is True
    assert decision.allowed_for_patch is True
    assert decision.allowed_for_runtime_wiring is False
    assert decision.allowed_for_live_execution is False
    assert decision.approval_decision["approved_by"] == "ram"


def test_forbidden_work_remains_blocked_even_with_reviews_and_human_approval():
    decision = evaluate_agent_review_orchestration(
        _work(action="PLACE_ORDER"),
        _all_reviews(),
        human_approved=True,
        approved_by="ram",
    )

    assert decision.state == AgentOrchestrationState.BLOCKED.value
    assert decision.accepted is False
    assert "ACTION_FORBIDDEN" in decision.blockers
    assert decision.allowed_for_patch is False
    assert decision.allowed_for_live_execution is False


def test_duplicate_stage_uses_latest_review():
    reviews = [
        _review("GRILL_ME", decision="REJECT", summary="Old reject"),
        _review("GRILL_ME", decision="APPROVE", summary="Updated approval"),
        _review("HERMES"),
        _review("GSD", decision="READY"),
    ]
    decision = evaluate_agent_review_orchestration(_work(), reviews)

    assert decision.state == AgentOrchestrationState.APPROVED_FOR_PATCH.value
    assert decision.accepted is True
    assert decision.completed_stages == ("GRILL_ME", "HERMES", "GSD")


def test_to_dict_is_json_friendly():
    payload = evaluate_agent_review_orchestration(_work(), _all_reviews()).to_dict()

    assert payload["schema_version"] == 1
    assert payload["metadata"]["contract"] == "agent_orchestrator_v1"
    assert isinstance(payload["reviews"], list)
    assert isinstance(payload["blockers"], list)
    json.dumps(payload, sort_keys=True)
