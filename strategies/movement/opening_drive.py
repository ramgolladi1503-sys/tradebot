"""Opening Drive movement strategy.

Captures strong early directional movement after open. This strategy emits
read-only StrategyCandidate objects only. It does not call brokers, submit
orders, alter execution gates, touch depth subscriptions, or tune live trading.
"""

from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import (
    RuntimeProfileResolution,
    resolve_required_profile_parameters,
)
from strategies.movement._utils import (
    block_on_required_fields,
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
EMBEDDED_PROFILE_DEFAULTS = {
    "MAX_OPENING_DRIVE_MINUTES": 20,
    "MIN_OPEN_MOVE_PCT": 0.0015,
    "MIN_VWAP_ALIGNMENT_PCT": 0.0005,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_opening_drive_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate opening-drive candidates for CALL/PUT when evidence exists."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    max_opening_drive_minutes = float(params["MAX_OPENING_DRIVE_MINUTES"])
    min_open_move_pct = float(params["MIN_OPEN_MOVE_PCT"])
    min_vwap_alignment_pct = float(params["MIN_VWAP_ALIGNMENT_PCT"])

    minutes = safe_float(ctx.minutes_since_open)
    if block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_session_timing",
        field_specs=(("minutes_since_open", ctx.minutes_since_open, "non_negative"),),
    ):
        return ()
    if minutes is None or minutes > max_opening_drive_minutes:
        return ()

    spot = safe_float(ctx.spot_ltp)
    open_price = safe_float(ctx.open_price)
    vwap = safe_float(ctx.vwap)
    if block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_thesis_evidence",
        field_specs=(
            ("spot_ltp", ctx.spot_ltp, "positive"),
            ("open_price", ctx.open_price, "positive"),
            ("vwap", ctx.vwap, "positive"),
        ),
    ):
        return ()

    open_move = signed_pct_distance(spot, open_price)
    vwap_move = signed_pct_distance(spot, vwap)
    if open_move is None or vwap_move is None:
        block_on_required_fields(
            STRATEGY_ID,
            reason="missing_required_thesis_evidence",
            field_specs=(
                ("open_price", ctx.open_price, "positive"),
                ("vwap", ctx.vwap, "positive"),
            ),
        )
        return ()

    candidates: list[StrategyCandidate] = []
    if open_move >= min_open_move_pct and vwap_move >= min_vwap_alignment_pct:
        candidates.append(_build_candidate(ctx, regime, profile, "BUY_CALL", open_move, vwap_move))
    if open_move <= -min_open_move_pct and vwap_move <= -min_vwap_alignment_pct:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_PUT",
                abs(open_move),
                abs(vwap_move),
            )
        )
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    open_move_abs: float,
    vwap_move_abs: float,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    min_open_move_pct = float(params["MIN_OPEN_MOVE_PCT"])
    min_vwap_alignment_pct = float(params["MIN_VWAP_ALIGNMENT_PCT"])
    side = side_evidence(ctx, direction)
    orb_distance = _orb_distance(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * ratio_score(open_move_abs, start=min_open_move_pct, full=0.006)
        + 0.30 * ratio_score(vwap_move_abs, start=min_vwap_alignment_pct, full=0.004)
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
        entry_trigger="opening_drive_with_vwap_alignment",
        invalid_if="price_reclaims_opening_drive",
        rank_reason="early directional drive with VWAP alignment",
        evidence=evidence,
        warnings=(),
        confluence_tags=("opening_drive", "vwap_alignment"),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _orb_distance(ctx: StrategyContext, direction: str) -> float:
    spot = safe_float(ctx.spot_ltp)
    if spot is None:
        return 0.0
    if direction == "BUY_CALL":
        level = safe_float(ctx.orb_high)
        if level is None or spot < level:
            return 0.0
        return pct_distance(spot, level) or 0.0
    if direction == "BUY_PUT":
        level = safe_float(ctx.orb_low)
        if level is None or spot > level:
            return 0.0
        return pct_distance(spot, level) or 0.0
    return 0.0


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_opening_drive_candidates"]
