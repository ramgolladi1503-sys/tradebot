from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.exhaustion_reversal import generate_exhaustion_reversal_candidates
from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates


def _regime(primary="EXHAUSTION_RISK", **scores):
    base={"TREND_UP":0.0,"TREND_DOWN":0.0,"RANGE":0.0,"CHOP":0.0,"COMPRESSION":0.0,"VOLATILITY_EXPANSION":0.0,"TRAP_RISK":0.0,"EXHAUSTION_RISK":0.0,"EXPIRY_CONTEXT":0.0,"INCONCLUSIVE":0.0}
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


def _base_context(**overrides):
    payload={
        "symbol":"NIFTY","spot_ltp":22740.0,"open_price":22500.0,"vwap":22580.0,"vwap_slope":0.01,
        "day_high":22760.0,"day_low":22480.0,"nearest_resistance":22760.0,"nearest_support":22490.0,
        "range_width_pct":0.50,"atr_short":80.0,"atr_long":100.0,"volume_z":0.35,
        "volatility_state":"EXPANDING",
        "option_ce_ltp":125.0,"option_pe_ltp":92.0,"ce_premium_change":0.0,"pe_premium_change":10.0,
        "ce_spread_pct":0.8,"pe_spread_pct":0.8,"ce_depth":1200.0,"pe_depth":1200.0,
        "option_ltp_age_sec":0.4,"quote_source":"live_option_tick","fallback_used":False,"minutes_since_open":110,
        "metadata":{"trap_state":True,"oscillator_confirmation":True,"rsi":70.0},
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_exhaustion_reversal_generates_put_candidate_after_upside_stall():
    candidates=generate_exhaustion_reversal_candidates(_base_context(),_regime(EXHAUSTION_RISK=0.75,TREND_UP=0.35))
    assert len(candidates)==1
    c=candidates[0]
    assert c.strategy_id=="exhaustion_reversal_v1" and c.direction=="BUY_PUT"
    assert c.evidence["volatility_state"]=="EXPANDING" and c.evidence["trap_state"] is True


def test_exhaustion_reversal_generates_call_candidate_after_downside_stall():
    ctx=_base_context(spot_ltp=22420.0,vwap=22580.0,ce_premium_change=11.0,pe_premium_change=0.0)
    candidates=generate_exhaustion_reversal_candidates(ctx,_regime(EXHAUSTION_RISK=0.75,TREND_DOWN=0.35))
    assert len(candidates)==1 and candidates[0].direction=="BUY_CALL"


def test_exhaustion_reversal_fails_closed_on_missing_thesis_evidence():
    assert generate_exhaustion_reversal_candidates(_base_context(vwap=None),_regime(EXHAUSTION_RISK=0.8))==()
    assert generate_exhaustion_reversal_candidates(_base_context(volume_z=None),_regime(EXHAUSTION_RISK=0.8))==()
    assert generate_exhaustion_reversal_candidates(_base_context(volatility_state=None),_regime(EXHAUSTION_RISK=0.8))==()
    assert generate_exhaustion_reversal_candidates(_base_context(metadata={"oscillator_confirmation":True}),_regime(EXHAUSTION_RISK=0.8))==()
    strong=_base_context(ce_premium_change=22.0,volume_z=3.0,pe_premium_change=0.0)
    assert generate_exhaustion_reversal_candidates(strong,_regime(EXHAUSTION_RISK=0.8))==()


def test_exhaustion_reversal_bad_quote_stays_raw_not_executable():
    ctx=_base_context(fallback_used=True,quote_source="recovered_fallback",pe_spread_pct=8.0,option_ltp_age_sec=8.0)
    candidates=generate_exhaustion_reversal_candidates(ctx,_regime(EXHAUSTION_RISK=0.8))
    pool=build_candidate_pool(candidates); summary=pool.summary()
    assert summary.total_count==1 and summary.raw_count==1 and summary.executable_eligible_count==0


def test_mean_reversion_extension_generates_put_with_explicit_oscillator():
    ctx=_base_context(spot_ltp=22710.0,vwap=22580.0,nearest_resistance=22720.0,pe_premium_change=10.0,ce_premium_change=0.0,metadata={"oscillator_confirmation":True,"rsi":70.0})
    candidates=generate_mean_reversion_extension_candidates(ctx,_regime(primary="RANGE",RANGE=0.72,TREND_UP=0.15,VOLATILITY_EXPANSION=0.05))
    assert len(candidates)==1 and candidates[0].direction=="BUY_PUT"
    assert candidates[0].evidence["oscillator_confirmation"] is True


def test_mean_reversion_extension_generates_call_with_explicit_oscillator():
    ctx=_base_context(spot_ltp=22460.0,vwap=22580.0,nearest_support=22450.0,ce_premium_change=10.0,pe_premium_change=0.0,metadata={"oscillator_confirmation":True,"rsi":30.0})
    candidates=generate_mean_reversion_extension_candidates(ctx,_regime(primary="RANGE",RANGE=0.72,TREND_DOWN=0.15,VOLATILITY_EXPANSION=0.05))
    assert len(candidates)==1 and candidates[0].direction=="BUY_CALL"


def test_mean_reversion_fails_closed_without_oscillator_or_in_bad_regime():
    missing_osc=_base_context(spot_ltp=22710.0,vwap=22580.0,metadata={"trap_state":True})
    assert generate_mean_reversion_extension_candidates(missing_osc,_regime(primary="RANGE",RANGE=0.8))==()
    non_range=_base_context(spot_ltp=22710.0,vwap=22580.0)
    assert generate_mean_reversion_extension_candidates(non_range,_regime(primary="TREND_UP",TREND_UP=0.75))==()
    strong=_base_context(spot_ltp=22710.0,vwap=22580.0,nearest_resistance=22720.0,ce_premium_change=22.0,pe_premium_change=0.0,volume_z=3.0)
    assert generate_mean_reversion_extension_candidates(strong,_regime(primary="RANGE",RANGE=0.7,TREND_UP=0.75,VOLATILITY_EXPANSION=0.7))==()


def test_mean_reversion_bad_quote_stays_raw_not_executable():
    ctx=_base_context(spot_ltp=22710.0,vwap=22580.0,nearest_resistance=22720.0,fallback_used=True,quote_source="recovered_fallback",pe_spread_pct=9.0,option_ltp_age_sec=8.0,metadata={"oscillator_confirmation":True,"rsi":70.0})
    candidates=generate_mean_reversion_extension_candidates(ctx,_regime(primary="RANGE",RANGE=0.8))
    pool=build_candidate_pool(candidates); summary=pool.summary()
    assert summary.total_count==1 and summary.raw_count==1 and summary.executable_eligible_count==0
