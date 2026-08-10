#!/usr/bin/env python3
import math
from typing import Any

def compute_bar_features(bar: dict[str, Any]) -> dict[str, float]:
    open_p = float(bar["open"])
    high_p = float(bar["high"])
    low_p = float(bar["low"])
    close_p = float(bar["close"])

    total_range = max(high_p - low_p, 1e-6)
    body = abs(close_p - open_p)
    upper_wick = high_p - max(open_p, close_p)
    lower_wick = min(open_p, close_p) - low_p

    body_ratio = body / total_range
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    close_location = (close_p - low_p) / total_range

    return {
        "bar_body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "close_location_value": close_location,
        "total_range": total_range
    }

def compute_session_features(session_bars: list[dict[str, Any]], current_idx: int) -> dict[str, Any]:
    if current_idx < 0 or current_idx >= len(session_bars):
        return {}

    bars_so_far = session_bars[: current_idx + 1]
    highs = [float(b["high"]) for b in bars_so_far]
    lows = [float(b["low"]) for b in bars_so_far]
    session_high = max(highs)
    session_low = min(lows)
    session_range = max(session_high - session_low, 1e-6)

    curr_close = float(session_bars[current_idx]["close"])
    range_percentile = (curr_close - session_low) / session_range

    open_price = float(session_bars[0]["open"])
    session_return_bps = (curr_close / open_price - 1.0) * 10000.0

    return {
        "range_percentile_so_far": range_percentile,
        "session_open_to_now_return": session_return_bps,
        "session_high_so_far": session_high,
        "session_low_so_far": session_low,
        "session_range_so_far": session_range
    }

def compute_prior_session_features(prior_session_bars: list[dict[str, Any]]) -> dict[str, Any]:
    if not prior_session_bars:
        return {}
    highs = [float(b["high"]) for b in prior_session_bars]
    lows = [float(b["low"]) for b in prior_session_bars]
    close_p = float(prior_session_bars[-1]["close"])
    p_high = max(highs)
    p_low = min(lows)
    p_range = max(p_high - p_low, 1e-6)
    close_loc = (close_p - p_low) / p_range

    return {
        "prior_session_range": p_range,
        "prior_session_high": p_high,
        "prior_session_low": p_low,
        "prior_session_close_location": close_loc
    }
