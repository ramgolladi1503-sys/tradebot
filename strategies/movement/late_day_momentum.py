"""Late-Day Momentum movement strategy.

Captures afternoon continuation only when structure and option premium still
confirm. This module emits read-only StrategyCandidate objects only and does not
alter execution paths.
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
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

STRATEGY_ID = "late_day_momentum_v1"
MOVEMENT_TYPE = "LATE_DAY_MOMENTUM"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_MINUTES_SINCE_OPEN": 240,
    "MIN_MINUTES_TO_CLOSE": 20,
    "MIN_DIRECTIONAL_SCORE": 0.45,
    "MIN_VWAP_DISTANCE_PCT": 0.002,
    "MAX_CHASE_DISTANCE_PCT": 0.012,
    "MAX_CHOP_SCORE": 0.5,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_late_day_momentum_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate late-day continuation candidates when timing and evidence align."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_minutes_since_open = float(params["MIN_MINUTES_SINCE_OPEN"])
    min_minutes_to_close = float(params["MIN_MINUTES_TO_CLOSE"])
    min_directional_score = float(params["MIN_DIRECTIONAL_SCORE"])
    min_vwap_distance_pct = float(params["MIN_VWAP_DISTANCE_PCT"])
    max_chase_distance_pct = float(params["MAX_CHASE_DISTANCE_PCT"])
    max_chop_score = float(params["MAX_CHOP_SCORE"])

    minutes_since_open = safe_float(ctx.minutes_since_open)
    minutes_to_close = safe_float(ctx.minutes_to_close)
    if block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_session_timing",
        field_specs=(
            ("minutes_since_open", ctx.minutes_since_open, "non_negative"),
            ("minutes_to_close", ctx.minutes_to_close, "non_negative"),
        ),
    ):
        return ()
    if minutes_since_open is None or minutes_since_open < min_minutes_since_open:
        return ()
    if minutes_to_close is None or minutes_to_close < min_minutes_to_close:
        return ()
    if float(regime.scores.get("CHOP", 0.0)) >= max_chop_score:
        return ()

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_thesis_evidence",
        field_specs=(
            ("spot_ltp", ctx.spot_ltp, "positive"),
            ("vwap", ctx.vwap, "positive"),
        ),
    ):
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None or abs(vwap_move) < min_vwap_distance_pct:
        return ()
    if abs(vwap_move) > max_chase_distance_pct:
        return ()

    candidates: list[StrategyCandidate] = []
    trend_up = float(regime.scores.get("TREND_UP", 0.0))
    trend_down = float(regime.scores.get("TREND_DOWN", 0.0))
    if vwap_move > 0 and trend_up >= min_directional_score:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_CALL",
                trend_up,
                abs(vwap_move),
                "late_day_upside_momentum",
            )
        )
    if vwap_move < 0 and trend_down >= min_directional_score:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_PUT",
                trend_down,
                abs(vwap_move),
                "late_day_downside_momentum",
            )
        )
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    directional_score: float,
    vwap_distance_abs: float,
    momentum_type: str,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    min_vwap_distance_pct = float(params["MIN_VWAP_DISTANCE_PCT"])
    max_chase_distance_pct = float(params["MAX_CHASE_DISTANCE_PCT"])
    side = side_evidence(ctx, direction)
    timing_quality = _timing_quality(ctx, profile)
    price_structure_score = clamp_score(
        0.40 * directional_score
        + 0.25
        * ratio_score(
            vwap_distance_abs, start=min_vwap_distance_pct, full=max_chase_distance_pct
        )
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
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _timing_quality(
    ctx: StrategyContext, profile: RuntimeProfileResolution
) -> float:
    params = dict(profile.parameters)
    min_minutes_since_open = float(params["MIN_MINUTES_SINCE_OPEN"])
    since_open = safe_float(ctx.minutes_since_open)
    to_close = safe_float(ctx.minutes_to_close)
    if since_open is None or to_close is None:
        return 0.0
    afternoon_score = ratio_score(since_open, start=min_minutes_since_open, full=330.0)
    close_buffer_score = clamp_score(to_close / 90.0)
    return clamp_score(0.65 * afternoon_score + 0.35 * close_buffer_score)


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_late_day_momentum_candidates"]
