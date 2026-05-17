"""Event Volatility Expansion movement strategy.

Captures sudden directional volatility expansion only when price, ATR/volume, and
option premium evidence agree. This module emits read-only StrategyCandidate
objects only and does not alter execution paths.
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

STRATEGY_ID = "event_volatility_expansion_v1"
MOVEMENT_TYPE = "EVENT_VOLATILITY_EXPANSION"
MIN_VOL_EXPANSION_SCORE = 0.40
MIN_IMPULSE_FROM_VWAP_PCT = 0.0025
MAX_CHASE_DISTANCE_PCT = 0.014
MIN_VOLUME_Z = 1.2
MIN_ATR_EXPANSION_RATIO = 1.15


def generate_event_volatility_expansion_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates when volatility expansion is confirmed."""

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None or abs(vwap_move) < MIN_IMPULSE_FROM_VWAP_PCT:
        return ()
    if abs(vwap_move) > MAX_CHASE_DISTANCE_PCT:
        return ()

    expansion_score = _expansion_score(ctx, regime)
    if expansion_score < MIN_VOL_EXPANSION_SCORE:
        return ()

    candidates: list[StrategyCandidate] = []
    if vwap_move > 0:
        candidates.append(_build_candidate(ctx, regime, "BUY_CALL", expansion_score, abs(vwap_move), "upside_volatility_expansion"))
    if vwap_move < 0:
        candidates.append(_build_candidate(ctx, regime, "BUY_PUT", expansion_score, abs(vwap_move), "downside_volatility_expansion"))
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    expansion_score: float,
    impulse_abs: float,
    expansion_type: str,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    atr_ratio = _atr_ratio(ctx)
    price_structure_score = clamp_score(
        0.40 * expansion_score
        + 0.30 * ratio_score(impulse_abs, start=MIN_IMPULSE_FROM_VWAP_PCT, full=MAX_CHASE_DISTANCE_PCT)
        + 0.20 * ratio_score(safe_float(ctx.volume_z), start=MIN_VOLUME_Z, full=3.0)
        + 0.10 * ratio_score(atr_ratio, start=MIN_ATR_EXPANSION_RATIO, full=2.0)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_impulse_abs_pct": impulse_abs,
        "expansion_type": expansion_type,
        "expansion_score": expansion_score,
        "atr_short": ctx.atr_short,
        "atr_long": ctx.atr_long,
        "atr_short_long_ratio": atr_ratio,
        "volume_z": ctx.volume_z,
        "volatility_state": ctx.volatility_state,
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
        entry_trigger="volatility_expansion_with_directional_price_and_option_confirmation",
        invalid_if="spread_explodes_price_mean_reverts_or_option_quote_degrades",
        rank_reason="directional impulse aligns with volatility expansion and option-side confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("volatility_expansion", "directional_impulse", "option_confirmation"),
        suppression_tags=("avoid_late_spike_chase",),
    )


def _expansion_score(ctx: StrategyContext, regime: MovementRegimeResult) -> float:
    atr_ratio = _atr_ratio(ctx)
    regime_score = safe_float(regime.scores.get("VOLATILITY_EXPANSION")) or 0.0
    volume = safe_float(ctx.volume_z)
    volatility_state_bonus = 1.0 if str(ctx.volatility_state or "").strip().upper() in {"EXPANDING", "EXPANSION", "VOL_EXPANSION"} else 0.0
    return clamp_score(
        0.40 * regime_score
        + 0.30 * ratio_score(atr_ratio, start=MIN_ATR_EXPANSION_RATIO, full=2.0)
        + 0.20 * ratio_score(volume, start=MIN_VOLUME_Z, full=3.0)
        + 0.10 * volatility_state_bonus
    )


def _atr_ratio(ctx: StrategyContext) -> float | None:
    atr_short = safe_float(ctx.atr_short)
    atr_long = safe_float(ctx.atr_long)
    if atr_short is None or atr_long is None or atr_long <= 0:
        return None
    return atr_short / atr_long


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_event_volatility_expansion_candidates"]
