def _normalize_bias(bias):
    if not isinstance(bias, str):
        return None
    bias = bias.strip().lower()
    if bias in ("bullish", "bull", "long", "up"):
        return "bullish"
    if bias in ("bearish", "bear", "short", "down"):
        return "bearish"
    return None

def generate_signal(ltp, vwap, bias, vwap_buffer=0.002, min_move=0.001):
    """
    BankNifty intraday signal using VWAP buffer + bias confirmation.
    """
    if not ltp or not vwap or vwap <= 0:
        return None

    bias_norm = _normalize_bias(bias)
    diff = (ltp - vwap) / vwap

    if bias_norm == "bullish" and diff >= vwap_buffer and abs(diff) >= min_move:
        return {"direction": "BUY_CALL", "reason": "Strong momentum above VWAP"}
    if bias_norm == "bearish" and diff <= -vwap_buffer and abs(diff) >= min_move:
        return {"direction": "BUY_PUT", "reason": "Strong breakdown below VWAP"}
    return None
