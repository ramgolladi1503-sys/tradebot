# core/premarket.py

from config.config import PREMARKET_INDICES_LTP, PREMARKET_INDICES_CLOSE
from core.market_data import get_ltp

def calculate_premarket_bias():
    score = 0
    prices = {}

    for idx in PREMARKET_INDICES_LTP:
        price = get_ltp(idx)
        if price is None:
            price = PREMARKET_INDICES_CLOSE[idx]
            print(f"Using fallback close for {idx}: {price}")
        prices[idx] = price

    # Simple scoring logic
    if prices.get("NIFTY", 0) > 16000: score += 1

    if score == 1:
        bias = "BULLISH"
    else:
        bias = "NEUTRAL"

    return {"bias": bias, "score": score, "prices": prices}

