"""Trend Pullback movement strategy.

Joins an established trend after a controlled pullback holds VWAP/structure. This
module emits read-only StrategyCandidate objects only. It does not call brokers,
submit orders, alter execution gates, touch depth subscriptions, or tune live
trading.
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
    pct_distance,
    ratio_score,
    safe_float,
    side_evidence,
)

STRATEGY_ID = "trend_pullback_v1"
MOVEMENT_TYPE = "TREND_PULLBACK"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_TREND_SCORE": 0.45,
    "MAX_PULLBACK_DISTANCE_PCT": 0.0035,
    "MIN_STRUCTURE_RESUME_PCT": 0.0004,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_trend_pullback_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates after pullback hold and trend resumption."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_trend_score = float(params["MIN_TREND_SCORE"])

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    candidates: list[StrategyCandidate] = []
    trend_up = safe_float(regime.scores.get("TREND_UP")) or 0.0
    trend_down = safe_float(regime.scores.get("TREND_DOWN")) or 0.0

    if trend_up >= min_trend_score and _call_pullback_holds(ctx, profile):
        candidates.append(_build_candidate(ctx, regime, profile, "BUY_CALL", trend_up))
    if trend_down >= min_trend_score and _put_pullback_holds(ctx, profile):
        candidates.append(_build_candidate(ctx, regime, profile, "BUY_PUT", trend_down))
    return tuple(candidates)


def _call_pullback_holds(
    ctx: StrategyContext, profile: RuntimeProfileResolution
) -> bool:
    params = dict(profile.parameters)
    max_pullback_distance_pct = float(params["MAX_PULLBACK_DISTANCE_PCT"])
    min_structure_resume_pct = float(params["MIN_STRUCTURE_RESUME_PCT"])
    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    support = safe_float(ctx.nearest_support)
    if spot is None or vwap is None:
        return False
    anchor = support if support is not None and support > 0 else vwap
    if spot < anchor or spot < vwap:
        return False
    distance = pct_distance(spot, anchor)
    if distance is None or distance > max_pullback_distance_pct:
        return False
    return ((spot - anchor) / abs(anchor)) >= min_structure_resume_pct


def _put_pullback_holds(
    ctx: StrategyContext, profile: RuntimeProfileResolution
) -> bool:
    params = dict(profile.parameters)
    max_pullback_distance_pct = float(params["MAX_PULLBACK_DISTANCE_PCT"])
    min_structure_resume_pct = float(params["MIN_STRUCTURE_RESUME_PCT"])
    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    resistance = safe_float(ctx.nearest_resistance)
    if spot is None or vwap is None:
        return False
    anchor = resistance if resistance is not None and resistance > 0 else vwap
    if spot > anchor or spot > vwap:
        return False
    distance = pct_distance(spot, anchor)
    if distance is None or distance > max_pullback_distance_pct:
        return False
    return ((anchor - spot) / abs(anchor)) >= min_structure_resume_pct


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    trend_score: float,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    max_pullback_distance_pct = float(params["MAX_PULLBACK_DISTANCE_PCT"])
    min_structure_resume_pct = float(params["MIN_STRUCTURE_RESUME_PCT"])
    side = side_evidence(ctx, direction)
    anchor = _pullback_anchor(ctx, direction)
    spot = safe_float(ctx.spot_ltp)
    pullback_distance = pct_distance(spot, anchor) or 0.0
    resume_distance = _resume_distance(ctx, direction, anchor)
    price_structure_score = clamp_score(
        0.45 * trend_score
        + 0.35
        * (
            1.0
            - ratio_score(pullback_distance, start=0.0, full=max_pullback_distance_pct)
        )
        + 0.20
        * ratio_score(resume_distance, start=min_structure_resume_pct, full=0.003)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "nearest_support": ctx.nearest_support,
        "nearest_resistance": ctx.nearest_resistance,
        "trend_score": trend_score,
        "pullback_anchor": anchor,
        "pullback_distance_pct": pullback_distance,
        "resume_distance_pct": resume_distance,
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
        entry_trigger="trend_pullback_hold_with_option_premium_resumption",
        invalid_if="pullback_breaks_anchor_or_option_quote_degrades",
        rank_reason="established trend resumed after controlled pullback with option-side confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("trend", "pullback_hold", "option_confirmation"),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _pullback_anchor(ctx: StrategyContext, direction: str) -> float | None:
    if direction == "BUY_CALL":
        return safe_float(ctx.nearest_support) or safe_float(ctx.vwap)
    if direction == "BUY_PUT":
        return safe_float(ctx.nearest_resistance) or safe_float(ctx.vwap)
    return None


def _resume_distance(
    ctx: StrategyContext, direction: str, anchor: float | None
) -> float:
    spot = safe_float(ctx.spot_ltp)
    if spot is None or anchor is None or anchor <= 0:
        return 0.0
    if direction == "BUY_CALL" and spot >= anchor:
        return (spot - anchor) / abs(anchor)
    if direction == "BUY_PUT" and spot <= anchor:
        return (anchor - spot) / abs(anchor)
    return 0.0


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_trend_pullback_candidates"]
