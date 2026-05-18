from __future__ import annotations

from core.selection_policy import (
    ADVISORY_ONLY,
    BLOCKED,
    NO_TRADE,
    SELECTED_FOR_PAPER,
    WAIT,
    build_selection_policy_report,
)


def _rank(**overrides):
    payload = {
        "rank": 1,
        "strategy_id": "call_high",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "final_score": 0.82,
        "bucket": "EXECUTABLE_CANDIDATE",
        "score_eligibility": "SCORE_ELIGIBLE",
        "executable_candidate": True,
        "blockers": [],
        "warnings": [],
        "directional_warnings": [],
    }
    payload.update(overrides)
    return payload


def _report(*ranks, **overrides):
    payload = {
        "schema_version": 1,
        "symbol": "NIFTY",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "ranking": {"ranks": list(ranks or [_rank()])},
        "metadata": {"orchestrator": "ranked_opportunity_pipeline_v1"},
    }
    payload.update(overrides)
    return payload


def _truth(**overrides):
    payload = {
        "schema_version": 1,
        "state": "PAPER_INTENT_ELIGIBLE",
        "allowed_for_paper_intent": True,
        "allowed_for_live_execution": False,
        "advisory_only": False,
        "blockers": [],
        "warnings": [],
        "is_order_action": False,
        "append": False,
    }
    payload.update(overrides)
    return payload


def test_top_execution_grade_rank_is_selected_for_paper():
    report = build_selection_policy_report(_report(), truth_path_decision=_truth(), max_selected=1)

    assert report.state == SELECTED_FOR_PAPER
    assert report.selected_count == 1
    assert report.selected_strategy_ids == ("call_high",)
    assert report.is_order_action is False
    assert report.append is False
    record = report.selections[0]
    assert record.decision == SELECTED_FOR_PAPER
    assert record.selected is True
    assert record.blockers == ()


def test_selection_respects_max_selected_capacity():
    report = build_selection_policy_report(
        _report(
            _rank(rank=1, strategy_id="call_high", final_score=0.82),
            _rank(rank=2, strategy_id="put_high", direction="BUY_PUT", final_score=0.81),
        ),
        truth_path_decision=_truth(),
        max_selected=1,
    )

    assert report.state == SELECTED_FOR_PAPER
    assert report.selected_strategy_ids == ("call_high",)
    assert report.selections[0].decision == SELECTED_FOR_PAPER
    assert report.selections[1].decision == WAIT
    assert "selection_capacity_already_used" in report.selections[1].reasons


def test_below_min_final_score_waits():
    report = build_selection_policy_report(
        _report(_rank(final_score=0.55)),
        truth_path_decision=_truth(),
        min_final_score=0.7,
    )

    assert report.state == WAIT
    assert report.selected_count == 0
    assert report.selections[0].decision == WAIT
    assert "ranked_candidate_below_min_final_score" in report.selections[0].reasons


def test_near_executable_candidate_waits_for_confirmation():
    report = build_selection_policy_report(
        _report(_rank(bucket="NEAR_EXECUTABLE_CANDIDATE", score_eligibility="NEEDS_CONFIRMATION")),
        truth_path_decision=_truth(),
    )

    assert report.state == WAIT
    assert report.selections[0].decision == WAIT
    assert "ranked_candidate_needs_confirmation" in report.selections[0].reasons


def test_advisory_rank_stays_advisory_only():
    report = build_selection_policy_report(
        _report(_rank(bucket="ADVISORY_CANDIDATE", score_eligibility="ADVISORY_ONLY", executable_candidate=False)),
        truth_path_decision=_truth(),
    )

    assert report.state == ADVISORY_ONLY
    assert report.selected_count == 0
    assert report.selections[0].decision == ADVISORY_ONLY


def test_no_trade_rank_stays_no_trade():
    report = build_selection_policy_report(
        _report(_rank(direction="NO_TRADE", bucket="NO_TRADE_CANDIDATE", score_eligibility="NO_TRADE_ONLY", executable_candidate=False)),
        truth_path_decision=_truth(),
    )

    assert report.state == NO_TRADE
    assert report.selected_count == 0
    assert report.selections[0].decision == NO_TRADE


def test_suppressed_or_blocked_rank_is_blocked():
    report = build_selection_policy_report(
        _report(
            _rank(
                bucket="SUPPRESSED_CANDIDATE",
                score_eligibility="SUPPRESSED_BY_DOWNGRADE",
                executable_candidate=False,
                blockers=["WIDE_SPREAD"],
            )
        ),
        truth_path_decision=_truth(),
    )

    assert report.state == BLOCKED
    assert report.selected_count == 0
    assert report.selections[0].decision == BLOCKED
    assert "WIDE_SPREAD" in report.selections[0].blockers


def test_missing_truth_path_blocks_global_selection():
    report = build_selection_policy_report(_report(), truth_path_decision=None)

    assert report.state == BLOCKED
    assert report.selected_count == 0
    assert "TRUTH_PATH_DECISION_MISSING" in report.blockers
    assert report.selections[0].decision == BLOCKED
    assert "TRUTH_PATH_DECISION_MISSING" in report.selections[0].blockers


def test_truth_path_not_eligible_blocks_global_selection():
    report = build_selection_policy_report(
        _report(),
        truth_path_decision=_truth(allowed_for_paper_intent=False, blockers=["EXECUTION_GRADE_FALSE"]),
    )

    assert report.state == BLOCKED
    assert "EXECUTION_GRADE_FALSE" in report.blockers
    assert "TRUTH_PATH_NOT_PAPER_INTENT_ELIGIBLE" in report.blockers
    assert report.selections[0].decision == BLOCKED


def test_ranked_report_order_action_blocks_global_selection():
    report = build_selection_policy_report(_report(is_order_action=True), truth_path_decision=_truth())

    assert report.state == BLOCKED
    assert "RANKED_REPORT_CONTAINS_ORDER_ACTION" in report.blockers
    assert report.selections[0].decision == BLOCKED


def test_empty_ranked_report_blocks():
    report = build_selection_policy_report(_report(ranking={"ranks": []}), truth_path_decision=_truth())

    assert report.state == BLOCKED
    assert report.candidate_count == 0
    assert "NO_RANKED_CANDIDATES" in report.blockers


def test_to_dict_is_json_friendly_and_stable():
    report = build_selection_policy_report(_report(), truth_path_decision=_truth())
    payload = report.to_dict()

    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["state"] == SELECTED_FOR_PAPER
    assert payload["selected_strategy_ids"] == ["call_high"]
    assert payload["selections"][0]["decision"] == SELECTED_FOR_PAPER
    assert payload["metadata"]["selector"] == "selection_policy_v1"
