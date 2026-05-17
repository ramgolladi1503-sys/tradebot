"""Opening Drive movement strategy.

Captures strong early directional movement after open. This strategy emits
read-only StrategyCandidate objects only. It does not call brokers, submit
orders, alter execution gates, touch depth subscriptions, or tune live trading.
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
    signed_pct_distance,
)

STRATEGY_ID = "opening_drive_v1"
MOVEMENT_TYPE = "OPENING_DRIVE"
MAX_OPENING_DRIVE_MINUTES = 20
MIN_OPEN_MOVE_PCT = 0.0015
MIN_VWAP_ALIGNMENT_PCT = 0.0005


def generate_opening_drive_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate opening-drive candidates for CALL/PUT when evidence exists."""

    minutes = safe_float(ctx.minutes_since_open)
    if minutes is None or minutes < 0 or minutes > MAX_OPENING_DRIVE_MINUTES:
        return ()

    spot = safe_float(ctx.spot_ltp)
    open_price = safe_float(ctx.open_price)
    vwap = safe_float(ctx.vwap)
    if spot is None or open_price is None or vwap is None:
        return ()

    open_move = signed_pct_distance(spot, open_price)
    vwap_move = signed_pct_distance(spot, vwap)
    if open_move is None or vwap_move is None:
        return ()

    candidates: list[StrategyCandidate] = []
    if open_move >= MIN_OPEN_MOVE_PCT and vwap_move >= MIN_VWAP_ALIGNMENT_PCT:
        candidates.append(_build_candidate(ctx, regime, "BUY_CALL", open_move, vwap_move))
    if open_move <= -MIN_OPEN_MOVE_PCT and vwap_move <= -MIN_VWAP_ALIGNMENT_PCT:
        candidates.append(_build_candidate(ctx, regime, "BUY_PUT", abs(open_move), abs(vwap_move)))
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    open_move_abs: float,
    vwap_move_abs: float,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    orb_distance = _orb_distance(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * ratio_score(open_move_abs, start=MIN_OPEN_MOVE_PCT, full=0.006)
        + 0.30 * ratio_score(vwap_move_abs, start=MIN_VWAP_ALIGNMENT_PCT, full=0.004)
        + 0.25 * ratio_score(orb_distance, start=0.0, full=0.003)
    )
    evidence = {
        "minutes_since_open": ctx.minutes_since_open,
        "open_price": ctx.open_price,
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "open_move_abs_pct": open_move_abs,
        "vwap_alignment_abs_pct": vwap_move_abs,
        "orb_distance_pct": orb_distance,
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
        entry_trigger="opening_drive_with_vwap_alignment_and_option_confirmation",
        invalid_if="price_reclaims_opening_drive_or_option_quote_degrades",
        rank_reason="early directional drive with VWAP alignment and option-side confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("opening_drive", "vwap_alignment", "option_confirmation"),
    )


def _orb_distance(ctx: StrategyContext, direction: str) -> float:
    spot = safe_float(ctx.spot_ltp)
    if direction == "BUY_CALL":
        return pct_distance(spot, ctx.orb_high) or 0.0 if spot is not None and safe_float(ctx.orb_high) is not None and spot >= safe_float(ctx.orb_high) else 0.0
    if direction == "BUY_PUT":
        return pct_distance(spot, ctx.orb_low) or 0.0 if spot is not None and safe_float(ctx.orb_low) is not None and spot <= safe_float(ctx.orb_low) else 0.0
    return 0.0


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_opening_drive_candidates"]
