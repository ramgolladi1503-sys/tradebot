import pytest

from core.strategy_regime_policy import evaluate_strategy_regime_policy
from core.candidate_ranking import (
    CandidateRankRecord,
    CandidateRankingReport,
    rank_candidates,
    is_feed_risk_candidate,
)
from core.opportunity_scoring import (
    OpportunityScoreRecord,
    OpportunityScoreBreakdown,
)

def test_orb_high_entropy_volatility_expansion():
    """1. Test ORB: OPEN_DISCOVERY + high entropy + volatility expansion -> ELIGIBLE_WITH_PENALTY."""
    orb_decision = evaluate_strategy_regime_policy(
        strategy="ORB",
        session_bucket="OPEN_DISCOVERY",
        entropy_value=0.8,
        normalized_entropy=0.8,
        entropy_state="HIGH",
        volatility_expansion=True
    )
    assert orb_decision is not None
    assert orb_decision["policy_result"] == "ELIGIBLE_WITH_PENALTY"

def test_mean_reversion_high_entropy():
    """2. Test Mean Reversion: high entropy + volatility expansion -> BLOCKED or ADVISORY_ONLY."""
    mr_decision = evaluate_strategy_regime_policy(
        strategy="MEAN_REVERSION",
        trend_state="TREND_EXPANSION",
        entropy_value=0.85,
        normalized_entropy=0.85,
        entropy_state="HIGH",
        session_bucket="MIDDAY",
    )
    assert mr_decision is not None
    assert mr_decision["policy_result"] in {"BLOCKED", "ADVISORY_ONLY"}

def test_short_premium_high_entropy():
    """3. Test Short Premium: high entropy -> BLOCKED."""
    sp_decision = evaluate_strategy_regime_policy(
        strategy="SHORT_STRADDLE",
        trend_state="ANY",
        entropy_value=0.9,
        normalized_entropy=0.9,
        entropy_state="HIGH",
        session_bucket="LATE_DAY",
    )
    assert sp_decision is not None
    assert sp_decision["policy_result"] == "BLOCKED"

def test_unknown_strategy_high_entropy():
    """4. Test Unknown Strategy: high entropy -> conservative non-executable behavior."""
    unk_decision = evaluate_strategy_regime_policy(
        strategy="UNKNOWN_BETA",
        trend_state="RANGE_BOUND",
        entropy_value=0.75,
        normalized_entropy=0.75,
        entropy_state="HIGH",
        session_bucket="MIDDAY",
    )
    assert unk_decision is not None
    assert unk_decision["policy_result"] in {"ADVISORY_ONLY", "BLOCKED"}

def test_mean_reversion_normal_entropy():
    """6. Test Mean Reversion (Normal): Normal entropy + range regime -> ELIGIBLE."""
    mr_decision = evaluate_strategy_regime_policy(
        strategy="MEAN_REVERSION",
        trend_state="RANGE",
        entropy_value=0.2,
        normalized_entropy=0.2,
        entropy_state="LOW",
        session_bucket="MIDDAY",
    )
    assert mr_decision is not None
    assert mr_decision["policy_result"] == "ELIGIBLE"

def test_invariant_fallback_advisory_never_executable():
    """5. Test Invariant: Any fallback/advisory candidate -> cannot become EXECUTABLE."""
    from core.opportunity_scoring import OpportunityScoreRecord, OpportunityScoreBreakdown, SUPPRESSED_BY_DOWNGRADE
    
    breakdown = OpportunityScoreBreakdown(
        component_scores={}, component_weights={}, weighted_component_scores={},
        base_score=0.0, penalties={}, total_penalty=0.0, bucket_cap=1.0, trap_risk_penalty=0.0, final_score=0.9
    )
    osr = OpportunityScoreRecord(
        strategy_id="TEST",
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="OPENING_DRIVE",
        bucket="ADVISORY_CANDIDATE",
        score_eligibility="ADVISORY_ONLY",
        final_score=0.9,
        executable_candidate=False,
        score_explanation="",
        downgrade_reasons=("fallback_data",),
        safety_flags=("fallback_data",),
        blockers=(),
        warnings=(),
        breakdown=breakdown,
    )
    
    ranks = rank_candidates([osr])
    r = ranks.ranks[0]
    assert r.bucket != "EXECUTABLE_CANDIDATE"
    assert r.score_eligibility != "SCORE_ELIGIBLE"
    assert r.executable_candidate is False
    assert is_feed_risk_candidate(osr).is_risk is True
