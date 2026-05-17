"""Late-Day Momentum movement strategy.

Captures afternoon continuation only when structure and option premium still
confirm. This module emits read-only StrategyCandidate objects only and does not
alter execution paths.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement._utils import (
    clamp_score,
    make_candidate,
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

STRATEGY_ID = "late_day_momentum_v1"
MOVEMENT_TYPE = "LATE_DAY_MOMENTUM"
MIN_MINUTES_SINCE_OPEN = 240
MIN_MINUTES_TO_CLOSE = 20
MIN_DIRECTIONAL_SCORE = 0.45
MIN_VWAP_DISTANCE_PCT = 0.002
MAX_CHASE_DISTANCE_PCT = 0.012
MAX_CHOP_SCORE = 0.50


def generate_late_day_momentum_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate late-day continuation candidates when timing and evidence align."""

    minutes_since_open = safe_float(ctx.minutes_since_open)
    minutes_to_close = safe_float(ctx.minutes_to_close)
    if minutes_since_open is None or minutes_since_open < MIN_MINUTES_SINCE_OPEN:
        return ()
    if minutes_to_close is None or minutes_to_close < MIN_MINUTES_TO_CLOSE:
        return ()
    if float(regime.scores.get("CHOP", 0.0)) >= MAX_CHOP_SCORE:
        return ()

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None or abs(vwap_move) < MIN_VWAP_DISTANCE_PCT:
        return ()
    if abs(vwap_move) > MAX_CHASE_DISTANCE_PCT:
        return ()

    candidates: list[StrategyCandidate] = []
    trend_up = float(regime.scores.get("TREND_UP", 0.0))
    trend_down = float(regime.scores.get("TREND_DOWN", 0.0))
    if vwap_move > 0 and trend_up >= MIN_DIRECTIONAL_SCORE:
        candidates.append(_build_candidate(ctx, regime, "BUY_CALL", trend_up, abs(vwap_move), "late_day_upside_momentum"))
    if vwap_move < 0 and trend_down >= MIN_DIRECTIONAL_SCORE:
        candidates.append(_build_candidate(ctx, regime, "BUY_PUT", trend_down, abs(vwap_move), "late_day_downside_momentum"))
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    directional_score: float,
    vwap_distance_abs: float,
    momentum_type: str,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    timing_quality = _timing_quality(ctx)
    price_structure_score = clamp_score(
        0.40 * directional_score
        + 0.25 * ratio_score(vwap_distance_abs, start=MIN_VWAP_DISTANCE_PCT, full=MAX_CHASE_DISTANCE_PCT)
        + 0.20 * ratio_score(safe_float(ctx.volume_z), start=0.8, full=2.5)
        + 0.15 * timing_quality
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_distance_abs_pct": vwap_distance_abs,
        "momentum_type": momentum_type,
        "directional_score": directional_score,
        "minutes_since_open": ctx.minutes_since_open,
        "minutes_to_close": ctx.minutes_to_close,
        "expiry_context": ctx.expiry_context,
        "volume_z": ctx.volume_z,
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    warnings = ("expiry_context_late_day",) if ctx.expiry_context else ()
    return make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction=direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="late_day_directional_continuation_with_option_confirmation",
        invalid_if="momentum_fades_price_returns_to_vwap_or_option_quote_degrades",
        rank_reason="late-day directional structure still confirms with option-side momentum",
        evidence=evidence,
        warnings=warnings,
        confluence_tags=("late_day", "momentum", "option_confirmation"),
        suppression_tags=("avoid_end_of_day_decay_chase",),
    )


def _timing_quality(ctx: StrategyContext) -> float:
    since_open = safe_float(ctx.minutes_since_open)
    to_close = safe_float(ctx.minutes_to_close)
    if since_open is None or to_close is None:
        return 0.0
    afternoon_score = ratio_score(since_open, start=MIN_MINUTES_SINCE_OPEN, full=330.0)
    close_buffer_score = clamp_score(to_close / 90.0)
    return clamp_score(0.65 * afternoon_score + 0.35 * close_buffer_score)


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_late_day_momentum_candidates"]
