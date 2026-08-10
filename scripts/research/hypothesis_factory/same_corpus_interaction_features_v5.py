#!/usr/bin/env python3
"""
Same-Corpus Interaction Features V5 (TradeBot / MROS)
Calculates multi-dimensional interaction features from completed OHLC bars, 
session context, and BDE2 behavior states.
"""
import math
from typing import Dict, List, Any

def compute_bar_features(bar: Dict[str, Any]) -> Dict[str, float]:
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    c = float(bar["close"])
    
    rng = max(h - l, 1e-6)
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    
    return {
        "bar_body_ratio": body / rng,
        "upper_wick_ratio": upper_wick / rng,
        "lower_wick_ratio": lower_wick / rng,
        "close_location_value": (c - l) / rng
    }

def compute_session_context(df_session) -> Dict[str, Any]:
    """
    Expects df_session sorted by timestamp.
    Calculates completed-bar features and intraday interaction states.
    """
    bars = df_session.to_dict("records")
    n = len(bars)
    if n == 0:
        return {}

    # Calculate running session high/low up to bar t
    running_high = []
    running_low = []
    curr_h = -1e9
    curr_l = 1e9
    for b in bars:
        curr_h = max(curr_h, float(b["high"]))
        curr_l = min(curr_l, float(b["low"]))
        running_high.append(curr_h)
        running_low.append(curr_l)

    # First hour (first 12 5-min bars)
    first_hour_bars = bars[:min(12, n)]
    fh_high = max(float(b["high"]) for b in first_hour_bars)
    fh_low = min(float(b["low"]) for b in first_hour_bars)
    fh_range = max(fh_high - fh_low, 1e-6)

    bar_ctx = []
    for i in range(n):
        bf = compute_bar_features(bars[i])
        rh = running_high[i]
        rl = running_low[i]
        s_rng = max(rh - rl, 1e-6)
        c = float(bars[i]["close"])
        
        # Percentile so far in session
        pct_so_far = (c - rl) / s_rng
        
        # Position in first-hour range
        fh_pos = (c - fh_low) / fh_range if i >= 11 else 0.5
        
        bar_ctx.append({
            "timestamp": str(bars[i]["timestamp"]),
            "index": i,
            "close": c,
            "bar_body_ratio": bf["bar_body_ratio"],
            "upper_wick_ratio": bf["upper_wick_ratio"],
            "lower_wick_ratio": bf["lower_wick_ratio"],
            "close_location_value": bf["close_location_value"],
            "session_range_percentile_so_far": pct_so_far,
            "first_hour_range_location": fh_pos,
            "session_high_so_far": rh,
            "session_low_so_far": rl
        })

    return {
        "bars": bar_ctx,
        "first_hour_high": fh_high,
        "first_hour_low": fh_low,
        "first_hour_range": fh_range
    }
