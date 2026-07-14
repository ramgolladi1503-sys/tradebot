"""Event Volatility Expansion movement strategy.

Captures sudden directional volatility expansion only when price, ATR/volume, and
option premium evidence agree. This module emits read-only StrategyCandidate
objects only and does not alter execution paths.
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

STRATEGY_ID = "event_volatility_expansion_v1"
MOVEMENT_TYPE = "EVENT_VOLATILITY_EXPANSION"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_VOL_EXPANSION_SCORE": 0.4,
    "MIN_IMPULSE_FROM_VWAP_PCT": 0.0025,
    "MAX_CHASE_DISTANCE_PCT": 0.014,
    "MIN_VOLUME_Z": 1.2,
    "MIN_ATR_EXPANSION_RATIO": 1.15,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


def generate_event_volatility_expansion_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates when volatility expansion is confirmed."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_vol_expansion_score = float(params["MIN_VOL_EXPANSION_SCORE"])
    min_impulse_from_vwap_pct = float(params["MIN_IMPULSE_FROM_VWAP_PCT"])
    max_chase_distance_pct = float(params["MAX_CHASE_DISTANCE_PCT"])

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
    if vwap_move is None or abs(vwap_move) < min_impulse_from_vwap_pct:
        return ()
    if abs(vwap_move) > max_chase_distance_pct:
        return ()

    expansion_missing = block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_thesis_evidence",
        field_specs=(
            ("atr_short", ctx.atr_short, "positive"),
            ("atr_long", ctx.atr_long, "positive"),
            ("volume_z", ctx.volume_z, "finite"),
        ),
    )
    expansion_score = _expansion_score(ctx, regime, profile)
    if expansion_score < min_vol_expansion_score:
        if expansion_missing:
            return ()
        return ()

    candidates: list[StrategyCandidate] = []
    if vwap_move > 0:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_CALL",
                expansion_score,
                abs(vwap_move),
                "upside_volatility_expansion",
            )
        )
    if vwap_move < 0:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                profile,
                "BUY_PUT",
                expansion_score,
                abs(vwap_move),
                "downside_volatility_expansion",
            )
        )
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    expansion_score: float,
    impulse_abs: float,
    expansion_type: str,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    min_impulse_from_vwap_pct = float(params["MIN_IMPULSE_FROM_VWAP_PCT"])
    max_chase_distance_pct = float(params["MAX_CHASE_DISTANCE_PCT"])
    min_volume_z = float(params["MIN_VOLUME_Z"])
    min_atr_expansion_ratio = float(params["MIN_ATR_EXPANSION_RATIO"])
    side = side_evidence(ctx, direction)
    atr_ratio = _atr_ratio(ctx)
    price_structure_score = clamp_score(
        0.40 * expansion_score
        + 0.30
        * ratio_score(
            impulse_abs, start=min_impulse_from_vwap_pct, full=max_chase_distance_pct
        )
        + 0.20 * ratio_score(safe_float(ctx.volume_z), start=min_volume_z, full=3.0)
        + 0.10 * ratio_score(atr_ratio, start=min_atr_expansion_ratio, full=2.0)
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
        entry_trigger="volatility_expansion_with_directional_price",
        invalid_if="price_mean_reverts_against_expansion",
        rank_reason="directional impulse aligns with volatility expansion",
        evidence=evidence,
        warnings=(),
        confluence_tags=(
            "volatility_expansion",
            "directional_impulse",
        ),
        suppression_tags=("avoid_late_spike_chase",),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _expansion_score(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
) -> float:
    params = dict(profile.parameters)
    min_volume_z = float(params["MIN_VOLUME_Z"])
    min_atr_expansion_ratio = float(params["MIN_ATR_EXPANSION_RATIO"])
    atr_ratio = _atr_ratio(ctx)
    volume = safe_float(ctx.volume_z)
    if atr_ratio is None or volume is None:
        return 0.0
    regime_score = safe_float(regime.scores.get("VOLATILITY_EXPANSION")) or 0.0
    volatility_state_bonus = (
        1.0
        if str(ctx.volatility_state or "").strip().upper()
        in {"EXPANDING", "EXPANSION", "VOL_EXPANSION"}
        else 0.0
    )
    return clamp_score(
        0.40 * regime_score
        + 0.30 * ratio_score(atr_ratio, start=min_atr_expansion_ratio, full=2.0)
        + 0.20 * ratio_score(volume, start=min_volume_z, full=3.0)
        + 0.10 * volatility_state_bonus
    )


def _atr_ratio(ctx: StrategyContext) -> float | None:
    atr_short = safe_float(ctx.atr_short)
    atr_long = safe_float(ctx.atr_long)
    if atr_short is None or atr_long is None or atr_long <= 0:
        return None
    return atr_short / atr_long


__all__ = [
    "STRATEGY_ID",
    "MOVEMENT_TYPE",
    "generate_event_volatility_expansion_candidates",
]
