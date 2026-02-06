# strategies/zero_hero.py

from core.market_calendar import next_expiry
from datetime import date

def _normalize_bias(bias):
    if not isinstance(bias, str):
        return None
    bias = bias.strip().lower()
    if bias in ("bullish", "bull", "long", "up"):
        return "bullish"
    if bias in ("bearish", "bear", "short", "down"):
        return "bearish"
    return None

def zero_hero_strategy(symbol, ltp, premarket_bias):
    """
    Zero-Hero logic for weekly expiry (Tuesday)
    Only generates manual approval trades
    """
    trades = []

    # Only on expiry day
    bias_norm = _normalize_bias(premarket_bias.get("bias") if isinstance(premarket_bias, dict) else premarket_bias)

    if bias_norm and date.today() == next_expiry(symbol):
        strike = round(ltp / 100) * 100
        option_type = "CE" if bias_norm == "bullish" else "PE"
        entry_price = max(ltp * 0.005, 25)      # small premium
        stop_loss = round(entry_price * 0.8, 2)
        target = round(entry_price * 2, 2)
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
