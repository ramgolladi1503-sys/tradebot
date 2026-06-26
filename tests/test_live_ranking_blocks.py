import pytest
from core.candidate_ranking import rank_candidates
from core.opportunity_scoring import OpportunityScoreRecord, OpportunityScoreBreakdown

def _dummy_breakdown():
    return OpportunityScoreBreakdown(
        component_scores={},
        component_weights={},
        weighted_component_scores={},
        base_score=0.9,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=0.9
    )

def test_feed_risk_blocked_from_top_opportunities():
    records = [
        OpportunityScoreRecord(
            strategy_id="S1",
            symbol="NIFTY",
            direction="UP",
            movement_type="TREND",
            final_score=0.9,
            bucket="EXECUTABLE_CANDIDATE",
            score_eligibility="SCORE_ELIGIBLE",
            executable_candidate=True,
            score_explanation="",
            safety_flags=("fallback",),
            downgrade_reasons=(),
            blockers=(),
            warnings=(),
            breakdown=_dummy_breakdown()
        ),
        OpportunityScoreRecord(
            strategy_id="S2",
            symbol="BANKNIFTY",
            direction="DOWN",
            movement_type="TREND",
            final_score=0.85,
            bucket="EXECUTABLE_CANDIDATE",
            score_eligibility="SCORE_ELIGIBLE",
            executable_candidate=True,
            score_explanation="",
            safety_flags=(),
            downgrade_reasons=(),
            blockers=(),
            warnings=(),
            breakdown=_dummy_breakdown()
        ),
        OpportunityScoreRecord(
            strategy_id="S3",
            symbol="SENSEX",
            direction="UP",
            movement_type="TREND",
            final_score=0.95,
            bucket="EXECUTABLE_CANDIDATE",
            score_eligibility="SCORE_ELIGIBLE",
            executable_candidate=True,
            score_explanation="",
            safety_flags=(),
            downgrade_reasons=("stale_feed",),
            blockers=(),
            warnings=(),
            breakdown=_dummy_breakdown()
        )
    ]
    report = rank_candidates(records)
    
    clean = next((r for r in report.ranks if r.strategy_id == "S2"), None)
    assert clean is not None
    assert clean.executable_candidate is True
    
    fallback = next((r for r in report.ranks if r.strategy_id == "S1"), None)
    assert fallback is not None
    assert fallback.executable_candidate is False
    assert fallback.bucket == "SUPPRESSED_CANDIDATE"
    assert "ranking_feed_risk" in fallback.safety_flags
    
    stale = next((r for r in report.ranks if r.strategy_id == "S3"), None)
    assert stale is not None
    assert stale.executable_candidate is False
    assert stale.bucket == "SUPPRESSED_CANDIDATE"
    assert "ranking_feed_risk_suppression" in stale.downgrade_reasons

def test_no_fake_best_trade_when_all_stale():
    records = [
        OpportunityScoreRecord(
            strategy_id="S1",
            symbol="NIFTY",
            direction="UP",
            movement_type="TREND",
            final_score=0.9,
            bucket="EXECUTABLE_CANDIDATE",
            score_eligibility="SCORE_ELIGIBLE",
            executable_candidate=True,
            score_explanation="",
            safety_flags=("fallback",),
            downgrade_reasons=(),
            blockers=(),
            warnings=(),
            breakdown=_dummy_breakdown()
        )
    ]
    report = rank_candidates(records)
    
    assert not any(c.executable_candidate for c in report.ranks)
    assert "ranking_feed_risk" in report.ranks[0].safety_flags
