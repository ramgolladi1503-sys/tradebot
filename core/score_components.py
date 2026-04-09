def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def compute_final_score(candidate):
    c = candidate or {}
    signal_score = _safe_float(c.get("signal_score"), c.get("builder_confidence", 0.0))
    regime_score = _safe_float(c.get("regime_score"), c.get("regime_alignment", 0.0))
    execution_score = _safe_float(c.get("execution_score"), c.get("execution_quality_score", 0.0))
    liquidity_score = _safe_float(c.get("liquidity_score"), c.get("liquidity_quality", 0.0))
    risk_reward_score = _safe_float(c.get("risk_reward_score"), c.get("risk_adjusted_quality", 0.0))
    return (
        0.35 * signal_score
        + 0.20 * regime_score
        + 0.20 * execution_score
        + 0.15 * liquidity_score
        + 0.10 * risk_reward_score
    )
