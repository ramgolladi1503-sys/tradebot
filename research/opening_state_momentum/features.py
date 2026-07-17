import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

class FeatureExtractionError(Exception):
    pass

def extract_features(nifty_df: pd.DataFrame, banknifty_df: pd.DataFrame) -> Dict[str, Any]:
    # Sort for safety
    nifty = nifty_df.sort_values("timestamp").reset_index(drop=True)
    bnifty = banknifty_df.sort_values("timestamp").reset_index(drop=True)
    
    n_times = nifty["timestamp"].dt.time
    b_times = bnifty["timestamp"].dt.time
    
    open_start = pd.Timestamp("09:15:00").time()
    open_end = pd.Timestamp("09:44:00").time()
    cutoff_time = pd.Timestamp("14:44:00").time()
    
    # Opening window slices
    n_open = nifty[(n_times >= open_start) & (n_times <= open_end)]
    b_open = bnifty[(b_times >= open_start) & (b_times <= open_end)]
    
    # 1. NIFTY session open & opening window close
    session_open = float(n_open.iloc[0]["open"])
    opening_close = float(n_open.iloc[-1]["close"])
    
    opening_high = float(n_open["high"].max())
    opening_low = float(n_open["low"].min())
    
    # 2. NIFTY opening return
    nifty_opening_return = (opening_close / session_open) - 1.0
    
    # 3. BANKNIFTY opening return
    b_session_open = float(b_open.iloc[0]["open"])
    b_opening_close = float(b_open.iloc[-1]["close"])
    bnifty_opening_return = (b_opening_close / b_session_open) - 1.0
    
    # 4. Close location
    range_high_low = opening_high - opening_low
    if range_high_low == 0.0:
        raise FeatureExtractionError("ZERO_OPENING_RANGE")
    close_location = (opening_close - opening_low) / range_high_low
    
    # 5. Decision close
    n_decision = nifty[n_times == cutoff_time]
    decision_close = float(n_decision.iloc[0]["close"])
    
    # 6. Retained-move fraction
    # Long retained denominator: opening_close - session_open
    # Short retained denominator: session_open - opening_close
    # We must reject non-positive denominators
    long_denom = opening_close - session_open
    short_denom = session_open - opening_close
    
    # 7. Session Typical Price Mean Anchor
    nifty_history = nifty[n_times <= cutoff_time]
    typical_prices = (nifty_history["high"] + nifty_history["low"] + nifty_history["close"]) / 3.0
    session_anchor = float(typical_prices.mean())
    
    features = {
        "session_open": session_open,
        "opening_close": opening_close,
        "opening_high": opening_high,
        "opening_low": opening_low,
        "opening_midpoint": (opening_high + opening_low) / 2.0,
        "nifty_opening_return": nifty_opening_return,
        "bnifty_opening_return": bnifty_opening_return,
        "close_location": close_location,
        "decision_close": decision_close,
        "long_retained_denom": long_denom,
        "short_retained_denom": short_denom,
        "session_anchor": session_anchor,
        "anchor_type": "SESSION_TYPICAL_PRICE_MEAN"
    }
    
    return features
