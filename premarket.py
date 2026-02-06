from config.config import PREMARKET_INDICES_LTP
from core.market_data import get_ltp

def calculate_premarket_bias():
    score = 0

    # Fetch LTPs only for tradable symbols
    for idx in PREMARKET_INDICES_LTP:
        price = get_ltp(idx)
        PREMARKET_INDICES_LTP[idx] = price if price else 0
        if price is None:
            print(f"LTP unavailable (empty response) for {idx}")

    # Example scoring
    if PREMARKET_INDICES_LTP.get("NIFTY", 0) > 16000: score += 1
    if PREMARKET_INDICES_LTP.get("BANKNIFTY", 0) > 40000: score += 1

    # Bias
    if score == 2:
        bias = "BULLISH"
    elif score == 1:
        bias = "NEUTRAL"
    else:
        bias = "BEARISH"

    return {"bias": bias, "score": score}

