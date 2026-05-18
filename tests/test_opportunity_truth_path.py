from __future__ import annotations

from core.opportunity_truth_path import assess_opportunity_truth_path
from core.ranking_orchestrator import PIPELINE_STAGE_ORDER


def _ranked_report(**overrides):
    payload = {
        "schema_version": 1,
        "symbol": "NIFTY",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "pipeline_stage_order": list(PIPELINE_STAGE_ORDER),
        "ranked_candidate_count": 2,
        "top_rank_strategy_id": "call_high",
        "metadata": {
            "orchestrator": "ranked_opportunity_pipeline_v1",
            "scope": "read_only_no_execution_no_dashboard_no_live_wiring",
        },
    }
    payload.update(overrides)
    return payload


def _execution_decision(**overrides):
    payload = {
        "schema_version": 1,
        "strategy_id": "call_high",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "execution_grade": True,
        "allowed_for_execution": True,
        "allowed_for_paper_execution": True,
        "advisory_only": False,
        "state": "EXECUTION_GRADE",
        "blockers": [],
        "warnings": [],
        "reasons": [],
        "is_order_action": False,
        "append": False,
    }
    payload.update(overrides)
    return payload


def test_canonical_ranked_pipeline_with_execution_firewall_pass_is_paper_intent_eligible():
    decision = assess_opportunity_truth_path(
        _ranked_report(),
        execution_grade_decision=_execution_decision(),
    )

    assert decision.state == "PAPER_INTENT_ELIGIBLE"
    assert decision.canonical is True
    assert decision.truth_path == "ranked_pipeline_to_execution_firewall"
    assert decision.allowed_for_paper_intent is True
    assert decision.allowed_for_live_execution is False
    assert decision.advisory_only is False
    assert decision.blockers == ()
    assert decision.is_order_action is False
    assert decision.append is False


def test_missing_ranked_report_blocks_fail_closed():
    decision = assess_opportunity_truth_path(None, execution_grade_decision=_execution_decision())

    assert decision.state == "BLOCKED"
    assert decision.allowed_for_paper_intent is False
    assert decision.canonical is False
    assert "RANKED_PIPELINE_REPORT_MISSING" in decision.blockers


def test_missing_execution_firewall_decision_blocks_even_for_canonical_report():
    decision = assess_opportunity_truth_path(_ranked_report(), execution_grade_decision=None)

    assert decision.state == "BLOCKED"
    assert decision.allowed_for_paper_intent is False
    assert "EXECUTION_GRADE_DECISION_MISSING" in decision.blockers


def test_failing_execution_firewall_blocks_paper_intent():
    decision = assess_opportunity_truth_path(
        _ranked_report(),
        execution_grade_decision=_execution_decision(
            execution_grade=False,
            allowed_for_paper_execution=False,
            advisory_only=True,
            blockers=["FALLBACK_QUOTE_ONLY"],
        ),
    )

    assert decision.state == "BLOCKED"
    assert decision.allowed_for_paper_intent is False
    assert "FALLBACK_QUOTE_ONLY" in decision.blockers
    assert "EXECUTION_GRADE_FALSE" in decision.blockers
    assert "PAPER_EXECUTION_NOT_ALLOWED" in decision.blockers
    assert "EXECUTION_FIREWALL_ADVISORY_ONLY" in decision.blockers


def test_legacy_source_is_advisory_only_even_with_valid_report_and_firewall():
    decision = assess_opportunity_truth_path(
        _ranked_report(),
        source_name="legacy_final_decision",
        execution_grade_decision=_execution_decision(),
    )

    assert decision.state == "ADVISORY_ONLY"
    assert decision.allowed_for_paper_intent is False
    assert decision.advisory_only is True
    assert "LEGACY_OPPORTUNITY_SOURCE" in decision.blockers
    assert "LEGACY_SOURCE_CONTAINED_AS_ADVISORY_ONLY" in decision.warnings


def test_non_canonical_orchestrator_blocks():
    decision = assess_opportunity_truth_path(
        _ranked_report(metadata={"orchestrator": "legacy_opportunity_engine"}),
        execution_grade_decision=_execution_decision(),
    )

    assert decision.allowed_for_paper_intent is False
    assert "NON_CANONICAL_OPPORTUNITY_SOURCE" in decision.blockers


def test_ranked_pipeline_order_action_blocks():
    decision = assess_opportunity_truth_path(
        _ranked_report(is_order_action=True),
        execution_grade_decision=_execution_decision(),
    )

    assert decision.allowed_for_paper_intent is False
    assert "RANKED_PIPELINE_CONTAINS_ORDER_ACTION" in decision.blockers


def test_ranked_pipeline_append_true_blocks():
    decision = assess_opportunity_truth_path(
        _ranked_report(append=True),
        execution_grade_decision=_execution_decision(),
    )

    assert decision.allowed_for_paper_intent is False
    assert "RANKED_PIPELINE_APPEND_TRUE" in decision.blockers


def test_invalid_stage_order_blocks():
    decision = assess_opportunity_truth_path(
        _ranked_report(pipeline_stage_order=["candidate_pool", "candidate_ranking"]),
        execution_grade_decision=_execution_decision(),
    )

    assert decision.allowed_for_paper_intent is False
    assert "RANKED_PIPELINE_STAGE_ORDER_INVALID" in decision.blockers
    assert decision.observed_stage_order == ("candidate_pool", "candidate_ranking")


def test_no_ranked_candidates_blocks():
    decision = assess_opportunity_truth_path(
        _ranked_report(ranked_candidate_count=0, top_rank_strategy_id=None),
        execution_grade_decision=_execution_decision(),
    )

    assert decision.allowed_for_paper_intent is False
    assert "NO_RANKED_CANDIDATES" in decision.blockers
    assert "TOP_RANK_MISSING" in decision.blockers


def test_to_dict_is_json_friendly_and_stable():
    decision = assess_opportunity_truth_path(
        _ranked_report(),
        execution_grade_decision=_execution_decision(),
    )
    payload = decision.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == "PAPER_INTENT_ELIGIBLE"
    assert payload["allowed_for_paper_intent"] is True
    assert payload["allowed_for_live_execution"] is False
    assert payload["blockers"] == []
    assert payload["required_stage_order"] == list(PIPELINE_STAGE_ORDER)
    assert payload["observed_stage_order"] == list(PIPELINE_STAGE_ORDER)
    assert payload["is_order_action"] is False
    assert payload["append"] is False
