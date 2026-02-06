def _normalize_bias(bias):
    if not isinstance(bias, str):
        return None
    bias = bias.strip().lower()
    if bias in ("bullish", "bull", "long", "up"):
        return "bullish"
    if bias in ("bearish", "bear", "short", "down"):
        return "bearish"
    return None

def generate_signal(ltp, vwap, bias, vwap_buffer=0.0015, min_move=0.001):
    """
    Nifty intraday signal using bias + VWAP buffer to avoid noise.
    """
    if not ltp or not vwap or vwap <= 0:
        return None

    bias_norm = _normalize_bias(bias)
    diff = (ltp - vwap) / vwap

    if bias_norm == "bullish" and diff >= vwap_buffer and abs(diff) >= min_move:
        return {"direction": "BUY_CALL", "reason": "Bullish bias + VWAP strength"}
    if bias_norm == "bearish" and diff <= -vwap_buffer and abs(diff) >= min_move:
        return {"direction": "BUY_PUT", "reason": "Bearish bias + VWAP weakness"}
    return None
