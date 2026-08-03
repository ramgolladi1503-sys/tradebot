import pytest

from core.ai_reliability_agent.analytics import (
    analyze_candidates,
    build_candidate_autopsy,
    classify_decision_outcome,
    classify_rejection,
    derive_session_verdict,
    group_candidate_rows,
    normalize_outcome,
    observed_contributors,
    pipeline_funnel,
    rejection_breakdown,
)
from core.ai_reliability_agent.contracts import (
    DecisionOutcomeClass,
    FailureFactor,
    OutcomeKind,
    RejectionVerdict,
    SessionVerdict,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("target", OutcomeKind.TARGET),
        ("target_hit", OutcomeKind.TARGET),
        ("win", OutcomeKind.TARGET),
        ("stop", OutcomeKind.STOP),
        ("stop_hit", OutcomeKind.STOP),
        ("sl", OutcomeKind.STOP),
        ("loss", OutcomeKind.STOP),
        ("time_exit", OutcomeKind.TIME_EXIT),
        ("eod", OutcomeKind.TIME_EXIT),
        ("manual_exit", OutcomeKind.MANUAL_EXIT),
        ("no_hit", OutcomeKind.NO_HIT),
        ("blocked", OutcomeKind.NOT_EXECUTED),
        ("advisory_only", OutcomeKind.NOT_EXECUTED),
        ("something", OutcomeKind.UNKNOWN),
    ],
)
def test_normalize_outcome(raw, expected):
    assert normalize_outcome({"outcome": raw}) == expected


@pytest.mark.parametrize(
    "decision_valid,outcome,expected",
    [
        (True, OutcomeKind.TARGET, DecisionOutcomeClass.GOOD_DECISION_GOOD_OUTCOME),
        (True, OutcomeKind.STOP, DecisionOutcomeClass.GOOD_DECISION_BAD_OUTCOME),
        (False, OutcomeKind.TARGET, DecisionOutcomeClass.BAD_DECISION_GOOD_OUTCOME),
        (False, OutcomeKind.STOP, DecisionOutcomeClass.BAD_DECISION_BAD_OUTCOME),
        (None, OutcomeKind.TARGET, DecisionOutcomeClass.UNVERIFIABLE),
        (True, OutcomeKind.NO_HIT, DecisionOutcomeClass.UNVERIFIABLE),
    ],
)
def test_classify_decision_outcome(decision_valid, outcome, expected):
    assert classify_decision_outcome(decision_valid=decision_valid, outcome=outcome) == expected


@pytest.mark.parametrize(
    "row,outcome,expected",
    [
        ({"block_reason": "spread", "counterfactual_net_positive": True}, OutcomeKind.TARGET, RejectionVerdict.MISSED_OPPORTUNITY),
        ({"block_reason": "spread", "counterfactual_executable": False}, OutcomeKind.TARGET, RejectionVerdict.CORRECT_REJECTION),
        ({"block_reason": "spread"}, OutcomeKind.TARGET, RejectionVerdict.UNVERIFIABLE),
        ({"block_reason": "spread"}, OutcomeKind.STOP, RejectionVerdict.CORRECT_REJECTION),
        ({"block_reason": "spread"}, OutcomeKind.NO_HIT, RejectionVerdict.NEUTRAL_REJECTION),
        ({}, OutcomeKind.TARGET, RejectionVerdict.INVALID_REJECTION),
        ({"block_reason": "spread"}, OutcomeKind.UNKNOWN, RejectionVerdict.UNVERIFIABLE),
    ],
)
def test_classify_rejection(row, outcome, expected):
    assert classify_rejection(row, outcome) == expected


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"session_data_valid": False, "emitted_untrustworthy": 0, "unexplained_disappearances": 0, "observability_gaps": 0, "materially_missed_candidates": 0}, SessionVerdict.LIVE_SESSION_INVALID),
        ({"session_data_valid": True, "emitted_untrustworthy": 1, "unexplained_disappearances": 0, "observability_gaps": 0, "materially_missed_candidates": 0}, SessionVerdict.PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES),
        ({"session_data_valid": True, "emitted_untrustworthy": 0, "unexplained_disappearances": 0, "observability_gaps": 0, "materially_missed_candidates": 1}, SessionVerdict.PIPELINE_SUPPRESSED_VALID_CANDIDATES),
        ({"session_data_valid": True, "emitted_untrustworthy": 0, "unexplained_disappearances": 1, "observability_gaps": 0, "materially_missed_candidates": 0}, SessionVerdict.PIPELINE_OPERATIONAL_BUT_OBSERVABILITY_INCOMPLETE),
        ({"session_data_valid": True, "emitted_untrustworthy": 0, "unexplained_disappearances": 0, "observability_gaps": 0, "materially_missed_candidates": 0}, SessionVerdict.PIPELINE_TRUTHFUL_AND_OPERATIONAL),
    ],
)
def test_derive_session_verdict(kwargs, expected):
    assert derive_session_verdict(**kwargs) == expected


def test_group_candidate_rows_orders_by_time():
    grouped = group_candidate_rows([
        {"candidate_id": "C", "ts_epoch": 2},
        {"candidate_id": "C", "ts_epoch": 1},
    ])
    assert [row["ts_epoch"] for row in grouped["C"]] == [1, 2]


def test_pipeline_funnel_counts_flags():
    result = pipeline_funnel([
        {"stage": "phase1", "stage_status": "passed", "displayable": True, "rankable": True},
        {"stage": "phase2", "stage_status": "blocked", "executable": False},
    ])
    assert result["stage:phase1"] == 1
    assert result["status:blocked"] == 1
    assert result["displayable"] == 1


