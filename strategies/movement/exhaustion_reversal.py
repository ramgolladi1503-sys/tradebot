"""Exhaustion Reversal movement strategy.

Detects stretched directional moves that are losing premium/volume support.
Missing volatility, trap, premium, or volume evidence fails closed; absence of
telemetry is never interpreted as exhaustion.
"""
from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.strategy_parameter_profiles import get_default_profile
from core.movement_regime import MovementRegimeResult
from strategies.movement._utils import clamp_score, make_candidate, ratio_score, safe_float, side_evidence, signed_pct_distance

STRATEGY_ID = "exhaustion_reversal_v1"
MOVEMENT_TYPE = "EXHAUSTION_REVERSAL"


def _trap_state_confirmed(ctx: StrategyContext) -> bool:
    value = (ctx.metadata or {}).get("trap_state", (ctx.metadata or {}).get("exhaustion_trap_state"))
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        value = value.get("confirmed", value.get("active", value.get("state")))
    return str(value or "").strip().upper() in {"1", "TRUE", "YES", "CONFIRMED", "ACTIVE", "EXHAUSTION", "TRAP"}


def generate_exhaustion_reversal_candidates(ctx: StrategyContext, regime: MovementRegimeResult) -> tuple[StrategyCandidate, ...]:
    """Generate opposite-side candidates only with complete exhaustion evidence."""
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_stretch = float(params.get("MIN_STRETCH_FROM_VWAP_PCT", 0.005))
    max_stretch = float(params.get("MAX_ENTRY_STRETCH_PCT", 0.018))
    min_score = float(params.get("MIN_EXHAUSTION_SCORE", 0.50))
    max_continuation = float(params.get("MAX_CONTINUATION_PRESSURE_SCORE", 0.55))

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()
    if not str(ctx.volatility_state or "").strip():
        return ()
    if not _trap_state_confirmed(ctx):
        return ()
    # Premium and volume evidence are thesis inputs. Missing data cannot count as a stall.
    if safe_float(ctx.ce_premium_change) is None or safe_float(ctx.pe_premium_change) is None or safe_float(ctx.volume_z) is None:
        return ()

    distance = signed_pct_distance(spot, vwap)
    if distance is None or abs(distance) < min_stretch or abs(distance) > max_stretch:
        return ()

    candidates: list[StrategyCandidate] = []
    if distance > 0:
        score = _upside_exhaustion_score(ctx, regime, abs(distance))
        if score >= min_score and _continuation_pressure_score(ctx, "BUY_CALL") <= max_continuation:
            candidates.append(_build_candidate(ctx, regime, "BUY_PUT", score, abs(distance), "upside_exhaustion"))
    elif distance < 0:
        score = _downside_exhaustion_score(ctx, regime, abs(distance))
        if score >= min_score and _continuation_pressure_score(ctx, "BUY_PUT") <= max_continuation:
            candidates.append(_build_candidate(ctx, regime, "BUY_CALL", score, abs(distance), "downside_exhaustion"))
    return tuple(candidates)


def _build_candidate(ctx: StrategyContext, regime: MovementRegimeResult, direction: str, exhaustion_score: float, stretch_abs: float, exhaustion_type: str) -> StrategyCandidate:
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_stretch = float(params.get("MIN_STRETCH_FROM_VWAP_PCT", 0.005))
    max_stretch = float(params.get("MAX_ENTRY_STRETCH_PCT", 0.018))
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.50 * exhaustion_score
        + 0.25 * clamp_score(regime.scores.get("EXHAUSTION_RISK", 0.0))
        + 0.25 * ratio_score(stretch_abs, start=min_stretch, full=max_stretch)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_stretch_abs_pct": stretch_abs,
        "exhaustion_type": exhaustion_type,
        "exhaustion_score": exhaustion_score,
        "volatility_state": ctx.volatility_state,
        "trap_state": True,
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
        entry_trigger="stretched_move_with_explicit_volatility_trap_and_premium_stall_confirmation",
        invalid_if="trend_side_premium_reaccelerates_or_trap_state_clears_or_option_quote_degrades",
        rank_reason="stretched move has complete exhaustion evidence and opposite option confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("exhaustion", "vwap_stretch", "volatility_state", "trap_state", "opposite_option_confirmation"),
        suppression_tags=("avoid_blind_trend_fade",),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.params_hash if profile else None,
        promotion_state="ADVISORY_ONLY",
    )


def _upside_exhaustion_score(ctx: StrategyContext, regime: MovementRegimeResult, stretch_abs: float) -> float:
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_stretch = float(params.get("MIN_STRETCH_FROM_VWAP_PCT", 0.005))
    max_stretch = float(params.get("MAX_ENTRY_STRETCH_PCT", 0.018))
    ce_change = safe_float(ctx.ce_premium_change)
    pe_change = safe_float(ctx.pe_premium_change)
    volume = safe_float(ctx.volume_z)
    if ce_change is None or pe_change is None or volume is None:
        return 0.0
    ce_stall = clamp_score(1.0 - ratio_score(ce_change, start=0.0, full=12.0))
    pe_confirm = ratio_score(pe_change, start=0.0, full=15.0)
    volume_fade = clamp_score(1.0 - ratio_score(volume, start=0.4, full=2.0))
    return clamp_score(
        0.30 * ratio_score(stretch_abs, start=min_stretch, full=max_stretch)
        + 0.25 * ce_stall + 0.20 * pe_confirm + 0.15 * volume_fade
        + 0.10 * clamp_score(regime.scores.get("EXHAUSTION_RISK", 0.0))
    )


def _downside_exhaustion_score(ctx: StrategyContext, regime: MovementRegimeResult, stretch_abs: float) -> float:
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_stretch = float(params.get("MIN_STRETCH_FROM_VWAP_PCT", 0.005))
    max_stretch = float(params.get("MAX_ENTRY_STRETCH_PCT", 0.018))
    pe_change = safe_float(ctx.pe_premium_change)
    ce_change = safe_float(ctx.ce_premium_change)
    volume = safe_float(ctx.volume_z)
    if pe_change is None or ce_change is None or volume is None:
        return 0.0
    pe_stall = clamp_score(1.0 - ratio_score(pe_change, start=0.0, full=12.0))
    ce_confirm = ratio_score(ce_change, start=0.0, full=15.0)
    volume_fade = clamp_score(1.0 - ratio_score(volume, start=0.4, full=2.0))
    return clamp_score(
        0.30 * ratio_score(stretch_abs, start=min_stretch, full=max_stretch)
        + 0.25 * pe_stall + 0.20 * ce_confirm + 0.15 * volume_fade
        + 0.10 * clamp_score(regime.scores.get("EXHAUSTION_RISK", 0.0))
    )


def _continuation_pressure_score(ctx: StrategyContext, direction: str) -> float:
    premium = safe_float(ctx.ce_premium_change if direction == "BUY_CALL" else ctx.pe_premium_change if direction == "BUY_PUT" else None)
    volume = safe_float(ctx.volume_z)
    if premium is None or volume is None:
        return 1.0  # fail closed: missing anti-thesis evidence blocks fading
    return clamp_score(0.65 * ratio_score(premium, start=4.0, full=20.0) + 0.35 * ratio_score(volume, start=1.0, full=3.0))


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_exhaustion_reversal_candidates"]
