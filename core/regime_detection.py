import pandas as pd
from core.market_data import get_current_regime


def detect_regime(df=None):
    """
    LEGACY WRAPPER; DO NOT ADD LOGIC.
    Returns canonical regime snapshot dict.
    """
    snap = get_current_regime("NIFTY")
    return {
        "regime": snap.get("primary_regime", "NEUTRAL"),
        **snap,
    }
