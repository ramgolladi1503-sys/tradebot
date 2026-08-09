def volatility_scaled_trend_strategy(symbol, ltp, vwap, atr, base_lot_size=15, target_risk_points=500, cross_assets=None):
    """Volatility-scaled trend strategy with mandatory cross-asset confirmation."""
    trades = []
    if not ltp or not vwap or not atr or atr <= 0:
        return trades
    if not isinstance(cross_assets, dict) or not cross_assets:
        return trades

    trend = (ltp - vwap) / vwap
    if trend > 0.0015:
        option_type = "CE"
        trend_direction = 1
    elif trend < -0.0015:
        option_type = "PE"
        trend_direction = -1
    else:
        return trades

    confirming_assets = 0
    valid_assets = 0
    for data in cross_assets.values():
        if not isinstance(data, dict):
            continue
        asset_ltp = data.get("ltp")
        asset_vwap = data.get("vwap")
        if not asset_ltp or not asset_vwap or asset_vwap <= 0:
            continue
        valid_assets += 1
        if trend_direction == 1 and asset_ltp > asset_vwap:
            confirming_assets += 1
        elif trend_direction == -1 and asset_ltp < asset_vwap:
            confirming_assets += 1
    if valid_assets == 0 or confirming_assets / valid_assets < 0.5:
        return trades

    strike = round(ltp / 100) * 100
    stop_points = atr * 1.5
    dynamic_lots = max(1, int(target_risk_points / stop_points))
    dynamic_qty = dynamic_lots * base_lot_size
    try:
        from config.config import MIN_PREMIUM, MAX_PREMIUM
        min_prem = MIN_PREMIUM
        max_prem = MAX_PREMIUM
    except Exception:
        min_prem = 40
        max_prem = 150

    entry_price = max(min(ltp * 0.004, max_prem), min_prem)
    stop_loss = round(entry_price * 0.8, 2)
    target = round(entry_price * 1.5, 2)
    predicted_edge_bps = min(50.0, max(5.0, abs(trend) * 10000))
    expected_holding_time_sec = max(300, int(3600 / (atr + 1e-9)))

    trades.append({
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "target": target,
        "lot_size": dynamic_qty,
        "confidence": 75,
        "reason": "Volatility Scaled Trend",
        "initial_predicted_edge": round(predicted_edge_bps, 2),
        "expected_holding_period": expected_holding_time_sec,
        "cross_asset_health": {
            "valid_assets": valid_assets,
            "confirming_assets": confirming_assets,
            "confirmation_rate": confirming_assets / valid_assets,
        },
    })
    return trades
