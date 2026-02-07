import pandas as pd
from core.market_data import get_current_regime

# LEGACY WRAPPER; DO NOT ADD LOGIC.

def adx(df, period=14):
    return None

def trend_slope(df, window=20):
    return 0.0

def detect_regime(df=None):
    snap = get_current_regime("NIFTY")
    return {
        "regime": snap.get("primary_regime", "NEUTRAL"),
        **snap,
    }
