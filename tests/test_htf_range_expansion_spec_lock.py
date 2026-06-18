import pytest
import pandas as pd
from datetime import datetime, timedelta
import inspect

from core.candidate_audits.htf_strategies import HTFStrategy
from core.candidate_audits.models import Candle, Signal, Rejection

def create_mock_data(time_str, regime="VOL_EXPANSION", c15_close=100.0, od_high=90.0, pdc=100.0, current_open=100.0):
    ts = pd.to_datetime(f"2024-01-02 {time_str}")
    
    # Mock dataframes
    df_15m = pd.DataFrame([
        {'timestamp': pd.to_datetime("2024-01-01 15:15:00"), 'open': 90.0, 'high': 100.0, 'low': 90.0, 'close': pdc, 'volume': 1000},
        {'timestamp': ts, 'open': current_open, 'high': c15_close + 5, 'low': od_high - 5, 'close': c15_close, 'volume': 1000}
    ])
    
    df_1m = pd.DataFrame([
        {'timestamp': ts, 'open': c15_close, 'high': c15_close+1, 'low': c15_close-1, 'close': c15_close, 'volume': 100, 'trend_15m': 1, 'trend_30m': 1}
    ])
    
    c_15m = Candle('NIFTY', ts, current_open, c15_close + 5, od_high - 5, c15_close, 1000, c15_close)
    c_1m = Candle('NIFTY', ts, c15_close, c15_close+1, c15_close-1, c15_close, 100, c15_close)
    
    return df_15m, df_1m, c_15m, c_1m, regime

def test_vol_expansion_gate_locked():
    strat = HTFStrategy("RANGE_EXPANSION")
    df_15m, df_1m, c_15m, c_1m, regime = create_mock_data("10:30:00", regime="CHOP")
    strat.last_date = c_15m.timestamp.date()
    strat.od_high = 90.0
    
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime)
    assert isinstance(res, Rejection), "Strategy MUST reject when regime is not VOL_EXPANSION"
    assert res.reason == "REJECT_VOLATILITY", "Reason must be explicitly REJECT_VOLATILITY"

def test_session_gating_locked():
    strat = HTFStrategy("RANGE_EXPANSION")
    
    # Test early reject
    df_15m, df_1m, c_15m, c_1m, regime = create_mock_data("10:00:00", regime="VOL_EXPANSION")
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime)
    assert isinstance(res, Rejection)
    assert res.reason == "REJECT_SESSION", "MUST reject before 10:15"
    
    # Test late reject
    df_15m, df_1m, c_15m, c_1m, regime = create_mock_data("14:45:00", regime="VOL_EXPANSION")
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime)
    assert isinstance(res, Rejection)
    assert res.reason == "REJECT_SESSION", "MUST reject after 14:30"

def test_gap_expansion_rejection_locked():
    strat = HTFStrategy("RANGE_EXPANSION")
    df_15m, df_1m, c_15m, c_1m, regime = create_mock_data("10:30:00", regime="VOL_EXPANSION", c15_close=102.0, od_high=95.0, pdc=100.0, current_open=101.0)
    strat.last_date = c_15m.timestamp.date()
    strat.pdc = 100.0 # Prior day close
    strat.od_high = 95.0
    
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime)
    assert isinstance(res, Rejection)
    assert res.reason == "REJECT_GAP_EXPANSION", "MUST reject if gap is > 0.5%"

def test_execution_latency_simulation():
    strat = HTFStrategy("RANGE_EXPANSION")
    # Simulate a corrupted 1m candle (meaning no next-open execution available)
    df_15m, df_1m, c_15m, c_1m, regime = create_mock_data("10:30:00", regime="VOL_EXPANSION", c15_close=100.0, od_high=90.0)
    strat.last_date = c_15m.timestamp.date()
    c_1m.open = float('nan') # Missing next open
    strat.od_high = 90.0
    
    res = strat.evaluate(df_15m, df_1m, c_15m, c_1m, regime)
    assert isinstance(res, Rejection)
    assert res.reason == "REJECT_EXECUTION_AVAILABILITY", "MUST enforce next-candle execution tracking"

def test_no_broker_routing_imports():
    import core.candidate_audits.htf_strategies as htf_mod
    src = inspect.getsource(htf_mod)
    assert "kite.place_order" not in src, "FORBIDDEN: Live routing imports found in strategy logic"
    assert "order_router" not in src, "FORBIDDEN: order_router imported"
    assert "execution_engine" not in src, "FORBIDDEN: execution_engine imported"
