import pytest
from core.opportunity_ranking import CandidateOpportunity, rank_opportunities

def test_fallback_quote_forces_advisory_only():
    candidate = CandidateOpportunity(
        symbol="NIFTY",
        strategy_id="OPENING_DRIVE",
        edge_evidence_score=1.0,
        regime_compatibility_score=1.0,
        liquidity_spread_score=1.0,
        quote_freshness_ms=500,
        cost_hurdle_passed=True,
        truth_quality_score=1.0,
        is_fallback_or_recovered_quote=True  # Should force advisory_only = True
    )
    
    assert candidate.advisory_only is True
    
def test_normal_quote_is_not_advisory_only():
    candidate = CandidateOpportunity(
        symbol="BANKNIFTY",
        strategy_id="OPENING_DRIVE",
        edge_evidence_score=1.0,
        regime_compatibility_score=1.0,
        liquidity_spread_score=1.0,
        quote_freshness_ms=500,
        cost_hurdle_passed=True,
        truth_quality_score=1.0,
        is_fallback_or_recovered_quote=False
    )
    
    assert candidate.advisory_only is False

def test_rank_opportunities_output_shape():
    c1 = CandidateOpportunity(
        symbol="NIFTY",
        strategy_id="OPENING_DRIVE",
        edge_evidence_score=0.9,
        regime_compatibility_score=0.8,
        liquidity_spread_score=0.9,
        quote_freshness_ms=200,
        cost_hurdle_passed=True,
        truth_quality_score=1.0,
        is_fallback_or_recovered_quote=False
    )
    c2 = CandidateOpportunity(
        symbol="BANKNIFTY",
        strategy_id="OPENING_DRIVE",
        edge_evidence_score=0.9,
        regime_compatibility_score=0.8,
        liquidity_spread_score=0.9,
        quote_freshness_ms=200,
        cost_hurdle_passed=True,
        truth_quality_score=1.0,
        is_fallback_or_recovered_quote=True # Fallback
    )
    c3 = CandidateOpportunity(
        symbol="RELIANCE",
        strategy_id="OPENING_DRIVE",
        edge_evidence_score=0.5,
        regime_compatibility_score=0.5,
        liquidity_spread_score=0.5,
        quote_freshness_ms=200,
        cost_hurdle_passed=False, # Fails cost hurdle
        truth_quality_score=0.5,
        is_fallback_or_recovered_quote=False
    )

    result = rank_opportunities([c1, c2, c3])
    
    assert "TOP_OPPORTUNITIES" in result
    assert "ALL_CANDIDATES_DEBUG" in result
    
    # c3 failed cost hurdle, so rank is 0, shouldn't be in top opportunities
    assert len(result["TOP_OPPORTUNITIES"]) == 2
    assert len(result["ALL_CANDIDATES_DEBUG"]) == 3
    
    # c2 must have advisory_only == True in output shape
    banknifty_top = next(x for x in result["TOP_OPPORTUNITIES"] if x["symbol"] == "BANKNIFTY")
    assert banknifty_top["advisory_only"] is True

    nifty_top = next(x for x in result["TOP_OPPORTUNITIES"] if x["symbol"] == "NIFTY")
    assert nifty_top["advisory_only"] is False
