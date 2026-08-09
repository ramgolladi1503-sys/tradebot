from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.candidate_pool import build_candidate_pool
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates

IST=ZoneInfo("Asia/Kolkata")


def _history(closes, *, start=None):
    start=start or datetime(2026,7,14,9,15,tzinfo=IST)
    bars=[]
    for i,close in enumerate(closes):
        bar_start=start+timedelta(minutes=i); bar_end=bar_start+timedelta(minutes=1)
        bars.append({"symbol":"NIFTY","session_date":"2026-07-14","timeframe":"1m","bar_start_timestamp":bar_start.isoformat(),"bar_end_timestamp":bar_end.isoformat(),"timestamp":bar_end.isoformat(),"open":close-2.0,"high":close+5.0,"low":close-5.0,"close":close,"volume":1000.0+i*100,"source":"unit_test","source_timestamp":bar_end.isoformat(),"receipt_timestamp":(bar_end+timedelta(seconds=1)).isoformat(),"is_complete":True})
    return bars


def _trend_history(closes=(22590.0,22630.0,22615.0,22635.0)):
    return _history(closes)


def _compression_history(center=22610.0):
    return _history((center-2,center+1,center-1,center+2,center,center+1))


def _regime(primary="COMPRESSION",**scores):
    base={"TREND_UP":0.0,"TREND_DOWN":0.0,"RANGE":0.0,"CHOP":0.0,"COMPRESSION":0.0,"VOLATILITY_EXPANSION":0.0,"TRAP_RISK":0.0,"EXHAUSTION_RISK":0.0,"EXPIRY_CONTEXT":0.0,"INCONCLUSIVE":0.0}; base.update(scores)
    return MovementRegimeResult(schema_version=1,primary_regime=primary,scores=base)


def _base_context(**overrides):
    payload={"symbol":"NIFTY","ts_epoch":datetime(2026,7,14,9,30,tzinfo=IST).timestamp(),"spot_ltp":22650.0,"open_price":22500.0,"vwap":22600.0,"day_high":22620.0,"day_low":22480.0,"orb_high":22610.0,"orb_low":22490.0,"nearest_resistance":22620.0,"nearest_support":22490.0,"range_width_pct":0.14,"atr_short":35.0,"atr_long":100.0,"volume_z":1.5,"option_ce_ltp":125.0,"option_pe_ltp":92.0,"ce_premium_change":13.0,"pe_premium_change":0.0,"ce_spread_pct":0.8,"pe_spread_pct":0.8,"ce_depth":1200.0,"pe_depth":1200.0,"option_ltp_age_sec":0.4,"quote_source":"live_option_tick","fallback_used":False,"minutes_since_open":55,"completed_bar_history":_compression_history()}
    payload.update(overrides); return StrategyContext(**payload)


def test_compression_breakout_requires_completed_compression_then_later_call_break():
    candidates=generate_compression_breakout_candidates(_base_context(),_regime(COMPRESSION=0.82,VOLATILITY_EXPANSION=0.45,TREND_UP=0.35))
    assert len(candidates)==1
    c=candidates[0]
    assert c.direction=="BUY_CALL" and c.evidence["completed_bar_history"] is True
    assert c.evidence["compression_lookback_bars"]==6 and c.evidence["breakout_distance_pct"]>0


def test_compression_breakout_requires_completed_compression_then_later_put_break():
    ctx=_base_context(spot_ltp=22450.0,vwap=22520.0,nearest_support=22480.0,nearest_resistance=22620.0,pe_premium_change=14.0,ce_premium_change=0.0,completed_bar_history=_compression_history(22490.0))
    candidates=generate_compression_breakout_candidates(ctx,_regime(COMPRESSION=0.82,VOLATILITY_EXPANSION=0.45,TREND_DOWN=0.35))
    assert len(candidates)==1 and candidates[0].direction=="BUY_PUT"


