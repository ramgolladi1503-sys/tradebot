"""Pairs Trading Arbitrage Strategy implementation.

The implementation is fail-closed on stale legs, missing aligned history, and
unavailable stationarity evidence. It never substitutes a mock ADF pass.
"""

from core.regime_router import resolve_strategy_regime
from core.math.kalman_filter import KalmanFilter
from core.math.mean_reversion import calculate_ou_half_life
import numpy as np


def _update_debug(debug_stats, *, considered=0, rejected=0, scored=0, reason=None):
    if not isinstance(debug_stats, dict):
        return
    debug_stats["candidates_considered"] = int(debug_stats.get("candidates_considered", 0)) + int(considered)
    debug_stats["candidates_rejected_pre_score"] = int(debug_stats.get("candidates_rejected_pre_score", 0)) + int(rejected)
    debug_stats["candidates_scored"] = int(debug_stats.get("candidates_scored", 0)) + int(scored)
    counts = debug_stats.setdefault("rejection_reason_counts", {})
    if reason:
        counts[str(reason)] = int(counts.get(str(reason), 0)) + 1


def _fresh_leg(age, max_age):
    try:
        age = float(age)
        max_age = float(max_age)
    except Exception:
        return False
    return np.isfinite(age) and np.isfinite(max_age) and 0.0 <= age <= max_age


def generate_signal(
    price_a,
    price_b,
    historical_a=None,
    historical_b=None,
    min_zscore=2.0,
    debug_stats=None,
    regime=None,
    expiry_context=False,
    leg_a_age_sec=None,
    leg_b_age_sec=None,
    max_leg_age_sec=5.0,
    **kwargs,
):
    """Pairs signal with explicit spread, hedge-ratio, stationarity and freshness truth."""
    _update_debug(debug_stats, considered=1)

    if price_a is None or price_b is None:
        _update_debug(debug_stats, rejected=1, reason="missing_prices")
        return None
    if not _fresh_leg(leg_a_age_sec, max_leg_age_sec) or not _fresh_leg(leg_b_age_sec, max_leg_age_sec):
        _update_debug(debug_stats, rejected=1, reason="stale_or_missing_leg_freshness")
        return None
    if historical_a is None or historical_b is None:
        _update_debug(debug_stats, rejected=1, reason="missing_aligned_history")
        return None
    if len(historical_a) != len(historical_b):
        _update_debug(debug_stats, rejected=1, reason="unaligned_history_lengths")
        return None
    if len(historical_a) < 9:
        _update_debug(debug_stats, rejected=1, reason="insufficient_history")
        return None

    kf = KalmanFilter()
    spreads = []
    for a, b in zip(historical_a, historical_b):
        hr, intercept, _ = kf.update(a, b)
        spreads.append(a - (hr * b + intercept))

    hedge_ratio, intercept, _ = kf.update(price_a, price_b)
    if not np.isfinite(float(hedge_ratio)) or not np.isfinite(float(intercept)):
        _update_debug(debug_stats, rejected=1, reason="invalid_beta_truth")
        return None
    current_spread = price_a - (hedge_ratio * price_b + intercept)
    spreads.append(current_spread)

    spreads_arr = np.asarray(spreads, dtype=float)
    if not np.all(np.isfinite(spreads_arr)) or float(np.std(spreads_arr)) <= 1e-12:
        _update_debug(debug_stats, rejected=1, reason="invalid_spread_truth")
        return None
    spread_z = float((current_spread - np.mean(spreads_arr)) / np.std(spreads_arr))

    try:
        from statsmodels.tsa.stattools import adfuller
        adf_pvalue = float(adfuller(spreads_arr)[1])
    except Exception:
        _update_debug(debug_stats, rejected=1, reason="cointegration_truth_unavailable")
        return None
    if not np.isfinite(adf_pvalue) or adf_pvalue > 0.05:
        _update_debug(debug_stats, rejected=1, reason="spread_not_cointegrated")
        return None

    ou_half_life = calculate_ou_half_life(spreads)
    max_half_life_periods = float(kwargs.get("max_half_life_periods", 36.0))
    if not np.isfinite(float(ou_half_life)) or ou_half_life > max_half_life_periods:
        _update_debug(debug_stats, rejected=1, reason="half_life_too_long")
        return None

    regime_name = resolve_strategy_regime(regime, bias=None, expiry_context=expiry_context)
    abs_z = abs(spread_z)
    if abs_z < min_zscore:
        _update_debug(debug_stats, rejected=1, reason="zscore_too_small")
        return None

    direction = "SELL_SPREAD" if spread_z > 0 else "BUY_SPREAD"
    score = 0.6 + min(0.35, (abs_z - min_zscore) * 0.1)
    soft_flags = []
    if abs_z > 3.5:
        soft_flags.append("extreme_divergence")
        score -= 0.1
    soft_flags.append(f"regime_{regime_name.lower()}")
    score = max(0.05, min(0.95, score))
    _update_debug(debug_stats, scored=1)

    return {
        "direction": direction,
        "reason": "Spread Z-Score Divergence",
        "score": round(score, 3),
        "soft_flags": soft_flags,
        "setup_type": "STATISTICAL_ARBITRAGE",
        "regime_path": regime_name,
        "hedge_ratio": round(float(hedge_ratio), 4),
        "beta_truth": round(float(hedge_ratio), 6),
        "cointegration_truth": {"adf_pvalue": adf_pvalue, "passed": True},
        "spread_truth": {"zscore": spread_z, "current_spread": float(current_spread)},
        "leg_freshness_a": float(leg_a_age_sec),
        "leg_freshness_b": float(leg_b_age_sec),
    }
