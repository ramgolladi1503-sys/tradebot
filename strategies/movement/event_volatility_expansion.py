"""Event Volatility Expansion movement strategy.

Requires explicit event state plus complete volatility evidence. A regime score
alone cannot synthesize an event, and missing ATR/volume evidence fails closed.
"""
from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.strategy_parameter_profiles import get_default_profile
from core.movement_regime import MovementRegimeResult
from strategies.movement._utils import clamp_score, make_candidate, ratio_score, safe_float, side_evidence, signed_pct_distance

STRATEGY_ID = "event_volatility_expansion_v1"
MOVEMENT_TYPE = "EVENT_VOLATILITY_EXPANSION"


def _event_state_active(ctx: StrategyContext) -> bool:
    value = (ctx.metadata or {}).get("event_state", (ctx.metadata or {}).get("event_active"))
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        value = value.get("active", value.get("confirmed", value.get("state")))
    return str(value or "").strip().upper() in {"1", "TRUE", "YES", "ACTIVE", "CONFIRMED", "EVENT", "LIVE"}


def generate_event_volatility_expansion_candidates(ctx: StrategyContext, regime: MovementRegimeResult) -> tuple[StrategyCandidate, ...]:
    """Generate candidates only when event, volatility, price, and volume all agree."""
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_expansion = float(params.get("MIN_VOL_EXPANSION_SCORE", 0.40))
    min_impulse = float(params.get("MIN_IMPULSE_FROM_VWAP_PCT", 0.0025))
    max_chase = float(params.get("MAX_CHASE_DISTANCE_PCT", 0.014))

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    atr_ratio = _atr_ratio(ctx)
    volume = safe_float(ctx.volume_z)
    if spot is None or vwap is None or atr_ratio is None or volume is None:
        return ()
    if not str(ctx.volatility_state or "").strip():
        return ()
    if not _event_state_active(ctx):
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None or abs(vwap_move) < min_impulse or abs(vwap_move) > max_chase:
        return ()
    expansion_score = _expansion_score(ctx, regime)
    if expansion_score < min_expansion:
        return ()

    direction = "BUY_CALL" if vwap_move > 0 else "BUY_PUT"
    expansion_type = "upside_volatility_expansion" if vwap_move > 0 else "downside_volatility_expansion"
    return (_build_candidate(ctx, regime, direction, expansion_score, abs(vwap_move), expansion_type),)


def _build_candidate(ctx: StrategyContext, regime: MovementRegimeResult, direction: str, expansion_score: float, impulse_abs: float, expansion_type: str) -> StrategyCandidate:
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_impulse = float(params.get("MIN_IMPULSE_FROM_VWAP_PCT", 0.0025))
    max_chase = float(params.get("MAX_CHASE_DISTANCE_PCT", 0.014))
    min_volume_z = float(params.get("MIN_VOLUME_Z", 1.2))
    min_atr_ratio = float(params.get("MIN_ATR_EXPANSION_RATIO", 1.15))
    side = side_evidence(ctx, direction)
    atr_ratio = _atr_ratio(ctx)
    volume = safe_float(ctx.volume_z)
    price_structure_score = clamp_score(
        0.40 * expansion_score
        + 0.30 * ratio_score(impulse_abs, start=min_impulse, full=max_chase)
        + 0.20 * ratio_score(volume, start=min_volume_z, full=3.0)
        + 0.10 * ratio_score(atr_ratio, start=min_atr_ratio, full=2.0)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_impulse_abs_pct": impulse_abs,
        "expansion_type": expansion_type,
        "expansion_score": expansion_score,
        "event_state": True,
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
        entry_trigger="confirmed_event_state_with_volatility_expansion_and_directional_price",
        invalid_if="event_state_clears_volatility_contracts_or_option_quote_degrades",
        rank_reason="explicit event state aligns with complete ATR/volume expansion evidence and directional price",
        evidence=evidence,
        warnings=(),
        confluence_tags=("event_state", "volatility_expansion", "directional_impulse", "option_confirmation"),
        suppression_tags=("avoid_late_spike_chase",),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.params_hash if profile else None,
        promotion_state="ADVISORY_ONLY",
    )


def _expansion_score(ctx: StrategyContext, regime: MovementRegimeResult) -> float:
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_volume_z = float(params.get("MIN_VOLUME_Z", 1.2))
    min_atr_ratio = float(params.get("MIN_ATR_EXPANSION_RATIO", 1.15))
    atr_ratio = _atr_ratio(ctx)
    volume = safe_float(ctx.volume_z)
    if atr_ratio is None or volume is None or not str(ctx.volatility_state or "").strip() or not _event_state_active(ctx):
        return 0.0
    regime_score = safe_float(regime.scores.get("VOLATILITY_EXPANSION")) or 0.0
    volatility_state_bonus = 1.0 if str(ctx.volatility_state).strip().upper() in {"EXPANDING", "EXPANSION", "VOL_EXPANSION", "HIGH", "HIGH_VOLATILITY"} else 0.0
    return clamp_score(
        0.35 * regime_score
        + 0.30 * ratio_score(atr_ratio, start=min_atr_ratio, full=2.0)
        + 0.20 * ratio_score(volume, start=min_volume_z, full=3.0)
        + 0.10 * volatility_state_bonus
        + 0.05
    )


def _atr_ratio(ctx: StrategyContext) -> float | None:
    atr_short = safe_float(ctx.atr_short)
    atr_long = safe_float(ctx.atr_long)
    if atr_short is None or atr_long is None or atr_long <= 0:
        return None
    return atr_short / atr_long


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_event_volatility_expansion_candidates"]
