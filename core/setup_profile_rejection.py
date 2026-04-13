from __future__ import annotations

from typing import Dict, Any
from core.profile_features import normalize_profile, downside_path_quality
from core.regime_filters import evaluate_regime
from core.setup_types import ProfileRejectionSetup


def _bearish_rejection(candle: Dict[str, Any]) -> float:
    try:
        high = float(candle.get("high"))
        low = float(candle.get("low"))
        close = float(candle.get("close"))
        open_ = float(candle.get("open"))
    except Exception:
        return 0.0

    body = abs(close - open_)
    wick = high - max(close, open_)

    if high == low:
        return 0.0

    wick_ratio = wick / max(high - low, 1e-6)
    bearish = 1.0 if close < open_ else 0.0
    return min(1.0, wick_ratio * bearish)


def evaluate_profile_rejection_setup(candidate: Dict[str, Any]) -> ProfileRejectionSetup:
    profile = normalize_profile(candidate.get("session_profile") or candidate.get("profile_snapshot"))
    regime_decision = evaluate_regime(candidate)

    price = float(candidate.get("current_price") or candidate.get("last_price") or 0.0)
    candle = candidate.get("latest_candle") or {}

    vah = profile.get("vah")

    if vah is None:
        return ProfileRejectionSetup(False, "SELL", 0, 0, 0, 0, price, price, price, ["no_vah"], {})

    # Condition 1: price near/above VAH
    level_score = 1.0 if price >= vah else 0.0

    # Condition 2: rejection
    rejection_score = _bearish_rejection(candle)

    # Stop above candle high
    stop = float(candle.get("high") or price)

    # Condition 3: path quality
    path_score, target = downside_path_quality(profile, price, stop)

    rr = abs(price - target) / max(abs(stop - price), 1e-6)

    # Regime
    regime_score = 1.0 if regime_decision.allow_mean_reversion else 0.0

    setup_score = (0.25 * level_score + 0.25 * rejection_score + 0.25 * path_score + 0.25 * regime_score)

    detected = bool(
        level_score > 0.5
        and rejection_score > 0.3
        and path_score > 0.3
        and regime_decision.allow_mean_reversion
        and rr > 1.5
    )

    return ProfileRejectionSetup(
        detected=detected,
        direction="SELL",
        setup_score=setup_score,
        trigger_score=rejection_score,
        entry_quality_score=path_score,
        rr=rr,
        entry=price,
        stop=stop,
        target=target,
        reasons=regime_decision.reasons,
        telemetry={
            "vah": vah,
            "price": price,
            "rejection_score": rejection_score,
            "path_score": path_score,
            "rr": rr,
        },
    )
