"""Compression Breakout movement strategy.

Captures expansion after a tight range/ATR compression. This module emits
read-only StrategyCandidate objects only. It does not call brokers, submit
orders, alter execution gates, touch depth subscriptions, or tune live trading.
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

STRATEGY_ID = "compression_breakout_v1"
MOVEMENT_TYPE = "COMPRESSION_BREAKOUT"
MAX_RANGE_WIDTH_PCT = 0.35
MAX_ATR_RATIO = 0.75
MIN_COMPRESSION_SCORE = 0.50
MIN_BREAKOUT_DISTANCE_PCT = 0.0008
MIN_VWAP_ALIGNMENT_PCT = 0.0004


def generate_compression_breakout_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates only after compression break evidence."""

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    compression_score = _compression_evidence_score(ctx, regime)
    if compression_score < MIN_COMPRESSION_SCORE:
        return ()

    candidates: list[StrategyCandidate] = []
    upper_level = _upper_breakout_level(ctx)
    lower_level = _lower_breakout_level(ctx)
    vwap_move = signed_pct_distance(spot, vwap)

    if upper_level is not None and vwap_move is not None:
        breakout_distance = (spot - upper_level) / abs(upper_level)
        if breakout_distance >= MIN_BREAKOUT_DISTANCE_PCT and vwap_move >= MIN_VWAP_ALIGNMENT_PCT:
            candidates.append(
                _build_candidate(
                    ctx,
                    regime,
                    "BUY_CALL",
                    compression_score,
                    breakout_distance,
                    abs(vwap_move),
                    upper_level,
                )
            )

    if lower_level is not None and vwap_move is not None:
        breakout_distance = (lower_level - spot) / abs(lower_level)
        if breakout_distance >= MIN_BREAKOUT_DISTANCE_PCT and vwap_move <= -MIN_VWAP_ALIGNMENT_PCT:
            candidates.append(
                _build_candidate(
                    ctx,
                    regime,
                    "BUY_PUT",
                    compression_score,
                    breakout_distance,
                    abs(vwap_move),
                    lower_level,
                )
            )

    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    compression_score: float,
    breakout_distance: float,
    vwap_alignment: float,
    breakout_level: float,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * compression_score
        + 0.35 * ratio_score(breakout_distance, start=MIN_BREAKOUT_DISTANCE_PCT, full=0.006)
        + 0.20 * ratio_score(vwap_alignment, start=MIN_VWAP_ALIGNMENT_PCT, full=0.004)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "range_width_pct": ctx.range_width_pct,
        "atr_short": ctx.atr_short,
        "atr_long": ctx.atr_long,
        "atr_short_long_ratio": _atr_ratio(ctx),
        "compression_score": compression_score,
        "breakout_level": breakout_level,
        "breakout_distance_pct": breakout_distance,
        "vwap_alignment_abs_pct": vwap_alignment,
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
        entry_trigger="compression_range_breakout_with_option_premium_expansion",
        invalid_if="price_returns_inside_compression_range_or_option_quote_degrades",
        rank_reason="range and ATR compression released into a confirmed option-side breakout",
        evidence=evidence,
        warnings=(),
        confluence_tags=("compression", "range_breakout", "option_confirmation"),
    )


def _compression_evidence_score(ctx: StrategyContext, regime: MovementRegimeResult) -> float:
    parts: list[float] = []
    range_width = safe_float(ctx.range_width_pct)
    if range_width is not None:
        parts.append(clamp_score((MAX_RANGE_WIDTH_PCT - range_width) / MAX_RANGE_WIDTH_PCT))
    atr_ratio = _atr_ratio(ctx)
    if atr_ratio is not None:
        parts.append(clamp_score((MAX_ATR_RATIO - atr_ratio) / MAX_ATR_RATIO))
    regime_score = safe_float(regime.scores.get("COMPRESSION"))
    if regime_score is not None:
        parts.append(regime_score)
    if not parts:
        return 0.0
    return clamp_score(sum(parts) / len(parts))


def _atr_ratio(ctx: StrategyContext) -> float | None:
    atr_short = safe_float(ctx.atr_short)
    atr_long = safe_float(ctx.atr_long)
    if atr_short is None or atr_long is None or atr_long <= 0:
        return None
    return atr_short / atr_long


def _upper_breakout_level(ctx: StrategyContext) -> float | None:
    for value in (ctx.nearest_resistance, ctx.orb_high, ctx.day_high):
        level = safe_float(value)
        if level is not None and level > 0:
            return level
    return None


def _lower_breakout_level(ctx: StrategyContext) -> float | None:
    for value in (ctx.nearest_support, ctx.orb_low, ctx.day_low):
        level = safe_float(value)
        if level is not None and level > 0:
            return level
    return None


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_compression_breakout_candidates"]
