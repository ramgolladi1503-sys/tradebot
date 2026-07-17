import pandas as pd
from typing import List, Dict, Any, Tuple

def validate_session_quality(nifty_df: pd.DataFrame, banknifty_df: pd.DataFrame) -> Tuple[bool, List[str]]:
    rejections = []
    
    # 1. Presence check
    if nifty_df.empty:
        rejections.append("MISSING_NIFTY")
    if banknifty_df.empty:
        rejections.append("MISSING_BANKNIFTY")
        
    if rejections:
        return False, rejections
        
    cutoff_time = pd.Timestamp("14:44:00").time()
    
    # Slice inputs to cutoff time to ensure future data post-cutoff cannot affect quality gates
    # Since timestamps represent candle open, 14:44:00 candle closes at 14:45:00.
    n_times_all = nifty_df["timestamp"].dt.time
    b_times_all = banknifty_df["timestamp"].dt.time
    
    nifty = nifty_df[n_times_all <= cutoff_time].sort_values("timestamp").reset_index(drop=True)
    bnifty = banknifty_df[b_times_all <= cutoff_time].sort_values("timestamp").reset_index(drop=True)
    
    if nifty.empty:
        rejections.append("DECISION_WINDOW_INCOMPLETE")
    if bnifty.empty:
        rejections.append("DECISION_WINDOW_INCOMPLETE")
        
    if rejections:
        return False, rejections
    
    # 2. Duplicate timestamps check
    if nifty["timestamp"].duplicated().any():
        rejections.append("DUPLICATE_TIMESTAMP")
    if bnifty["timestamp"].duplicated().any():
        rejections.append("DUPLICATE_TIMESTAMP")
        
    # 3. OHLC validity
    for col in ["open", "high", "low", "close"]:
        if col in nifty.columns and nifty[col].isna().any():
            rejections.append("OHLC_INVALID")
        if col in bnifty.columns and bnifty[col].isna().any():
            rejections.append("OHLC_INVALID")
            
    # Invariants: high < low, high < open, high < close, low > open, low > close
    if "high" in nifty.columns and "low" in nifty.columns:
        if (nifty["high"] < nifty["low"]).any() or (nifty["high"] < nifty["open"]).any() or (nifty["high"] < nifty["close"]).any():
            rejections.append("OHLC_INVALID")
        if (nifty["low"] > nifty["open"]).any() or (nifty["low"] > nifty["close"]).any():
            rejections.append("OHLC_INVALID")
            
    if "high" in bnifty.columns and "low" in bnifty.columns:
        if (bnifty["high"] < bnifty["low"]).any() or (bnifty["high"] < bnifty["open"]).any() or (bnifty["high"] < bnifty["close"]).any():
            rejections.append("OHLC_INVALID")
        if (bnifty["low"] > bnifty["open"]).any() or (bnifty["low"] > bnifty["close"]).any():
            rejections.append("OHLC_INVALID")

    # Time boundaries check (IST offset based on 09:15 - 09:44 and cutoff 14:45)
    n_times = nifty["timestamp"].dt.time
    b_times = bnifty["timestamp"].dt.time
    
    # Opening window completeness check: need bar at 09:15 and 09:44
    open_start = pd.Timestamp("09:15:00").time()
    open_end = pd.Timestamp("09:44:00").time()
    
    nifty_open_window = nifty[(n_times >= open_start) & (n_times <= open_end)]
    bnifty_open_window = bnifty[(b_times >= open_start) & (b_times <= open_end)]
    
    if nifty_open_window.empty or len(nifty_open_window) < 30: # 30 1-min bars expected
        rejections.append("OPENING_WINDOW_INCOMPLETE")
    if bnifty_open_window.empty or len(bnifty_open_window) < 30:
        rejections.append("OPENING_WINDOW_INCOMPLETE")
        
    # Decision window check (need the cutoff bar itself)
    n_decision = nifty[n_times == cutoff_time]
    b_decision = bnifty[b_times == cutoff_time]
    
    if n_decision.empty:
        rejections.append("DECISION_WINDOW_INCOMPLETE")
    if b_decision.empty:
        rejections.append("DECISION_WINDOW_INCOMPLETE")
        
    # Align checks: timestamps must align in critical windows
    n_ts_set = set(nifty_open_window["timestamp"])
    b_ts_set = set(bnifty_open_window["timestamp"])
    if n_ts_set != b_ts_set:
        rejections.append("TIMESTAMP_MISALIGNMENT")
        
    unique_rejections = sorted(list(set(rejections)))
    return len(unique_rejections) == 0, unique_rejections
