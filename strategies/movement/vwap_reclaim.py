"""VWAP Reclaim/Rejection movement strategy.

This strategy is intentionally stricter than a generic above/below VWAP signal.
It requires explicit reclaim/rejection evidence or a previous VWAP cross. It emits
read-only StrategyCandidate objects only and does not touch execution paths.
"""

from __future__ import annotations

from typing import Any

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import (
    RuntimeProfileResolution,
    resolve_required_profile_parameters,
)
from strategies.movement._utils import (
    clamp_score,
    make_candidate,
    missing_evidence_warning,
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

STRATEGY_ID = "vwap_reclaim_rejection_v1"
MOVEMENT_TYPE = "VWAP_RECLAIM_REJECTION"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_VWAP_DISTANCE_PCT": 0.00035,
    "MAX_VWAP_ENTRY_DISTANCE_PCT": 0.0035,
    "MAX_CHOP_SCORE": 0.55,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_vwap_reclaim_rejection_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates for confirmed VWAP reclaim/rejection events."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_vwap_distance_pct = float(params["MIN_VWAP_DISTANCE_PCT"])
    max_vwap_entry_distance_pct = float(params["MAX_VWAP_ENTRY_DISTANCE_PCT"])
    max_chop_score = float(params["MAX_CHOP_SCORE"])

    if float(regime.scores.get("CHOP", 0.0)) >= max_chop_score:
        return ()

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None or abs(vwap_move) < min_vwap_distance_pct:
        return ()
    if abs(vwap_move) > max_vwap_entry_distance_pct:
        return ()

    candidates: list[StrategyCandidate] = []
    if vwap_move > 0 and _has_upside_vwap_confirmation(ctx):
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_CALL",
                vwap_move,
                "upside_vwap_reclaim_or_rejection",
            )
        )
    if vwap_move < 0 and _has_downside_vwap_confirmation(ctx):
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_PUT",
                abs(vwap_move),
                "downside_vwap_reclaim_or_rejection",
            )
        )
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    vwap_distance_abs: float,
    confirmation_type: str,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    max_vwap_entry_distance_pct = float(params["MAX_VWAP_ENTRY_DISTANCE_PCT"])
    side = side_evidence(ctx, direction)
    slope_score = _vwap_slope_alignment_score(ctx, direction)
    distance_quality = clamp_score(
        1.0
        - ratio_score(vwap_distance_abs, start=0.0, full=max_vwap_entry_distance_pct)
    )
    price_structure_score = clamp_score(
        0.45 * distance_quality
        + 0.30 * slope_score
        + 0.25 * ratio_score(abs(safe_float(ctx.volume_z) or 0.0), start=0.5, full=2.0)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_slope": ctx.vwap_slope,
        "vwap_distance_abs_pct": vwap_distance_abs,
        "confirmation_type": confirmation_type,
        "previous_spot_ltp": _metadata_float(ctx, "previous_spot_ltp"),
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    warnings = missing_evidence_warning(STRATEGY_ID, "vwap_slope") if safe_float(ctx.vwap_slope) is None else ()
    return make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction=direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="confirmed_vwap_reclaim_or_rejection_with_option_confirmation",
        invalid_if="price_crosses_back_through_vwap_or_option_quote_degrades",
        rank_reason="confirmed VWAP reclaim/rejection with option-side confirmation and non-chop regime",
        evidence=evidence,
        warnings=warnings,
        confluence_tags=("vwap", "reclaim_rejection", "option_confirmation"),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _has_upside_vwap_confirmation(ctx: StrategyContext) -> bool:
    if _metadata_bool(ctx, "vwap_reclaim_up_confirmed") or _metadata_bool(
        ctx, "vwap_rejection_up_confirmed"
    ):
        return True
    previous = _metadata_float(ctx, "previous_spot_ltp")
    vwap = safe_float(ctx.vwap)
    spot = safe_float(ctx.spot_ltp)
    return bool(
        previous is not None
        and vwap is not None
        and spot is not None
        and previous <= vwap < spot
    )


def _has_downside_vwap_confirmation(ctx: StrategyContext) -> bool:
    if _metadata_bool(ctx, "vwap_reclaim_down_confirmed") or _metadata_bool(
        ctx, "vwap_rejection_down_confirmed"
    ):
        return True
    previous = _metadata_float(ctx, "previous_spot_ltp")
    vwap = safe_float(ctx.vwap)
    spot = safe_float(ctx.spot_ltp)
    return bool(
        previous is not None
        and vwap is not None
        and spot is not None
        and previous >= vwap > spot
    )


def _vwap_slope_alignment_score(ctx: StrategyContext, direction: str) -> float:
    slope = safe_float(ctx.vwap_slope)
    if slope is None:
        return 0.0
    if direction == "BUY_CALL" and slope >= 0:
        return clamp_score(0.5 + ratio_score(abs(slope), start=0.0, full=0.08) * 0.5)
    if direction == "BUY_PUT" and slope <= 0:
        return clamp_score(0.5 + ratio_score(abs(slope), start=0.0, full=0.08) * 0.5)
    return 0.15


def _metadata_bool(ctx: StrategyContext, key: str) -> bool:
    value = (ctx.metadata or {}).get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _metadata_float(ctx: StrategyContext, key: str) -> float | None:
    value: Any = (ctx.metadata or {}).get(key)
    return safe_float(value)


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_vwap_reclaim_rejection_candidates"]