def test_compression_breakout_fails_without_temporal_compression_or_with_future_bar():
    assert generate_compression_breakout_candidates(_base_context(completed_bar_history=None),_regime(COMPRESSION=0.9))==()
    wide=_history((22500,22540,22480,22560,22460,22580))
    assert generate_compression_breakout_candidates(_base_context(completed_bar_history=wide),_regime(COMPRESSION=0.1))==()
    future=_compression_history(); future[-1]=dict(future[-1]); future[-1]["timestamp"]="2026-07-14T10:00:00+05:30"; future[-1]["bar_end_timestamp"]="2026-07-14T10:00:00+05:30"
    assert generate_compression_breakout_candidates(_base_context(completed_bar_history=future),_regime(COMPRESSION=0.9))==()
    assert generate_compression_breakout_candidates(_base_context(vwap=None),_regime(COMPRESSION=0.9))==()


def test_compression_bad_quote_remains_non_executable_raw_candidate():
    ctx=_base_context(fallback_used=True,quote_source="recovered_fallback",ce_spread_pct=9.0,ce_depth=None,option_ltp_age_sec=8.0)
    candidates=generate_compression_breakout_candidates(ctx,_regime(COMPRESSION=0.8,TREND_UP=0.3)); summary=build_candidate_pool(candidates).summary()
    assert summary.total_count==1 and summary.raw_count==1 and summary.executable_eligible_count==0


def test_trend_pullback_generates_call_candidate_when_uptrend_pullback_holds():
    ctx=_base_context(spot_ltp=22625.0,vwap=22600.0,nearest_support=22610.0,ce_premium_change=11.0,minutes_since_open=75,completed_bar_history=_trend_history())
    candidates=generate_trend_pullback_candidates(ctx,_regime(primary="TREND_UP",TREND_UP=0.72))
    assert len(candidates)==1 and candidates[0].direction=="BUY_CALL" and "pullback_hold" in candidates[0].confluence_tags


def test_trend_pullback_generates_put_candidate_when_downtrend_pullback_rejects():
    ctx=_base_context(spot_ltp=22495.0,vwap=22520.0,nearest_resistance=22510.0,pe_premium_change=12.0,ce_premium_change=0.0,minutes_since_open=80,completed_bar_history=_trend_history((22525.0,22500.0,22510.0,22480.0)))
    candidates=generate_trend_pullback_candidates(ctx,_regime(primary="TREND_DOWN",TREND_DOWN=0.74))
    assert len(candidates)==1 and candidates[0].direction=="BUY_PUT"


def test_trend_pullback_rejects_weak_late_or_missing_core():
    ctx=_base_context(spot_ltp=22625.0,nearest_support=22610.0,completed_bar_history=_trend_history())
    assert generate_trend_pullback_candidates(ctx,_regime(primary="RANGE",TREND_UP=0.2))==()
    late=_base_context(spot_ltp=22850.0,vwap=22600.0,nearest_support=22610.0,completed_bar_history=_trend_history())
    assert generate_trend_pullback_candidates(late,_regime(primary="TREND_UP",TREND_UP=0.8))==()
    assert generate_trend_pullback_candidates(_base_context(spot_ltp=None,completed_bar_history=_trend_history()),_regime(primary="TREND_UP",TREND_UP=0.8))==()


def test_trend_pullback_stale_fallback_remains_non_executable():
    ctx=_base_context(spot_ltp=22625.0,vwap=22600.0,nearest_support=22610.0,fallback_used=True,quote_source="recovered_fallback",ce_premium_change=0.0,ce_spread_pct=8.5,option_ltp_age_sec=7.0,completed_bar_history=_trend_history())
    candidates=generate_trend_pullback_candidates(ctx,_regime(primary="TREND_UP",TREND_UP=0.75))
    assert len(candidates)==1 and candidates[0].status=="RAW_CANDIDATE" and candidates[0].executable_eligible is False
