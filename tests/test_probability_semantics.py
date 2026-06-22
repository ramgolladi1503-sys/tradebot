import pytest
from core.candidate_outcome_contract import CandidateOutcomeContract
from core.probability_semantics import get_probability_label


def test_fallback_candidate_cannot_display_probability():
    candidate = CandidateOutcomeContract(
        candidate_id="123",
        strategy_name="test",
        created_at="2026-01-01T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=True,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=85.5,
    )
    
    label = get_probability_label(candidate)
    assert "No executable probability" in label


def test_heuristic_confidence_displays_setup_score():
    candidate = CandidateOutcomeContract(
        candidate_id="123",
        strategy_name="test",
        created_at="2026-01-01T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=85.5,
    )
    
    label = get_probability_label(candidate)
    assert label == "Setup score: 85.5/100"


def test_candidate_without_horizon_cannot_display_probability():
    candidate = CandidateOutcomeContract(
        candidate_id="123",
        strategy_name="test",
        created_at="2026-01-01T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=85.5,
        prediction_event="TARGET_BEFORE_STOP",
        calibration_source="historical_v1",
        probability_target_before_stop=0.75
        # Missing horizon
    )
    
    label = get_probability_label(candidate)
    assert label == "Setup score: 85.5/100"


def test_calibrated_candidate_displays_target_hit_probability():
    candidate = CandidateOutcomeContract(
        candidate_id="123",
        strategy_name="test",
        created_at="2026-01-01T00:00:00Z",
        entry_price=100.0,
        candidate_status="PENDING",
        execution_ok=True,
        is_fallback=False,
        is_advisory=False,
        is_stale=False,
        is_recovered=False,
        confidence_score=85.5,
        prediction_event="TARGET_BEFORE_STOP",
        prediction_horizon_minutes=30,
        calibration_source="historical_v1",
        probability_target_before_stop=0.75
    )
    
    label = get_probability_label(candidate)
    assert label == "Target-hit probability: 75.0% within 30 min"
