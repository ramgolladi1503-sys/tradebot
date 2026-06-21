import pytest
import pandas as pd
from datetime import datetime, timedelta
from core.candidate_audits.htf_strategies import HTFStrategy
from core.candidate_audits.models import Candle, Signal, Rejection

# Helper to create mock candles
def _make_candle(ts, o, h, l, c, v=1000):
    return Candle("NIFTY", ts, o, h, l, c, v, c)

def _mock_data():
    ts = datetime.now().replace(hour=11, minute=15, second=0, microsecond=0)
    
    # 15m historical df
    df_15m = pd.DataFrame([
        vars(_make_candle(ts - timedelta(minutes=30), 25000, 25050, 24950, 25020)),
        vars(_make_candle(ts - timedelta(minutes=15), 25020, 25100, 25010, 25080)),
    ])
    
    # 1m historical df
    df_1m = pd.DataFrame([
        vars(_make_candle(ts - timedelta(minutes=2), 25070, 25080, 25060, 25075)),
        vars(_make_candle(ts - timedelta(minutes=1), 25075, 25090, 25070, 25080)),
    ])
    df_1m['trend_15m'] = 1 # UP
    df_1m['trend_30m'] = 1 # UP
    
    c_15m = _make_candle(ts, 25080, 25150, 25070, 25120)
    c_1m = _make_candle(ts, 25120, 25130, 25110, 25125)
    
    return df_15m, df_1m, c_15m, c_1m, ts

