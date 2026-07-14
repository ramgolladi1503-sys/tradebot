"""Mean Reversion Extension movement strategy.

Detects range/chop extension back toward VWAP/range mean. This strategy refuses
to fade strong continuation and emits read-only StrategyCandidate objects only.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import (
    RuntimeProfileResolution,
    resolve_required_profile_parameters,
)
from strategies.movement._utils import (
    clamp_score,
    make_candidate,
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

STRATEGY_ID = "mean_reversion_extension_v1"
MOVEMENT_TYPE = "MEAN_REVERSION_EXTENSION"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_RANGE_OR_CHOP_SCORE": 0.45,
    "MIN_EXTENSION_FROM_VWAP_PCT": 0.0035,
    "MAX_EXTENSION_FROM_VWAP_PCT": 0.014,
    "MAX_TREND_CONTINUATION_SCORE": 0.55,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_mean_reversion_extension_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate mean-reversion candidates only in range/chop extension contexts."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_range_or_chop_score = float(params["MIN_RANGE_OR_CHOP_SCORE"])
    min_extension_from_vwap_pct = float(params["MIN_EXTENSION_FROM_VWAP_PCT"])
    max_extension_from_vwap_pct = float(params["MAX_EXTENSION_FROM_VWAP_PCT"])
    max_trend_continuation_score = float(params["MAX_TREND_CONTINUATION_SCORE"])

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    range_chop_score = max(
        float(regime.scores.get("RANGE", 0.0)), float(regime.scores.get("CHOP", 0.0))
    )
    if range_chop_score < min_range_or_chop_score:
        return ()

    distance = signed_pct_distance(spot, vwap)
    if distance is None or abs(distance) < min_extension_from_vwap_pct:
        return ()
    if abs(distance) > max_extension_from_vwap_pct:
        return ()

    candidates: list[StrategyCandidate] = []
    if (
        distance > 0
        and _trend_continuation_score(ctx, regime, "BUY_CALL")
        <= max_trend_continuation_score
    ):
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_PUT",
                range_chop_score,
                abs(distance),
                "upper_extension_reversion",
            )
        )
    if (
        distance < 0
        and _trend_continuation_score(ctx, regime, "BUY_PUT")
        <= max_trend_continuation_score
    ):
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_CALL",
                range_chop_score,
                abs(distance),
                "lower_extension_reversion",
            )
        )
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    range_chop_score: float,
    extension_abs: float,
    reversion_type: str,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    min_extension_from_vwap_pct = float(params["MIN_EXTENSION_FROM_VWAP_PCT"])
    max_extension_from_vwap_pct = float(params["MAX_EXTENSION_FROM_VWAP_PCT"])
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * range_chop_score
        + 0.35
        * ratio_score(
            extension_abs,
            start=min_extension_from_vwap_pct,
            full=max_extension_from_vwap_pct,
        )
        + 0.20 * _range_boundary_score(ctx, direction)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_extension_abs_pct": extension_abs,
        "reversion_type": reversion_type,
        "range_chop_score": range_chop_score,
        "day_high": ctx.day_high,
        "day_low": ctx.day_low,
        "nearest_support": ctx.nearest_support,
        "nearest_resistance": ctx.nearest_resistance,
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    return make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction=direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="range_extension_with_opposite_option_confirmation",
        invalid_if="extension_expands_into_trend_continuation_or_option_quote_degrades",
        rank_reason="range/chop extension stretched away from VWAP with opposite option confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("mean_reversion", "range_extension", "option_confirmation"),
        suppression_tags=("avoid_fading_strong_trend",),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _range_boundary_score(ctx: StrategyContext, direction: str) -> float:
    spot = safe_float(ctx.spot_ltp)
    if spot is None:
        return 0.0
    if direction == "BUY_PUT":
        boundary = safe_float(ctx.nearest_resistance) or safe_float(ctx.day_high)
        if boundary is None or boundary <= 0 or spot > boundary:
            return 0.0
        distance = abs(boundary - spot) / abs(boundary)
        return clamp_score(1.0 - ratio_score(distance, start=0.0, full=0.004))
    if direction == "BUY_CALL":
        boundary = safe_float(ctx.nearest_support) or safe_float(ctx.day_low)
        if boundary is None or boundary <= 0 or spot < boundary:
            return 0.0
        distance = abs(spot - boundary) / abs(boundary)
        return clamp_score(1.0 - ratio_score(distance, start=0.0, full=0.004))
    return 0.0


def _trend_continuation_score(
    ctx: StrategyContext, regime: MovementRegimeResult, direction: str
) -> float:
    if direction == "BUY_CALL":
        premium = safe_float(ctx.ce_premium_change)
        trend = float(regime.scores.get("TREND_UP", 0.0))
    elif direction == "BUY_PUT":
        premium = safe_float(ctx.pe_premium_change)
        trend = float(regime.scores.get("TREND_DOWN", 0.0))
    else:
        premium = None
        trend = 0.0
    volume = safe_float(ctx.volume_z)
    expansion = float(regime.scores.get("VOLATILITY_EXPANSION", 0.0))
    return clamp_score(
        0.40 * trend
        + 0.25 * expansion
        + 0.25 * ratio_score(premium, start=4.0, full=18.0)
        + 0.10 * ratio_score(volume, start=1.0, full=3.0)
    )


__all__ = [
    "STRATEGY_ID",
    "MOVEMENT_TYPE",
    "generate_mean_reversion_extension_candidates",
]
