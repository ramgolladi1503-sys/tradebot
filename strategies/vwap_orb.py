# strategies/vwap_orb.py

def vwap_orb_strategy(symbol, ltp, vwap, vwap_buffer=0.0015, market_data=None):
    """
    VWAP + ORB confirmation strategy with Elite GEX and CVD Filtering
    """
    trades = []
    market_data = market_data or {}

    if not ltp or not vwap or vwap <= 0:
        return trades

    # Elite 10/10 GEX Filter: Hard-lock if Positive Gamma
    dealer_gamma = market_data.get("dealer_gamma_exposure", 0)
    if dealer_gamma > 0:
        # Veto the trade: Positive gamma suppresses volatility and destroys ORBs
        return trades

    # Elite 10/10 CVD Filter: Volume must support the breakout
    cvd = market_data.get("cumulative_volume_delta", 0)

    # VWAP buffer to reduce noise
    if ltp > vwap * (1 + vwap_buffer):
        if cvd < 0:
            return trades  # Veto: Fake breakout without volume backing
        option_type = "CE"
    elif ltp < vwap * (1 - vwap_buffer):
        if cvd > 0:
            return trades  # Veto: Fake breakdown without volume backing
        option_type = "PE"
    else:
        return trades  # no signal

    strike = round(ltp / 100) * 100
    # Clamp entry to a realistic premium band if available
    try:
        from config.config import MIN_PREMIUM, MAX_PREMIUM
        min_prem = MIN_PREMIUM
        max_prem = MAX_PREMIUM
    except Exception:
        min_prem = 40
        max_prem = 150

    entry_price = ltp * 0.004
    entry_price = max(entry_price, min_prem)
    entry_price = min(entry_price, max_prem)
    stop_loss = round(entry_price * 0.8, 2)
    target = round(entry_price * 1.3, 2)
    lot_size = 1

    trades.append({
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "target": target,
        "lot_size": lot_size,
        "confidence": 60
    })

    return trades
