"""Probability semantics for UI labels."""

from core.candidate_outcome_contract import CandidateOutcomeContract


def get_probability_label(candidate: CandidateOutcomeContract) -> str:
    """
    Get the UI label for a candidate's probability/confidence.
    
    Rules:
    - If fallback/advisory/stale: no executable probability is shown.
    - If prediction_event + horizon + calibration_source exist: Target-hit probability: X% within Y min.
    - If lacks horizon/event/calibration: Setup score: X/100.
    """
    
    if candidate.is_fallback or candidate.is_advisory or candidate.is_stale:
        return "No executable probability (fallback/advisory/stale)"
        
    if (
        candidate.prediction_event is not None
        and candidate.prediction_horizon_minutes is not None
        and candidate.calibration_source is not None
        and candidate.probability_target_before_stop is not None
    ):
        prob_pct = round(candidate.probability_target_before_stop * 100, 1)
        return f"Target-hit probability: {prob_pct}% within {candidate.prediction_horizon_minutes} min"
        
    # Heuristic fallback
    score = round(candidate.confidence_score, 1)
    return f"Setup score: {score}/100"
