"""Opening Range Breakout Retest movement strategy.

This strategy avoids chasing the first break. It emits candidates only when price
is near a confirmed retest zone after breaking the opening range. It is
read-only and never calls broker/order/depth/execution code.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement._utils import (
    clamp_score,
    make_candidate,
    pct_distance,
    ratio_score,
    safe_float,
    side_evidence,
)

STRATEGY_ID = "opening_range_retest_v1"
MOVEMENT_TYPE = "OPENING_RANGE_RETEST"
MIN_RETEST_MINUTES = 15
MAX_RETEST_MINUTES = 90
MAX_RETEST_DISTANCE_PCT = 0.0018
MIN_BREAKOUT_DISTANCE_PCT = 0.0008


def generate_opening_range_retest_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate ORB retest candidates for CALL/PUT when evidence exists."""

    minutes = safe_float(ctx.minutes_since_open)
    if minutes is None or minutes < MIN_RETEST_MINUTES or minutes > MAX_RETEST_MINUTES:
        return ()

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    orb_high = safe_float(ctx.orb_high)
    orb_low = safe_float(ctx.orb_low)
    if spot is None or vwap is None or orb_high is None or orb_low is None:
        return ()

    candidates: list[StrategyCandidate] = []
    if _call_retest_confirmed(spot=spot, vwap=vwap, orb_high=orb_high):
        candidates.append(_build_candidate(ctx, regime, "BUY_CALL", orb_high))
    if _put_retest_confirmed(spot=spot, vwap=vwap, orb_low=orb_low):
        candidates.append(_build_candidate(ctx, regime, "BUY_PUT", orb_low))
    return tuple(candidates)


def _call_retest_confirmed(*, spot: float, vwap: float, orb_high: float) -> bool:
    return (
        spot >= orb_high
        and spot >= vwap
        and (pct_distance(spot, orb_high) or 1.0) <= MAX_RETEST_DISTANCE_PCT
        and ((spot - orb_high) / abs(orb_high)) >= 0.0
    )


def _put_retest_confirmed(*, spot: float, vwap: float, orb_low: float) -> bool:
    return (
        spot <= orb_low
        and spot <= vwap
        and (pct_distance(spot, orb_low) or 1.0) <= MAX_RETEST_DISTANCE_PCT
        and ((orb_low - spot) / abs(orb_low)) >= 0.0
    )


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    retest_level: float,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    spot = safe_float(ctx.spot_ltp)
    retest_distance = pct_distance(spot, retest_level) or 0.0
    breakout_distance = _breakout_distance(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * (1.0 - ratio_score(retest_distance, start=0.0, full=MAX_RETEST_DISTANCE_PCT))
        + 0.35 * ratio_score(breakout_distance, start=MIN_BREAKOUT_DISTANCE_PCT, full=0.004)
        + 0.20 * clamp_score(regime.scores.get("VOLATILITY_EXPANSION", 0.0))
    )
    evidence = {
        "minutes_since_open": ctx.minutes_since_open,
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "orb_high": ctx.orb_high,
        "orb_low": ctx.orb_low,
        "retest_level": retest_level,
        "retest_distance_pct": retest_distance,
        "breakout_distance_pct": breakout_distance,
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
        entry_trigger="opening_range_breakout_retest_hold_with_option_confirmation",
        invalid_if="price_returns_inside_opening_range_or_option_quote_degrades",
        rank_reason="opening range breakout retest held with option-side confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("orb_retest", "vwap_alignment", "option_confirmation"),
    )


def _breakout_distance(ctx: StrategyContext, direction: str) -> float:
    spot = safe_float(ctx.spot_ltp)
    if spot is None:
        return 0.0
    if direction == "BUY_CALL":
        level = safe_float(ctx.orb_high)
        if level is None or spot < level:
            return 0.0
        return (spot - level) / abs(level)
    if direction == "BUY_PUT":
        level = safe_float(ctx.orb_low)
        if level is None or spot > level:
            return 0.0
        return (level - spot) / abs(level)
    return 0.0


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_opening_range_retest_candidates"]
