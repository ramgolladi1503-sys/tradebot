from core.regime_router import get_strategy_regime_profile, record_strategy_regime_path, resolve_strategy_regime
from strategies.soft_signal import soft_signal


def _update_debug(debug_stats, *, considered=0, rejected=0, scored=0, reason=None):
    if not isinstance(debug_stats, dict):
        return
    debug_stats["candidates_considered"] = int(debug_stats.get("candidates_considered", 0)) + int(considered)
    debug_stats["candidates_rejected_pre_score"] = int(
        debug_stats.get("candidates_rejected_pre_score", 0)
    ) + int(rejected)
    debug_stats["candidates_scored"] = int(debug_stats.get("candidates_scored", 0)) + int(scored)
    counts = debug_stats.setdefault("rejection_reason_counts", {})
    if reason:
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

def generate_signal(ltp, vwap, bias, vwap_buffer=0.0015, min_move=0.001, debug_stats=None, regime=None, expiry_context=False):
    """
    Sensex intraday signal with VWAP context and soft bias preference.
    """
    _update_debug(debug_stats, considered=1)
    if not ltp or not vwap or vwap <= 0:
        _update_debug(debug_stats, rejected=1, reason="missing_reference_price")
        return None

    bias_norm = _normalize_bias(bias)
    regime_name = resolve_strategy_regime(regime, bias=bias_norm, expiry_context=expiry_context)
    profile = get_strategy_regime_profile("sensex_intraday", regime_name)
    record_strategy_regime_path("sensex_intraday", regime_name, profile, debug_stats=debug_stats)
    vwap_buffer = float(vwap_buffer) * float(profile.get("vwap_buffer_mult", 1.0))
    min_move = float(min_move) * float(profile.get("min_move_mult", 1.0))
    diff = (ltp - vwap) / vwap
    abs_diff = abs(diff)
    weak_move_floor = float(min_move) * 0.6
    if abs_diff < weak_move_floor:
        _update_debug(debug_stats, rejected=1, reason="move_too_small")
        direction = "BUY_CALL" if diff >= 0 else "BUY_PUT"
        return soft_signal(
            reason="move_too_small",
            direction=direction,
            setup_type="SOFT_REJECT",
            regime_path=regime_name,
        )

    if diff == 0:
        _update_debug(debug_stats, rejected=1, reason="flat_vs_vwap")
        direction = "BUY_CALL"
        return soft_signal(
            reason="flat_vs_vwap",
            direction=direction,
            setup_type="SOFT_REJECT",
            regime_path=regime_name,
        )

    setup_type = str(profile.get("setup_family") or "BREAKOUT")
    direction = "BUY_CALL" if diff > 0 else "BUY_PUT"
    soft_flags = []
    reason = "VWAP directional setup"
    if regime_name == "RANGE":
        if abs_diff < (vwap_buffer * float(profile.get("range_extension_mult", 1.15))):
            _update_debug(debug_stats, rejected=1, reason="range_extension_too_small")
            return None
        direction = "BUY_PUT" if diff > 0 else "BUY_CALL"
        setup_type = "MEAN_REVERSION"
        reason = "VWAP mean reversion setup"
        soft_flags.append("breakout_suppressed_range_regime")
        score = 0.43 + min(0.27, abs_diff / max(vwap_buffer, 1e-6) * 0.08)
    else:
        score = 0.47 + min(0.30, abs_diff / max(vwap_buffer, 1e-6) * 0.10)
        if regime_name == "VOLATILE":
            if abs_diff < (vwap_buffer * float(profile.get("strict_move_mult", 1.15))):
                _update_debug(debug_stats, rejected=1, reason="volatile_move_too_small")
                return None
            soft_flags.append("volatile_regime_path")
        elif regime_name == "EXPIRY_CONTEXT":
            soft_flags.append("expiry_context_path")
        else:
            soft_flags.append(f"regime_{regime_name.lower()}")
    if abs_diff < vwap_buffer:
        soft_flags.append("below_primary_vwap_buffer")
        score -= 0.08
    if bias_norm is None:
        soft_flags.append("bias_missing")
        score -= 0.05
    elif (bias_norm == "bullish" and direction == "BUY_PUT") or (
        bias_norm == "bearish" and direction == "BUY_CALL"
    ):
        if regime_name in {"TRENDING_UP", "TRENDING_DOWN"} and abs_diff < (vwap_buffer * float(profile.get("trend_conflict_mult", 1.40))):
            _update_debug(debug_stats, rejected=1, reason="trend_regime_conflict")
            return soft_signal(
                reason="trend_regime_conflict",
                direction=direction,
                setup_type="SOFT_REJECT",
                regime_path=regime_name,
            )
        if abs_diff < (vwap_buffer * 1.35):
            _update_debug(debug_stats, rejected=1, reason="bias_conflict_without_price_override")
            return None
        soft_flags.append("bias_conflict_price_override")
        score -= 0.10
    else:
        soft_flags.append("bias_aligned")
        score += 0.04

    score += float(profile.get("score_bias", 0.0))
    score = max(0.05, min(0.95, score))
    _update_debug(debug_stats, scored=1)
    return {
        "direction": direction,
        "reason": reason,
        "score": round(score, 3),
        "soft_flags": soft_flags,
        "setup_type": setup_type,
        "regime_path": regime_name,
    }
