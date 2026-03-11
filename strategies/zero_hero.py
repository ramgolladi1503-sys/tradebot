# strategies/zero_hero.py

from datetime import date

from config import config as cfg
from core.market_calendar import next_expiry


def _update_debug(debug_stats, *, considered=0, rejected=0, scored=0, reason=None):
    if not isinstance(debug_stats, dict):
        return
    debug_stats["zero_hero_considered"] = int(debug_stats.get("zero_hero_considered", 0)) + int(considered)
    debug_stats["candidates_considered"] = int(debug_stats.get("candidates_considered", 0)) + int(considered)
    debug_stats["candidates_rejected_pre_score"] = int(
        debug_stats.get("candidates_rejected_pre_score", 0)
    ) + int(rejected)
    debug_stats["candidates_scored"] = int(debug_stats.get("candidates_scored", 0)) + int(scored)
    counts = debug_stats.setdefault("rejection_reason_counts", {})
    if reason:
        debug_stats["zero_hero_rejected_reason"] = str(reason)
        counts[str(reason)] = int(counts.get(str(reason), 0)) + 1

def _normalize_bias(bias):
    if not isinstance(bias, str):
        return None
    bias = bias.strip().lower()
    if bias in ("bullish", "bull", "long", "up"):
        return "bullish"
    if bias in ("bearish", "bear", "short", "down"):
        return "bearish"
    return None

def zero_hero_strategy(symbol, ltp, premarket_bias, current_date=None, expiry_window_days=None, debug_stats=None):
    """
    Zero-Hero logic for weekly expiry.
    Only generates manual approval trades
    """
    _update_debug(debug_stats, considered=1)
    trades = []
    if ltp is None or float(ltp or 0) <= 0:
        _update_debug(debug_stats, rejected=1, reason="invalid_ltp")
        return trades

    bias_norm = _normalize_bias(premarket_bias.get("bias") if isinstance(premarket_bias, dict) else premarket_bias)
    if bias_norm is None:
        _update_debug(debug_stats, rejected=1, reason="missing_bias")
        return trades

    today = current_date or date.today()
    expiry = next_expiry(symbol)
    if not expiry:
        _update_debug(debug_stats, rejected=1, reason="expiry_unavailable")
        return trades

    window_days = int(
        expiry_window_days
        if expiry_window_days is not None
        else getattr(cfg, "ZERO_HERO_EXPIRY_WINDOW_DAYS", 1)
    )
    days_to_expiry = (expiry - today).days
    if days_to_expiry < 0 or days_to_expiry > max(0, window_days):
        _update_debug(debug_stats, rejected=1, reason="outside_expiry_window")
        return trades
    if isinstance(debug_stats, dict):
        debug_stats["zero_hero_activation_window"] = {
            "strategy": "ZERO_HERO",
            "variant": "manual_expiry_window",
            "days_to_expiry": days_to_expiry,
            "expiry_window_days": max(0, window_days),
        }

    strike = round(float(ltp) / 100) * 100
    option_type = "CE" if bias_norm == "bullish" else "PE"
    entry_price = max(float(ltp) * 0.005, 25)
    stop_loss = round(entry_price * 0.8, 2)
    target = round(entry_price * 2, 2)
    lot_size = 1

    trades.append(
        {
            "symbol": symbol,
            "strike": strike,
            "option_type": option_type,
            "entry_price": round(entry_price, 2),
            "stop_loss": stop_loss,
            "target": target,
            "lot_size": lot_size,
            "confidence": 60,
            "confidence_reason": "expiry_window_manual_advisory",
        }
    )
    if isinstance(debug_stats, dict):
        debug_stats["zero_hero_selected_premium_band"] = {
            "strategy": "ZERO_HERO",
            "variant": "manual_expiry_window",
            "low": 25.0,
            "high": round(float(entry_price), 2),
            "source": "manual_fixed_premium",
        }
        debug_stats["zero_hero_rejected_reason"] = None
    _update_debug(debug_stats, scored=1)

    return trades
