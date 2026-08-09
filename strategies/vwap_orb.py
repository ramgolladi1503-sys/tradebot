# strategies/vwap_orb.py


def _trend_confirmation(market_data, option_type):
    """Require explicit directional trend evidence; never infer it from VWAP alone."""
    raw = market_data.get("trend_confirmation")
    score = market_data.get("trend_score")
    direction = market_data.get("trend_direction")

    if isinstance(raw, dict):
        direction = raw.get("direction", direction)
        score = raw.get("score", score)
    elif isinstance(raw, str):
        direction = raw
    elif isinstance(raw, bool):
        if not raw:
            return False
        direction = "UP" if option_type == "CE" else "DOWN"

    try:
        score = float(score)
    except Exception:
        return False
    if score < 0.5:
        return False

    normalized = str(direction or "").strip().upper()
    if option_type == "CE":
        return normalized in {"UP", "BULL", "BULLISH", "BUY_CALL", "CE"}
    return normalized in {"DOWN", "BEAR", "BEARISH", "BUY_PUT", "PE"}


def vwap_orb_strategy(symbol, ltp, vwap, vwap_buffer=0.0015, market_data=None):
    """VWAP/ORB-style signal requiring independent trend and flow confirmation."""
    trades = []
    market_data = market_data or {}

    if not ltp or not vwap or vwap <= 0:
        return trades

    dealer_gamma = market_data.get("dealer_gamma_exposure")
    if dealer_gamma is None:
        return trades
    if dealer_gamma > 0:
        return trades

    cvd = market_data.get("cumulative_volume_delta")
    if cvd is None:
        return trades

    vpin_toxicity = market_data.get("vpin_toxicity")
    if vpin_toxicity is None:
        return trades
    min_vpin_threshold = market_data.get("min_vpin_threshold", 0.6)
    if vpin_toxicity < min_vpin_threshold:
        return trades

    if ltp > vwap * (1 + vwap_buffer):
        if cvd < 0:
            return trades
        option_type = "CE"
    elif ltp < vwap * (1 - vwap_buffer):
        if cvd > 0:
            return trades
        option_type = "PE"
    else:
        return trades

    if not _trend_confirmation(market_data, option_type):
        return trades

    strike = round(ltp / 100) * 100
    try:
        from config.config import MIN_PREMIUM, MAX_PREMIUM
        min_prem = MIN_PREMIUM
        max_prem = MAX_PREMIUM
    except Exception:
        min_prem = 40
        max_prem = 150

    entry_price = max(min(ltp * 0.004, max_prem), min_prem)
    stop_loss = round(entry_price * 0.8, 2)
    target = round(entry_price * 1.3, 2)

    trades.append({
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "target": target,
        "lot_size": 1,
        "confidence": 60,
        "trend_confirmation": True,
    })
    return trades
