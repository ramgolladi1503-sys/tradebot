import pytest

from core.candidate_outcome_contract import CandidateOutcomeContract
from core.candidate_ranking import CandidateRankRecord


def test_candidate_without_horizon_displays_setup_score():
    outcome = CandidateOutcomeContract(
        candidate_id="c1",
        strategy_name="s1",
        created_at="2026-06-21T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=0.8,
        prediction_event="TARGET_BEFORE_STOP",
        prediction_horizon_minutes=None,
        calibration_source="backtest",
    )
    record = CandidateRankRecord(
        rank=1,
        strategy_id="s1",
        symbol="AAPL",
        direction="BUY_CALL",
        directional_family="LONG",
        movement_type="OPENING_DRIVE",
        final_score=0.8,
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility="SCORE_ELIGIBLE",
        executable_candidate=True,
        rank_reason="test",
        downgrade_reasons=(),
        blockers=(),
        warnings=(),
        safety_flags=(),
        directional_warnings=(),
        sort_key=(1,),
        outcome_contract=outcome,
    )
    assert record.probability_ui_label == "Setup score"


def test_candidate_with_heuristic_confidence_displays_setup_score():
    outcome = CandidateOutcomeContract(
        candidate_id="c1",
        strategy_name="s1",
        created_at="2026-06-21T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=0.8,
        prediction_event=None,
        prediction_horizon_minutes=None,
        calibration_source=None,
    )
    record = CandidateRankRecord(
        rank=1,
        strategy_id="s1",
        symbol="AAPL",
        direction="BUY_CALL",
        directional_family="LONG",
        movement_type="OPENING_DRIVE",
        final_score=0.8,
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility="SCORE_ELIGIBLE",
        executable_candidate=True,
        rank_reason="test",
        downgrade_reasons=(),
        blockers=(),
        warnings=(),
        safety_flags=(),
        directional_warnings=(),
        sort_key=(1,),
        outcome_contract=outcome,
    )
    assert record.probability_ui_label == "Setup score"


def test_candidate_with_target_stop_horizon_displays_target_hit_probability():
    outcome = CandidateOutcomeContract(
        candidate_id="c1",
        strategy_name="s1",
        created_at="2026-06-21T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=0.8,
        prediction_event="TARGET_BEFORE_STOP",
        prediction_horizon_minutes=30,
        target_price=124.0,
        stop_price=106.0,
        calibration_source="paper",
    )
    record = CandidateRankRecord(
        rank=1,
        strategy_id="s1",
        symbol="AAPL",
        direction="BUY_CALL",
        directional_family="LONG",
        movement_type="OPENING_DRIVE",
        final_score=0.8,
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility="SCORE_ELIGIBLE",
        executable_candidate=True,
        rank_reason="test",
        downgrade_reasons=(),
        blockers=(),
        warnings=(),
        safety_flags=(),
        directional_warnings=(),
        sort_key=(1,),
        outcome_contract=outcome,
    )
    assert record.probability_ui_label == "Target-hit probability within 30 min"


def test_fallback_advisory_stale_candidate_remains_non_executable():
    record = CandidateRankRecord(
        rank=1,
        strategy_id="s1",
        symbol="AAPL",
        direction="BUY_CALL",
        directional_family="LONG",
        movement_type="OPENING_DRIVE",
        final_score=0.8,
        bucket="ADVISORY_CANDIDATE",
        score_eligibility="ADVISORY_ONLY",
        executable_candidate=False,
        rank_reason="test",
        downgrade_reasons=("fallback_quote_data",),
        blockers=(),
        warnings=(),
        safety_flags=("fallback_quote_data",),
        directional_warnings=(),
        sort_key=(1,),
        outcome_contract=None,
    )
    assert not record.executable_candidate


def test_ranking_cannot_convert_confidence_score_into_execution_permission():
    # Even if confidence is high, if the candidate was already downgraded or non-executable,
    # having an outcome contract does not magically make it executable.
    outcome = CandidateOutcomeContract(
        candidate_id="c1",
        strategy_name="s1",
        created_at="2026-06-21T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=0.99,
        prediction_event="TARGET_BEFORE_STOP",
        prediction_horizon_minutes=30,
        calibration_source="live",
    )
    record = CandidateRankRecord(
        rank=1,
        strategy_id="s1",
        symbol="AAPL",
        direction="BUY_CALL",
        directional_family="LONG",
        movement_type="OPENING_DRIVE",
        final_score=0.99,
        bucket="ADVISORY_CANDIDATE",
        score_eligibility="ADVISORY_ONLY",
        executable_candidate=False,
        rank_reason="test",
        downgrade_reasons=(),
        blockers=(),
        warnings=(),
        safety_flags=(),
        directional_warnings=(),
        sort_key=(1,),
        outcome_contract=outcome,
    )
    assert not record.executable_candidate
    assert record.probability_ui_label == "Target-hit probability within 30 min"
