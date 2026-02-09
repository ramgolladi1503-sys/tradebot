# core/no_trade_engine.py

from datetime import time
from core.time_utils import now_ist
from core.market_data import get_nifty_ltp, get_index_vwap

def check_no_trade_conditions():
    """
    Returns:
        dict:
            allowed (bool)
            reason (str)
    """

    now = now_ist().time()

    # -------- Rule 1: Early market noise --------
    if now < time(10, 15):
        return {
            "allowed": False,
            "reason": "Market too early (<10:15 AM)"
        }

    # -------- Rule 2: Midday chop --------
    if time(11, 30) <= now <= time(13, 30):
        return {
            "allowed": False,
            "reason": "Midday chop window (11:30–1:30)"
        }

    nifty_ltp = get_nifty_ltp()
    vwap = get_index_vwap("NIFTY")

    if not nifty_ltp or not vwap:
        return {
            "allowed": False,
            "reason": "Market data unavailable"
        }

    # -------- Rule 3: Flat VWAP (no momentum) --------
    vwap_distance = abs(nifty_ltp - vwap) / nifty_ltp * 100

    if vwap_distance < 0.15:
        return {
            "allowed": False,
            "reason": "Price hugging VWAP (no momentum)"
        }

    # -------- Passed all checks --------
    return {
        "allowed": True,
        "reason": "Trade allowed"
    }
