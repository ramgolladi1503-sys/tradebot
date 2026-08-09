from core.regime_router import resolve_strategy_regime, record_strategy_regime_path


def _update_debug(debug_stats, *, considered=0, rejected=0, scored=0, reason=None):
    if not isinstance(debug_stats, dict):
        return
    debug_stats["candidates_considered"] = int(debug_stats.get("candidates_considered", 0)) + int(considered)
    debug_stats["candidates_rejected_pre_score"] = int(debug_stats.get("candidates_rejected_pre_score", 0)) + int(rejected)
    debug_stats["candidates_scored"] = int(debug_stats.get("candidates_scored", 0)) + int(scored)
    counts = debug_stats.setdefault("rejection_reason_counts", {})
    if reason:
        counts[str(reason)] = int(counts.get(str(reason), 0)) + 1


_PROFILES = {
    "TRENDING_UP": {"setup_family": "BREAKOUT", "vwap_buffer_mult": 0.9, "min_move_mult": 0.9, "score_bias": 0.05, "trend_conflict_mult": 1.4},
    "TRENDING_DOWN": {"setup_family": "BREAKOUT", "vwap_buffer_mult": 0.9, "min_move_mult": 0.9, "score_bias": 0.05, "trend_conflict_mult": 1.4},
    "RANGE": {"setup_family": "MEAN_REVERSION", "vwap_buffer_mult": 1.15, "min_move_mult": 0.8, "score_bias": -0.02, "range_extension_mult": 1.2},
}
_ALLOWED_REGIMES = frozenset(_PROFILES)


def _normalize_bias(bias):
    if not isinstance(bias, str):
        return None
    bias = bias.strip().lower()
    if bias in ("bullish", "bull", "long", "up"):
        return "bullish"
    if bias in ("bearish", "bear", "short", "down"):
        return "bearish"
    return None


def generate_signal(ltp, vwap, bias, vwap_buffer=0.002, min_move=0.001, debug_stats=None, regime=None, expiry_context=False):
    """Canonical BANKNIFTY VWAP signal; rejected evidence never becomes a signal."""
    _update_debug(debug_stats, considered=1)
    if not ltp or not vwap or vwap <= 0:
        _update_debug(debug_stats, rejected=1, reason="missing_reference_price")
        return None

    bias_norm = _normalize_bias(bias)
    regime_name = resolve_strategy_regime(regime, bias=bias_norm, expiry_context=expiry_context)
    if regime_name not in _ALLOWED_REGIMES:
        _update_debug(debug_stats, rejected=1, reason="regime_not_declared_by_strategy_spec")
        return None
    profile = dict(_PROFILES[regime_name])
    profile["regime"] = regime_name
    record_strategy_regime_path("banknifty_intraday", regime_name, profile, debug_stats=debug_stats)

    vwap_buffer = float(vwap_buffer) * float(profile.get("vwap_buffer_mult", 1.0))
    min_move = float(min_move) * float(profile.get("min_move_mult", 1.0))
    diff = (float(ltp) - float(vwap)) / float(vwap)
    abs_diff = abs(diff)
    if abs_diff < float(min_move) * 0.65 or diff == 0:
        _update_debug(debug_stats, rejected=1, reason="move_too_small")
        return None

    direction = "BUY_CALL" if diff > 0 else "BUY_PUT"
    soft_flags = []
    if regime_name == "RANGE":
        if abs_diff < vwap_buffer * float(profile.get("range_extension_mult", 1.20)):
            _update_debug(debug_stats, rejected=1, reason="range_extension_too_small")
            return None
        direction = "BUY_PUT" if diff > 0 else "BUY_CALL"
        setup_type = "MEAN_REVERSION"
        reason = "VWAP mean reversion setup"
        score = 0.46 + min(0.26, abs_diff / max(vwap_buffer, 1e-6) * 0.08)
    else:
        setup_type = "BREAKOUT"
        reason = "VWAP directional setup"
        score = 0.50 + min(0.30, abs_diff / max(vwap_buffer, 1e-6) * 0.10)

    if abs_diff < vwap_buffer:
        score -= 0.08
        soft_flags.append("below_primary_vwap_buffer")
    if bias_norm is None:
        score -= 0.05
        soft_flags.append("bias_missing")
    elif (bias_norm == "bullish" and direction == "BUY_PUT") or (bias_norm == "bearish" and direction == "BUY_CALL"):
        if regime_name in {"TRENDING_UP", "TRENDING_DOWN"} and abs_diff < vwap_buffer * float(profile.get("trend_conflict_mult", 1.40)):
            _update_debug(debug_stats, rejected=1, reason="trend_regime_conflict")
            return None
        if abs_diff < vwap_buffer * 1.30:
            _update_debug(debug_stats, rejected=1, reason="bias_conflict_without_price_override")
            return None
        score -= 0.11
        soft_flags.append("bias_conflict_price_override")
    else:
        score += 0.04
        soft_flags.append("bias_aligned")

    score = max(0.05, min(0.95, score + float(profile.get("score_bias", 0.0))))
    _update_debug(debug_stats, scored=1)
    return {"direction": direction, "reason": reason, "score": round(score, 3), "soft_flags": soft_flags, "setup_type": setup_type, "regime_path": regime_name}


__all__ = ["generate_signal"]