# ==========================================
# 1. HTF_OPENING_DRIVE_CONT
# ==========================================
@pytest.mark.xfail(strict=True, reason="IMPLEMENTATION_BUG_FOUND: HTF_OPENING_DRIVE_CONT rejects valid bullish inputs; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_opening_drive_cont_bullish_maps_correctly():
    strat = HTFStrategy("OPENING_DRIVE_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    # To match OPENING_DRIVE_CONT, c_15m.close > od_high
    strat.od_high = 25100
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Signal)
    assert res.target > res.entry_price # Bullish maps to target > entry (CE)
    assert res.setup_name == "HTF_OPENING_DRIVE_CONT"

@pytest.mark.xfail(strict=True, reason="IMPLEMENTATION_BUG_FOUND: HTF_OPENING_DRIVE_CONT rejects valid bearish inputs; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_opening_drive_cont_bearish_maps_correctly():
    strat = HTFStrategy("OPENING_DRIVE_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    df_1m.loc[1, 'trend_15m'] = -1
    df_1m.loc[1, 'trend_30m'] = -1
    c_15m = _make_candle(ts, 25080, 25090, 25000, 25010)
    strat.od_low = 25050
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Signal)
    assert res.target < res.entry_price # Bearish maps to target < entry (PE)

def test_opening_drive_cont_no_trigger_blocks():
    strat = HTFStrategy("OPENING_DRIVE_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    strat.od_high = 25200 # close not > od_high
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Rejection)
    assert res.reason == "REJECT_STRUCTURE"

# ==========================================
# 2. HTF_15M_TREND_CONT
# ==========================================
def test_15m_trend_cont_bullish_maps_correctly():
    strat = HTFStrategy("15M_TREND_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    # Must have close > open, and close > prev high
    c_15m = _make_candle(ts, 25050, 25150, 25040, 25140)
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Signal)
    assert res.target > res.entry_price

@pytest.mark.xfail(strict=True, reason="IMPLEMENTATION_BUG_FOUND: HTF_15M_TREND_CONT rejects valid bearish inputs; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_15m_trend_cont_bearish_maps_correctly():
    strat = HTFStrategy("15M_TREND_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    df_1m.loc[1, 'trend_15m'] = -1
    df_1m.loc[1, 'trend_30m'] = -1
    # Must have close < open, and close < prev low
    c_15m = _make_candle(ts, 25080, 25090, 24900, 24910)
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Signal)
    assert res.target < res.entry_price

# ==========================================
# 3. HTF_15M_VWAP_PULLBACK
# ==========================================
def test_15m_vwap_pullback_bullish_maps_correctly():
    strat = HTFStrategy("15M_VWAP_PULLBACK")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    vwap = 25000
    c_15m = _make_candle(ts, 25080, 25150, 24990, 25050) # low <= vwap*1.001 (25025), close > vwap, dist = 50/25000 = 0.002
    c_15m.vwap = vwap
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Signal)
    assert res.target > res.entry_price

# ==========================================
# 4. HTF_FAILED_BREAKOUT_REVERSAL
# ==========================================
@pytest.mark.xfail(strict=True, reason="IMPLEMENTATION_BUG_FOUND: HTF_FAILED_BREAKOUT_REVERSAL miscalculates mapping directions; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_failed_breakout_reversal_bearish_maps_correctly():
    strat = HTFStrategy("FAILED_BREAKOUT_REVERSAL")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    # For FBR, requires RANGE or CHOP regime
    # df_15m.iloc[-2]['high'] > od_high and current_candle_15m.close < od_high
    strat.od_high = 25090
    c_15m = _make_candle(ts, 25100, 25110, 25050, 25060)
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="RANGE")
    assert isinstance(res, Signal)
    assert res.target < res.entry_price

# ==========================================
# 5. HTF_PDH_PDL_HOLD
# ==========================================
@pytest.mark.xfail(strict=True, reason="IMPLEMENTATION_BUG_FOUND: HTF_PDH_PDL_HOLD rejects valid bullish inputs; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_pdh_pdl_hold_bullish_maps_correctly():
    strat = HTFStrategy("PDH_PDL_HOLD")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    strat.pdh = 25050
    strat.pdl = 24000
    c_15m = _make_candle(ts, 25060, 25150, 25050, 25100)
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    assert isinstance(res, Signal)
    assert res.target > res.entry_price

# ==========================================
# Safety & Pipeline Assertions
# ==========================================
@pytest.mark.xfail(strict=True, reason="IMPLEMENTATION_BUG_FOUND: HTF_OPENING_DRIVE_CONT fails to return Rejection on NaN; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_htf_nan_fails_closed():
    strat = HTFStrategy("OPENING_DRIVE_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    
    # Inject NaN
    c_1m.open = float('nan')
    strat.od_high = 25100
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime="VOL_EXPANSION")
    
    # Should safely reject, not return an executable signal
    assert isinstance(res, Rejection)
    assert res.reason == "REJECT_EXECUTION_AVAILABILITY"

def test_htf_missing_field_fails_closed():
    strat = HTFStrategy("OPENING_DRIVE_CONT")
    df_15m, df_1m, c_15m, c_1m, ts = _mock_data()
    
    # Simulate missing data by passing empty DF
    empty_df = pd.DataFrame()
    with pytest.raises(Exception):
        # The logic does not safely handle missing rows, it throws an exception (IndexError).
        # We classify this as failing closed, but it's an unhandled crash.
        res = strat.evaluate(df_15m, empty_df, c_15m, c_1m, regime="VOL_EXPANSION")

@pytest.mark.xfail(strict=True, reason="PIPELINE_MUTATION_FOUND: HTF_BYPASSES_MAIN_SAFETY_GATES HTF paths completely bypass TradeBuilder and Execution Gates; tracked in docs/strategy_truth/strategy_truth_bug_register.md")
def test_htf_pipeline_safety_revival():
    # BUG/GAP FOUND: HTF strategies do not integrate with Phase-2/ranking pipeline.
    # They are executed by run_htf_real_paper_monitor.py which skips trade_builder and execution_gates entirely.
    # Therefore, they cannot guarantee Phase-2 safety or execution gate safety.
    # We write a failing test to document this PIPELINE_MUTATION_FOUND.
    assert False, "PIPELINE_MUTATION_FOUND: HTF paths completely bypass TradeBuilder and Execution Gates."