def test_rejection_breakdown_prioritizes_reason_code():
    result = rejection_breakdown([
        {"stage_status": "blocked", "block_reason": "text", "block_reason_code": "CODE"},
        {"status": "rejected", "reject_reason": "OTHER"},
    ])
    assert result == {"CODE": 1, "OTHER": 1}


@pytest.mark.parametrize(
    "entry,final,outcome,factor",
    [
        ({"fallback_used": True}, {}, OutcomeKind.STOP, FailureFactor.DATA_QUALITY_FAILURE),
        ({"breadth": 0.8}, {"breadth": 0.5}, OutcomeKind.STOP, FailureFactor.PARTICIPATION_COLLAPSE),
        ({"spread_pct": 1.0}, {"spread_pct": 1.6}, OutcomeKind.STOP, FailureFactor.LIQUIDITY_DETERIORATION),
        ({"entry_extension_atr": 1.8}, {}, OutcomeKind.STOP, FailureFactor.LATE_ENTRY),
        ({"regime": "TREND"}, {"regime": "RANGE"}, OutcomeKind.STOP, FailureFactor.REGIME_TRANSITION),
        ({}, {"breakout_held": False}, OutcomeKind.STOP, FailureFactor.THESIS_INVALIDATED),
        ({"direction": "BUY_CALL"}, {"iv_change": -0.1, "underlying_move": 2, "option_move": -1}, OutcomeKind.STOP, FailureFactor.IV_CONTRACTION),
        ({"initial_risk": 10, "slippage": 6}, {}, OutcomeKind.STOP, FailureFactor.EXCESSIVE_SLIPPAGE),
    ],
)
def test_observed_contributor_detection(entry, final, outcome, factor):
    assert factor in {item.factor for item in observed_contributors(entry, final, outcome)}


def test_stop_without_evidence_is_normal_variance_hypothesis():
    contributors = observed_contributors({}, {}, OutcomeKind.STOP)
    assert contributors[0].factor == FailureFactor.NORMAL_VARIANCE


def test_target_without_evidence_reports_insufficient_evidence():
    contributors = observed_contributors({}, {}, OutcomeKind.TARGET)
    assert contributors[0].factor == FailureFactor.INSUFFICIENT_EVIDENCE


def test_approved_fallback_target_is_bad_decision_good_outcome():
    autopsy = build_candidate_autopsy("C", [
        {"candidate_id": "C", "stage": "selected", "stage_status": "selected", "fallback_used": True},
        {"candidate_id": "C", "stage": "closed", "outcome": "target"},
    ])
    assert autopsy.approved is True
    assert autopsy.decision_outcome_class == DecisionOutcomeClass.BAD_DECISION_GOOD_OUTCOME


def test_rejected_stop_is_correct_rejection():
    autopsy = build_candidate_autopsy("C", [
        {"candidate_id": "C", "stage": "phase2", "stage_status": "blocked", "block_reason": "spread"},
        {"candidate_id": "C", "stage": "shadow_outcome", "outcome": "stop"},
    ])
    assert autopsy.approved is False
    assert autopsy.rejection_verdict == RejectionVerdict.CORRECT_REJECTION


def test_analyze_candidates_keeps_actual_and_counterfactual_separate():
    report = analyze_candidates([
        {"candidate_id": "A", "stage_status": "selected", "stage": "selected", "execution_ok": True},
        {"candidate_id": "A", "stage": "closed", "outcome": "target"},
        {"candidate_id": "B", "stage_status": "blocked", "stage": "phase2", "block_reason": "spread"},
        {"candidate_id": "B", "stage": "shadow_outcome", "outcome": "stop"},
    ])
    assert report["candidate_count"] == 2
    assert report["outcomes"]["TARGET"] == 1
    assert report["rejection_verdicts"]["CORRECT_REJECTION"] == 1


def test_actual_outcome_scope_for_executed_trade_row():
    autopsy = build_candidate_autopsy("C", [
        {"candidate_id": "C", "stage_status": "selected", "execution_ok": True, "spread_pct": 0.2},
        {"candidate_id": "C", "stage": "trade_log", "stage_status": "closed", "evidence_source": "trade_log", "outcome": "target"},
    ])
    assert autopsy.outcome_scope.value == "ACTUAL"


def test_unknown_outcome_scope_is_unresolved():
    autopsy = build_candidate_autopsy("C", [{"candidate_id": "C", "stage": "generated"}])
    assert autopsy.outcome_scope.value == "UNRESOLVED"


def test_rejected_target_without_execution_evidence_is_not_called_missed_opportunity():
    autopsy = build_candidate_autopsy("C", [
        {"candidate_id": "C", "stage_status": "blocked", "block_reason": "WIDE_SPREAD"},
        {"candidate_id": "C", "outcome": "target"},
    ])
    assert autopsy.rejection_verdict.value == "UNVERIFIABLE"


def test_rejected_target_with_non_executable_counterfactual_is_correct_rejection():
    autopsy = build_candidate_autopsy("C", [
        {"candidate_id": "C", "stage_status": "blocked", "block_reason": "WIDE_SPREAD"},
        {"candidate_id": "C", "outcome": "target", "counterfactual_executable": False},
    ])
    assert autopsy.rejection_verdict.value == "CORRECT_REJECTION"


def test_put_direction_iv_attribution_requires_downward_underlying_move():
    wrong_direction = observed_contributors(
        {"option_type": "PE"},
        {"underlying_move": 20, "option_move": -2, "iv_change": -0.05},
        OutcomeKind.STOP,
    )
    right_direction = observed_contributors(
        {"option_type": "PE"},
        {"underlying_move": -20, "option_move": -2, "iv_change": -0.05},
        OutcomeKind.STOP,
    )
    assert "IV_CONTRACTION" not in {item.factor.value for item in wrong_direction}
    assert "IV_CONTRACTION" in {item.factor.value for item in right_direction}
