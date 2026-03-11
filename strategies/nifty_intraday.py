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

def generate_signal(ltp, vwap, bias, vwap_buffer=0.0015, min_move=0.001, debug_stats=None):
    """
    Nifty intraday signal using VWAP context with bias as a quality input, not a hard gate.
    """
    _update_debug(debug_stats, considered=1)
    if not ltp or not vwap or vwap <= 0:
        _update_debug(debug_stats, rejected=1, reason="missing_reference_price")
        return None

    bias_norm = _normalize_bias(bias)
    diff = (ltp - vwap) / vwap
    abs_diff = abs(diff)
    weak_move_floor = float(min_move) * 0.6
    if abs_diff < weak_move_floor:
        _update_debug(debug_stats, rejected=1, reason="move_too_small")
        return None

    if diff == 0:
        _update_debug(debug_stats, rejected=1, reason="flat_vs_vwap")
        return None

    direction = "BUY_CALL" if diff > 0 else "BUY_PUT"
    soft_flags = []
    score = 0.48 + min(0.32, abs_diff / max(vwap_buffer, 1e-6) * 0.10)
    if abs_diff < vwap_buffer:
        soft_flags.append("below_primary_vwap_buffer")
        score -= 0.08
    if bias_norm is None:
        soft_flags.append("bias_missing")
        score -= 0.05
    elif (bias_norm == "bullish" and direction == "BUY_PUT") or (
        bias_norm == "bearish" and direction == "BUY_CALL"
    ):
        if abs_diff < (vwap_buffer * 1.35):
            _update_debug(debug_stats, rejected=1, reason="bias_conflict_without_price_override")
            return None
        soft_flags.append("bias_conflict_price_override")
        score -= 0.10
    else:
        soft_flags.append("bias_aligned")
        score += 0.04

    score = max(0.05, min(0.95, score))
    _update_debug(debug_stats, scored=1)
    return {
        "direction": direction,
        "reason": "VWAP directional setup",
        "score": round(score, 3),
        "soft_flags": soft_flags,
    }
