from config import config as cfg
from core.market_data import get_ltp


def calculate_premarket_bias():
    score = 0
    ltp_snapshot = {}
    thresholds = dict(getattr(cfg, "PREMARKET_INDICES_CLOSE", {}) or {})
    required_symbols = ("NIFTY", "BANKNIFTY")
    missing_symbols = []

    for idx in dict(getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}):
        price = get_ltp(idx)
        ltp_snapshot[idx] = price
        if price is None:
            print(f"LTP unavailable (empty response) for {idx}")

    for symbol in required_symbols:
        if ltp_snapshot.get(symbol) is None:
            missing_symbols.append(symbol)

    if missing_symbols:
        return {
            "bias": "NEUTRAL",
            "score": 0,
            "reason": "missing_required_ltp",
            "missing_symbols": missing_symbols,
            "ltp_snapshot": ltp_snapshot,
        }

    if float(ltp_snapshot.get("NIFTY") or 0.0) > float(thresholds.get("NIFTY", 16000)):
        score += 1
    if float(ltp_snapshot.get("BANKNIFTY") or 0.0) > float(thresholds.get("BANKNIFTY", 40000)):
        score += 1

    if score == 2:
        bias = "BULLISH"
    elif score == 1:
        bias = "NEUTRAL"
    else:
        bias = "BEARISH"

    return {
        "bias": bias,
        "score": score,
        "reason": None,
        "missing_symbols": [],
        "ltp_snapshot": ltp_snapshot,
    }
