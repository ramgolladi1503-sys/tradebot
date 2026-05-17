"""Exhaustion Reversal movement strategy.

Detects stretched directional moves that are losing premium/volume support. This
strategy is intentionally conservative: it refuses to fade strong continuation.
It emits read-only StrategyCandidate objects only and does not alter execution.
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

STRATEGY_ID = "exhaustion_reversal_v1"
MOVEMENT_TYPE = "EXHAUSTION_REVERSAL"
MIN_STRETCH_FROM_VWAP_PCT = 0.005
MAX_ENTRY_STRETCH_PCT = 0.018
MIN_EXHAUSTION_SCORE = 0.50
MAX_CONTINUATION_PRESSURE_SCORE = 0.55


def generate_exhaustion_reversal_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate opposite-side candidates only when stretched move is stalling."""

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    distance = signed_pct_distance(spot, vwap)
    if distance is None or abs(distance) < MIN_STRETCH_FROM_VWAP_PCT:
        return ()
    if abs(distance) > MAX_ENTRY_STRETCH_PCT:
        return ()

    candidates: list[StrategyCandidate] = []
    if distance > 0:
        score = _upside_exhaustion_score(ctx, regime, abs(distance))
        if score >= MIN_EXHAUSTION_SCORE and _continuation_pressure_score(ctx, "BUY_CALL") <= MAX_CONTINUATION_PRESSURE_SCORE:
            candidates.append(_build_candidate(ctx, regime, "BUY_PUT", score, abs(distance), "upside_exhaustion"))
    if distance < 0:
        score = _downside_exhaustion_score(ctx, regime, abs(distance))
        if score >= MIN_EXHAUSTION_SCORE and _continuation_pressure_score(ctx, "BUY_PUT") <= MAX_CONTINUATION_PRESSURE_SCORE:
            candidates.append(_build_candidate(ctx, regime, "BUY_CALL", score, abs(distance), "downside_exhaustion"))
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    exhaustion_score: float,
    stretch_abs: float,
    exhaustion_type: str,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.50 * exhaustion_score
        + 0.25 * clamp_score(regime.scores.get("EXHAUSTION_RISK", 0.0))
        + 0.25 * ratio_score(stretch_abs, start=MIN_STRETCH_FROM_VWAP_PCT, full=MAX_ENTRY_STRETCH_PCT)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_stretch_abs_pct": stretch_abs,
        "exhaustion_type": exhaustion_type,
        "exhaustion_score": exhaustion_score,
        "trend_side_ce_change": ctx.ce_premium_change,
        "trend_side_pe_change": ctx.pe_premium_change,
        "volume_z": ctx.volume_z,
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
        entry_trigger="stretched_move_premium_stall_with_opposite_option_confirmation",
        invalid_if="trend_side_premium_reaccelerates_or_option_quote_degrades",
        rank_reason="stretched move shows exhaustion and opposite option confirmation without strong continuation pressure",
        evidence=evidence,
        warnings=(),
        confluence_tags=("exhaustion", "vwap_stretch", "opposite_option_confirmation"),
        suppression_tags=("avoid_blind_trend_fade",),
    )


def _upside_exhaustion_score(ctx: StrategyContext, regime: MovementRegimeResult, stretch_abs: float) -> float:
    ce_change = safe_float(ctx.ce_premium_change)
    pe_change = safe_float(ctx.pe_premium_change)
    volume = safe_float(ctx.volume_z)
    ce_stall = 1.0 if ce_change is None or ce_change <= 0 else clamp_score(1.0 - ratio_score(ce_change, start=0.0, full=12.0))
    pe_confirm = ratio_score(pe_change, start=0.0, full=15.0)
    volume_fade = 1.0 if volume is None else clamp_score(1.0 - ratio_score(volume, start=0.4, full=2.0))
    return clamp_score(
        0.30 * ratio_score(stretch_abs, start=MIN_STRETCH_FROM_VWAP_PCT, full=MAX_ENTRY_STRETCH_PCT)
        + 0.25 * ce_stall
        + 0.20 * pe_confirm
        + 0.15 * volume_fade
        + 0.10 * clamp_score(regime.scores.get("EXHAUSTION_RISK", 0.0))
    )


def _downside_exhaustion_score(ctx: StrategyContext, regime: MovementRegimeResult, stretch_abs: float) -> float:
    pe_change = safe_float(ctx.pe_premium_change)
    ce_change = safe_float(ctx.ce_premium_change)
    volume = safe_float(ctx.volume_z)
    pe_stall = 1.0 if pe_change is None or pe_change <= 0 else clamp_score(1.0 - ratio_score(pe_change, start=0.0, full=12.0))
    ce_confirm = ratio_score(ce_change, start=0.0, full=15.0)
    volume_fade = 1.0 if volume is None else clamp_score(1.0 - ratio_score(volume, start=0.4, full=2.0))
    return clamp_score(
        0.30 * ratio_score(stretch_abs, start=MIN_STRETCH_FROM_VWAP_PCT, full=MAX_ENTRY_STRETCH_PCT)
        + 0.25 * pe_stall
        + 0.20 * ce_confirm
        + 0.15 * volume_fade
        + 0.10 * clamp_score(regime.scores.get("EXHAUSTION_RISK", 0.0))
    )


def _continuation_pressure_score(ctx: StrategyContext, direction: str) -> float:
    if direction == "BUY_CALL":
        premium = safe_float(ctx.ce_premium_change)
    elif direction == "BUY_PUT":
        premium = safe_float(ctx.pe_premium_change)
    else:
        premium = None
    volume = safe_float(ctx.volume_z)
    return clamp_score(
        0.65 * ratio_score(premium, start=4.0, full=20.0)
        + 0.35 * ratio_score(volume, start=1.0, full=3.0)
    )


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_exhaustion_reversal_candidates"]
