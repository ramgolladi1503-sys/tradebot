# strategies/zero_hero.py

from datetime import date

from config import config as cfg
from core.market_calendar import next_expiry
from core.regime_router import resolve_strategy_regime, record_strategy_regime_path



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

_PROFILES = {
    "TRENDING_UP": {'setup_family': 'BREAKOUT', 'vwap_buffer_mult': 0.9, 'min_move_mult': 0.9, 'score_bias': 0.05, 'range_reversion': False, 'trend_conflict_mult': 1.4, 'variant': 'non_expiry_context', 'entry_price_mult': 0.0035, 'premium_floor': 15.0, 'target_mult': 1.6, 'stop_loss_mult': 0.85, 'confidence': 46, 'confidence_reason': 'non_expiry_manual_advisory'},
    "TRENDING_DOWN": {'setup_family': 'BREAKOUT', 'vwap_buffer_mult': 0.9, 'min_move_mult': 0.9, 'score_bias': 0.05, 'range_reversion': False, 'trend_conflict_mult': 1.4, 'variant': 'non_expiry_context', 'entry_price_mult': 0.0035, 'premium_floor': 15.0, 'target_mult': 1.6, 'stop_loss_mult': 0.85, 'confidence': 46, 'confidence_reason': 'non_expiry_manual_advisory'},
    "RANGE": {'setup_family': 'MEAN_REVERSION', 'vwap_buffer_mult': 1.15, 'min_move_mult': 0.8, 'score_bias': -0.01, 'range_reversion': True, 'range_extension_mult': 1.2},
    "VOLATILE": {'setup_family': 'CONTINUATION', 'vwap_buffer_mult': 1.35, 'min_move_mult': 1.25, 'score_bias': -0.04, 'range_reversion': False, 'strict_move_mult': 1.15, 'variant': 'non_expiry_context', 'entry_price_mult': 0.003, 'premium_floor': 18.0, 'target_mult': 1.5, 'stop_loss_mult': 0.88, 'confidence': 42, 'confidence_reason': 'non_expiry_volatile_manual_advisory'},
    "EXPIRY_CONTEXT": {'setup_family': 'PULLBACK', 'vwap_buffer_mult': 1.0, 'min_move_mult': 0.85, 'score_bias': 0.02, 'range_reversion': False, 'variant': 'expiry_context', 'entry_price_mult': 0.005, 'premium_floor': 25.0, 'target_mult': 2.0, 'stop_loss_mult': 0.8, 'confidence': 60, 'confidence_reason': 'expiry_window_manual_advisory'},
}

def _normalize_bias(bias):
    if not isinstance(bias, str):
        return None
    bias = bias.strip().lower()
    if bias in ("bullish", "bull", "long", "up"):
        return "bullish"
    if bias in ("bearish", "bear", "short", "down"):
        return "bearish"
    return None

def zero_hero_strategy(symbol, ltp, premarket_bias, current_date=None, expiry_window_days=None, debug_stats=None, regime=None):
    """Zero-Hero weekly-expiry advisory logic."""
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

    window_days = int(expiry_window_days if expiry_window_days is not None else getattr(cfg, "ZERO_HERO_EXPIRY_WINDOW_DAYS", 1))
    days_to_expiry = (expiry - today).days
    expiry_context = 0 <= days_to_expiry <= max(0, window_days)
    if not expiry_context and not bool(getattr(cfg, "ZERO_HERO_ALLOW_NON_EXPIRY_CONTEXT", True)):
        _update_debug(debug_stats, rejected=1, reason="outside_expiry_window")
        return trades
    regime_name = resolve_strategy_regime(regime, bias=bias_norm, expiry_context=expiry_context)
    profile = dict(_PROFILES.get(regime_name, _PROFILES["TRENDING_UP"]))
    profile["regime"] = regime_name
    if not expiry_context and regime_name not in {"TRENDING_UP", "TRENDING_DOWN", "VOLATILE"}:
        regime_name = "TRENDING_DOWN" if bias_norm == "bearish" else "TRENDING_UP"
        profile = dict(_PROFILES.get(regime_name, _PROFILES["TRENDING_UP"]))
    profile["regime"] = regime_name
    if not expiry_context:
        profile = dict(profile)
        profile["premium_floor"] = float(getattr(cfg, "ZERO_HERO_NON_EXPIRY_PREMIUM_FLOOR", profile.get("premium_floor", 15.0)))
        profile["entry_price_mult"] = float(getattr(cfg, "ZERO_HERO_NON_EXPIRY_ENTRY_MULT", profile.get("entry_price_mult", 0.0035)))
        profile["target_mult"] = float(getattr(cfg, "ZERO_HERO_NON_EXPIRY_TARGET_MULT", profile.get("target_mult", 1.6)))
        profile["stop_loss_mult"] = float(getattr(cfg, "ZERO_HERO_NON_EXPIRY_STOP_MULT", profile.get("stop_loss_mult", 0.85)))
        profile["confidence"] = int(getattr(cfg, "ZERO_HERO_NON_EXPIRY_CONFIDENCE", profile.get("confidence", 46)))
        profile.setdefault("variant", "non_expiry_context")
        profile.setdefault("confidence_reason", "non_expiry_manual_advisory")
    record_strategy_regime_path("zero_hero", regime_name, profile, debug_stats=debug_stats)
    if isinstance(debug_stats, dict):
        debug_stats["zero_hero_activation_window"] = {
            "strategy": "ZERO_HERO",
            "variant": str(profile.get("variant") or "manual_expiry_window"),
            "days_to_expiry": days_to_expiry,
            "expiry_window_days": max(0, window_days),
        }

    strike = round(float(ltp) / 100) * 100
    option_type = "CE" if bias_norm == "bullish" else "PE"
    entry_price = max(float(ltp) * float(profile.get("entry_price_mult", 0.005)), float(profile.get("premium_floor", 25.0)))
    stop_loss = round(entry_price * float(profile.get("stop_loss_mult", 0.8)), 2)
    target = round(entry_price * float(profile.get("target_mult", 2.0)), 2)

    trades.append({
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "target": target,
        "lot_size": 1,
        "confidence": int(profile.get("confidence", 60)),
        "confidence_reason": str(profile.get("confidence_reason", "expiry_window_manual_advisory")),
        "regime_path": regime_name,
        "variant": str(profile.get("variant") or "manual_expiry_window"),
    })
    if isinstance(debug_stats, dict):
        debug_stats["zero_hero_selected_premium_band"] = {
            "strategy": "ZERO_HERO",
            "variant": str(profile.get("variant") or "manual_expiry_window"),
            "low": float(profile.get("premium_floor", 25.0)),
            "high": round(float(entry_price), 2),
            "source": "manual_fixed_premium",
        }
        debug_stats["zero_hero_rejected_reason"] = None
    _update_debug(debug_stats, scored=1)
    return trades


def generate_signal(symbol, ltp, premarket_bias, current_date=None, expiry_window_days=None, debug_stats=None, regime=None):
    """Canonical registry entrypoint; delegates without changing Zero-Hero semantics."""
    return zero_hero_strategy(
        symbol,
        ltp,
        premarket_bias,
        current_date=current_date,
        expiry_window_days=expiry_window_days,
        debug_stats=debug_stats,
        regime=regime,
    )


__all__ = ["zero_hero_strategy", "generate_signal"]
