"""Pairs Trading Arbitrage Strategy implementation."""

from core.regime_router import resolve_strategy_regime
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


def generate_signal(spread_z, min_zscore=2.0, debug_stats=None, regime=None, expiry_context=False, **kwargs):
    """
    Pairs arbitrage signal based on spread z-score and ADF cointegration.
    """
    _update_debug(debug_stats, considered=1)
    
    if spread_z is None:
        _update_debug(debug_stats, rejected=1, reason="missing_spread_zscore")
        return None

    # Elite 10/10 ADF Cointegration Check
    # If the spread is not stationary (p-value > 0.05), we refuse to trade it
    # as the statistical relationship is broken.
    adf_pvalue = kwargs.get('adf_pvalue', 1.0) if kwargs else 1.0
    if adf_pvalue > 0.05:
        _update_debug(debug_stats, rejected=1, reason="spread_not_cointegrated")
        return None

    # Elite 10/10 OU Half-Life Check
    # If the mean reversion takes too long, we will die to theta decay.
    # Assuming 5-minute candles, 36 periods = 3 hours. Reject if > 36.
    ou_half_life = kwargs.get('ou_half_life', 0.0) if kwargs else 0.0
    max_half_life_periods = kwargs.get('max_half_life_periods', 36.0) if kwargs else 36.0
    if ou_half_life > max_half_life_periods or ou_half_life == float('inf'):
        _update_debug(debug_stats, rejected=1, reason="half_life_too_long")
        return None

    hedge_ratio = kwargs.get('hedge_ratio', 1.0) if kwargs else 1.0

    regime_name = resolve_strategy_regime(regime, bias=None, expiry_context=expiry_context)
    
    abs_z = abs(spread_z)
    if abs_z < min_zscore:
        _update_debug(debug_stats, rejected=1, reason="zscore_too_small")
        return None

    direction = "SELL_SPREAD" if spread_z > 0 else "BUY_SPREAD"
    setup_type = "STATISTICAL_ARBITRAGE"
    reason = "Spread Z-Score Divergence"
    soft_flags = []
    
    # Scale score from 0.6 to 0.95 based on zscore
    score = 0.6 + min(0.35, (abs_z - min_zscore) * 0.1)
    
    if abs_z > 3.5:
        soft_flags.append("extreme_divergence")
        score -= 0.1 # Penalty for potential structural break
        
    soft_flags.append(f"regime_{regime_name.lower()}")
    
    score = max(0.05, min(0.95, score))
    _update_debug(debug_stats, scored=1)
    
    return {
        "direction": direction,
        "reason": reason,
        "score": round(score, 3),
        "soft_flags": soft_flags,
        "setup_type": setup_type,
        "regime_path": regime_name,
        "hedge_ratio": round(hedge_ratio, 4),
    }
