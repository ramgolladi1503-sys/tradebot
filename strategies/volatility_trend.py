def volatility_scaled_trend_strategy(symbol, ltp, vwap, atr, base_lot_size=15, target_risk_points=500):
    """
    Elite Volatility-Scaled Trend Strategy
    Scales lot sizes inversely to volatility (ATR) to maintain constant mathematical risk.
    """
    trades = []
    
    if not ltp or not vwap or not atr or atr <= 0:
        return trades
        
    trend = (ltp - vwap) / vwap
    
    # Require at least 0.15% trend deviation to enter
    if trend > 0.0015:
        option_type = "CE"
    elif trend < -0.0015:
        option_type = "PE"
    else:
        return trades

    strike = round(ltp / 100) * 100
    
    # Risk parameters: 1.5x ATR stop loss
    stop_points = atr * 1.5
    
    # Volatility Scaling: Dynamically adjust lot size so risk is constant
    # Calculate how many lots we can buy to risk exactly `target_risk_points` total
    # Example: If ATR is high (stop_points = 200), we buy fewer lots. If ATR is low, we buy more.
    dynamic_lots = max(1, int(target_risk_points / stop_points))
    # We round to nearest multiple of base_lot_size (e.g., 15 for Bank Nifty)
    dynamic_qty = dynamic_lots * base_lot_size
    
    # Premium clamping
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
    target = round(entry_price * 1.5, 2)
    
    trades.append({
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "target": target,
        "lot_size": dynamic_qty,
        "confidence": 75,
        "reason": "Volatility Scaled Trend"
    })
    
    return trades
