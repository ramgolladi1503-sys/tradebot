#!/usr/bin/env python3
"""
Same-Corpus Regime-Transition and Volatility-Shock Features V6 (TradeBot / MROS)
Calculates causally derivable regime-transition and volatility-shock features from completed OHLC bars
and prior-session context.
"""
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Any

def compute_v6_session_features(df_session, prior_session_context: Dict[str, Any] = None) -> Dict[str, Any]:
    bars = df_session.to_dict("records")
    n = len(bars)
    if n == 0:
        return {}

    # Realized ranges (high - low) for all bars
    ranges = [max(float(b["high"]) - float(b["low"]), 1e-6) for b in bars]
    closes = [float(b["close"]) for b in bars]
    
    # Calculate rolling realized range percentiles (lookback = 12 bars)
    rolling_range_percentiles = []
    for i in range(n):
        if i < 3:
            rolling_range_percentiles.append(0.50)
        else:
            window_rng = ranges[max(0, i-12):i+1]
            curr = ranges[i]
            pct = sum(1 for r in window_rng if r <= curr) / len(window_rng)
            rolling_range_percentiles.append(pct)

    # Intraday Range Expansion Ratio: range of current bar vs avg range of previous 6 bars
    range_expansion_ratios = []
    for i in range(n):
        if i < 6:
            range_expansion_ratios.append(1.0)
        else:
            avg_prior = np.mean(ranges[i-6:i])
            range_expansion_ratios.append(ranges[i] / max(avg_prior, 1e-6))

    # Prior Session Context
    prior_close_loc = prior_session_context.get("close_location", 0.50) if prior_session_context else 0.50
    prior_range_pct = prior_session_context.get("range_percentile", 0.50) if prior_session_context else 0.50
    prior_close = prior_session_context.get("close", float(bars[0]["open"])) if prior_session_context else float(bars[0]["open"])
    
    gap_bps = ((float(bars[0]["open"]) - prior_close) / prior_close) * 10000.0

    bar_ctx = []
    for i in range(n):
        c = closes[i]
        o = float(bars[i]["open"])
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        rng = ranges[i]

        bar_ctx.append({
            "timestamp": str(bars[i]["timestamp"]),
            "index": i,
            "close": c,
            "realized_range_bps": (rng / c) * 10000.0,
            "rolling_realized_range_percentile": rolling_range_percentiles[i],
            "intraday_range_expansion_ratio": range_expansion_ratios[i],
            "gap_size_bps": gap_bps,
            "prior_session_realized_range_percentile": prior_range_pct,
            "prior_session_close_location": prior_close_loc,
            "bar_body_ratio": abs(c - o) / rng
        })

    return {
        "bars": bar_ctx,
        "gap_size_bps": gap_bps,
        "prior_session_realized_range_percentile": prior_range_pct
    }
