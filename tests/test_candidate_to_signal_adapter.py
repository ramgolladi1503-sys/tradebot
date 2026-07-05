"""Tests for candidate_to_signal_adapter."""

from core.candidate_to_signal_adapter import adapt_candidate_to_signals
from core.movement_contract import StrategyCandidate, StrategyContext

def _make_candidate(status="VALIDATED_CANDIDATE", direction="BUY_CALL", symbol="NIFTY", blockers=(), evidence=None):
    return StrategyCandidate(
        schema_version=1,
        strategy_id="TEST",
        movement_type="TREND_PULLBACK",
        symbol=symbol,
        direction=direction,
        status=status,
        raw_score=0.8,
        confidence_score=0.75,
        price_structure_score=0.8,
        option_confirmation_score=0.8,
        liquidity_score=0.8,
        freshness_score=0.8,
        volatility_score=0.8,
        regime_alignment_score=0.8,
        timing_score=0.8,
        trap_risk_score=0.8,
        confluence_score=0.8,
        blockers=blockers,
        evidence=evidence or {},
    )

def test_adapter_rejects_unsafe_statuses():
    ctx = StrategyContext(symbol="NIFTY", spot_ltp=22010.5)
    
    for status in ["ADVISORY", "FALLBACK", "RECOVERED", "STALE", "DEBUG"]:
        cand = _make_candidate()
        object.__setattr__(cand, 'status', status)
        assert not adapt_candidate_to_signals(cand, ctx)

def test_adapter_rejects_hard_blockers():
    ctx = StrategyContext(symbol="NIFTY", spot_ltp=22010.5)
    cand = _make_candidate(blockers=("STALE_OPTION_LTP",))
    assert not adapt_candidate_to_signals(cand, ctx)

def test_adapter_rejects_unsafe_quotes():
    ctx = StrategyContext(symbol="NIFTY", spot_ltp=22010.5)
    
    cand = _make_candidate(evidence={"recovered_fallback": "true"})
    assert not adapt_candidate_to_signals(cand, ctx)
    
    cand = _make_candidate(evidence={"stale_quote": "true"})
    assert not adapt_candidate_to_signals(cand, ctx)
    
    cand = _make_candidate(evidence={"quote_source": "synthetic"})
    assert not adapt_candidate_to_signals(cand, ctx)

def test_adapter_missing_option_ltp_fails_closed():
    cand = _make_candidate(evidence={"quote_source": "upstox_historical"})
    ctx = StrategyContext(symbol="NIFTY", spot_ltp=22000.0)
    
    signals = adapt_candidate_to_signals(cand, ctx, mode="real")
    assert len(signals) == 1
    assert signals[0]["lifecycle_state"] == "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED"
    assert signals[0]["blocked_reason"] == "MISSING_VALID_OPTION_LTP"

def test_adapter_missing_strike_fails_closed():
    cand = _make_candidate(symbol="UNKNOWN", evidence={"option_ltp": 100, "quote_source": "real"})
    ctx = StrategyContext(symbol="UNKNOWN", spot_ltp=22000.0)
    signals = adapt_candidate_to_signals(cand, ctx, mode="real")
    assert len(signals) == 1
    assert signals[0]["lifecycle_state"] == "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED"
    assert signals[0]["blocked_reason"] == "MISSING_STRIKE_STEP_CONFIG"
    assert signals[0]["adapter_approved_for_replay"] is False

def test_adapter_fixture_mode_is_non_certifiable():
    cand = _make_candidate(symbol="UNKNOWN", evidence={"stop_loss": 50, "target": 150, "time_stop": 30})
    ctx = StrategyContext(symbol="UNKNOWN", spot_ltp=22000.0)
    
    signals = adapt_candidate_to_signals(cand, ctx, mode="fixture")
    assert len(signals) == 1
    assert signals[0]["certification_eligible"] is False
    assert signals[0]["adapter_approved_for_replay"] is False
    assert signals[0]["data_source"] == "synthetic_test_fixture"
    assert signals[0]["strike_step_used"] == 100

def test_adapter_missing_risk_reward_fails_closed():
    cand = _make_candidate(evidence={"option_ltp": 255.5, "quote_source": "upstox_live"})
    ctx = StrategyContext(symbol="NIFTY", spot_ltp=22000.0)
    
    signals = adapt_candidate_to_signals(cand, ctx, mode="real")
    assert len(signals) == 1
    assert signals[0]["lifecycle_state"] == "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED"
    assert signals[0]["blocked_reason"] == "MISSING_RISK_REWARD_CONTRACT"

def test_adapter_valid_historical_produces_approved_for_replay():
    cand = _make_candidate(evidence={"option_ltp": 255.5, "quote_source": "upstox_historical", "stop_loss": 200, "target": 300, "time_stop": 15})
    ctx = StrategyContext(symbol="NIFTY", spot_ltp=22000.0)
    
    signals = adapt_candidate_to_signals(cand, ctx, mode="real")
    assert len(signals) == 1
    sig = signals[0]
    assert sig.get("lifecycle_state") is None
    assert sig["adapter_approved_for_replay"] is True
    assert sig["certification_eligible"] is True
    
    assert sig["live_allowed"] is False
    assert sig["paper_live_allowed"] is False
    assert sig["broker_order_allowed"] is False
    assert sig["execution_allowed"] is False
    
    assert sig["strike_resolution_source"] == "STRIKE_STEP_BY_SYMBOL"
    assert sig["spot_ltp_used"] == 22000.0
    assert sig["strike_step_used"] == 50
    assert sig["selected_strike"] == 22000
