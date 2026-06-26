import pytest
from core.candidate_scoring import score_candidate
from core.candidate_ranking import is_feed_risk_candidate
from core.opportunity_scoring import OpportunityScoreRecord

def test_live_missing_spread_is_blocked():
    candidate = {"trade_id": "T1", "volume": 1000, "oi": 5000, "best_bid": None, "best_ask": None}
    market_data = {"current_ltp": 100.0}
    context = {"trading_mode": "LIVE", "market_open": True}
    res = score_candidate(candidate, market_data, context)
    assert "missing_spread_context_live_block" in res["penalty_reasons"]
    assert res["score_breakdown"]["components"]["spread_score"] == 0.0

def test_live_missing_liquidity_is_blocked():
    candidate = {"trade_id": "T1", "volume": 0, "oi": 0}
    market_data = {"current_ltp": 100.0}
    context = {"trading_mode": "LIVE", "market_open": True}
    res = score_candidate(candidate, market_data, context)
    assert "missing_liquidity_context_live_block" in res["penalty_reasons"]
    assert res["score_breakdown"]["components"]["liquidity_score"] == 0.0

def test_live_stale_quote_is_blocked():
    candidate = {"trade_id": "T1", "quote_age_sec": 3.0} # > 2.0s LIVE SLA
    market_data = {"current_ltp": 100.0}
    context = {"trading_mode": "LIVE", "market_open": True}
    res = score_candidate(candidate, market_data, context)
    assert "stale_quote_age_live_block" in res["penalty_reasons"]
    assert res["score_breakdown"]["components"]["timing_score"] == 0.0

def test_live_missing_quote_age_is_blocked():
    candidate = {"trade_id": "T1"}
    market_data = {"current_ltp": 100.0}
    context = {"trading_mode": "LIVE", "market_open": True}
    res = score_candidate(candidate, market_data, context)
    assert "missing_timing_context_live_block" in res["penalty_reasons"]
    assert res["score_breakdown"]["components"]["timing_score"] == 0.0

def test_rr_fallback_disabled_in_live():
    candidate = {"trade_id": "T1", "entry_price": 100.0, "stop_price": None, "target_price": None}
    market_data = {"current_ltp": 100.0}
    context = {"trading_mode": "LIVE", "market_open": True}
    res = score_candidate(candidate, market_data, context)
    assert "missing_rr_context_live_block" in res["penalty_reasons"]
    assert res["score_breakdown"]["components"]["rr_score"] == 0.0

def test_rr_fallback_enabled_in_paper():
    candidate = {"trade_id": "T1", "entry_price": 100.0, "stop_price": None, "target_price": None}
    market_data = {"current_ltp": 100.0}
    context = {"trading_mode": "PAPER", "market_open": True}
    res = score_candidate(candidate, market_data, context)
    assert "rr_estimated_context" in res.get("penalty_reasons", []) or "missing_rr_context" not in res["penalty_reasons"]
    assert res["score_breakdown"]["components"]["rr_score"] > 0.0

def test_feed_risk_candidates_quarantined():
    candidate = {"trade_id": "T1", "candidate_class": "fallback"}
    assert is_feed_risk_candidate(candidate).is_risk is True
    
    candidate = {"trade_id": "T1", "safety_flags": ["synthetic"]}
    assert is_feed_risk_candidate(candidate).is_risk is True

    candidate = {"trade_id": "T1", "safety_flags": ["stale_feed"]}
    assert is_feed_risk_candidate(candidate).is_risk is True
    
    candidate = {"trade_id": "T1", "safety_flags": ["missing_depth"]}
    assert is_feed_risk_candidate(candidate).is_risk is True

    candidate = {"trade_id": "T1", "safety_flags": ["clean_trade"]}
    assert is_feed_risk_candidate(candidate).is_risk is False
