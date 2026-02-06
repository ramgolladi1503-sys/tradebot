# core/market_regime.py

from core.market_data import get_nifty_ltp, get_index_vwap

def detect_market_regime():
    """
    Returns:
        dict:
            regime (str)
            confidence (int 0–100)
            reason (str)
    """

    ltp = get_nifty_ltp()
    vwap = get_index_vwap("NIFTY")

    if not ltp or not vwap:
        return {
            "regime": "UNKNOWN",
            "confidence": 0,
            "reason": "Market data unavailable"
        }

    distance_pct = abs(ltp - vwap) / vwap * 100

    # -------- TREND DAY --------
    if distance_pct >= 0.35:
        direction = "UP" if ltp > vwap else "DOWN"
        return {
            "regime": "TREND_DAY",
            "confidence": 75,
            "reason": f"Price trending {direction} away from VWAP ({round(distance_pct,2)}%)"
        }

    # -------- BREAKOUT ATTEMPT --------
    if 0.20 <= distance_pct < 0.35:
        return {
            "regime": "BREAKOUT_ATTEMPT",
            "confidence": 60,
            "reason": f"VWAP expansion attempt ({round(distance_pct,2)}%)"
        }

    # -------- RANGE DAY (default) --------
    return {
        "regime": "RANGE_DAY",
        "confidence": 65,
        "reason": "Price oscillating near VWAP"
    }

