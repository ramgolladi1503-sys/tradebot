# core/probability_engine.py

from datetime import datetime
from core.market_data import get_nifty_ltp, get_index_vwap

def calculate_trade_probability(trade, regime_info):
    score = 0
    reasons = []

    # ----------------------------
    # 1. Trend strength (0–25)
    # ----------------------------
    ltp = get_nifty_ltp()
    vwap = get_index_vwap("NIFTY")

    if ltp and vwap:
        distance_pct = abs(ltp - vwap) / vwap * 100

        if distance_pct >= 0.4:
            score += 25
            reasons.append("Strong VWAP separation")
        elif distance_pct >= 0.25:
            score += 18
            reasons.append("Moderate VWAP separation")
        else:
            score += 8
            reasons.append("Weak VWAP separation")

    # ----------------------------
    # 2. Regime quality (0–20)
    # ----------------------------
    if regime_info["regime"] == "TREND_DAY":
        score += 20
        reasons.append("Trend day")
    elif regime_info["regime"] == "BREAKOUT_ATTEMPT":
        score += 12
        reasons.append("Breakout attempt")

    # ----------------------------
    # 3. Time-of-day edge (0–15)
    # ----------------------------
    now = datetime.now().time()

    if now.hour in [10, 14, 15]:
        score += 15
        reasons.append("High-probability trading hour")
    elif now.hour == 11:
        score += 8
        reasons.append("Decent time window")
    else:
        score += 3
        reasons.append("Low-quality time window")

    # ----------------------------
    # 4. Option quality (0–20)
    # ----------------------------
    entry = trade["entry"]

    if 60 <= entry <= 200:
        score += 20
        reasons.append("Healthy premium zone")
    elif 40 <= entry < 60 or 200 < entry <= 300:
        score += 12
        reasons.append("Acceptable premium zone")
    else:
        score += 5
        reasons.append("Poor premium quality")

    # ----------------------------
    # 5. Risk–Reward (0–20)
    # ----------------------------
    rr = (trade["target"] - trade["entry"]) / (trade["entry"] - trade["stop_loss"])

    if rr >= 1.5:
        score += 20
        reasons.append("Excellent R:R")
    elif rr >= 1.0:
        score += 12
        reasons.append("Acceptable R:R")
    else:
        score += 4
        reasons.append("Poor R:R")

    return {
        "score": min(score, 100),
        "reasons": reasons
    }

