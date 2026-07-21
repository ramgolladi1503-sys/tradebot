import pytest
import pandas as pd
import numpy as np
import json
import os
from core.vectorized_signals import build_vectorized_signals
from core.config import TradingConfig

OUT_DIR = "runtime/research/upstream_backtest_integrity_codex_validation"
os.makedirs(OUT_DIR, exist_ok=True)

def test_suspect_1_daily_macro_ema_lookahead():
    """
    Suspect 1: Daily macro EMA lookahead.
    Target: core/vectorized_signals.py
    Contract: Changing a future final daily close must NOT change an earlier intraday feature.
    """
    # Create two dataframes identical up to 12:00, but differing at 15:00
    idx = pd.date_range("2024-01-01 09:15:00", periods=50, freq="5min")
    df1 = pd.DataFrame({
        "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 1000
    }, index=idx)
    df2 = df1.copy()
    
    # Change the final close of the day
    df2.iloc[-1, df2.columns.get_loc('close')] = 200.0
    
    config = TradingConfig()
    
    sig1 = build_vectorized_signals(df1, config)
    sig2 = build_vectorized_signals(df2, config)
    
    # Check if the signal/ema at 12:00 is different
    mid_idx = 25 # roughly mid-day
    ema1 = sig1.iloc[mid_idx].get("daily_ema", None)
    ema2 = sig2.iloc[mid_idx].get("daily_ema", None)
    
    # If it's a lookahead, EMA will differ because it used resample('D').last() without shift
    has_lookahead = (ema1 != ema2) and not pd.isna(ema1) and not pd.isna(ema2)
    
    result = {
        "suspect_id": "1",
        "name": "Daily macro EMA lookahead",
        "has_bug": bool(has_lookahead),
        "actual_value": f"ema1={ema1}, ema2={ema2}",
        "expected_value": "ema1 == ema2",
        "bias": "Future data leaks into past EMA, causing perfect foresight." if has_lookahead else "None"
    }
    
    with open(f"{OUT_DIR}/feature_causality_results.json", "w") as f:
        json.dump([result], f, indent=2)
        
    assert not has_lookahead, "Lookahead bug detected in daily macro EMA"
