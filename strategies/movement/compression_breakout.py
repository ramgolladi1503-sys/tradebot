"""Compression Breakout movement strategy.

A candidate is emitted only when a completed, strictly pre-decision bar window
proves compression and the current observation subsequently breaks that frozen
range. Snapshot-only compression assertions are not accepted.
"""
from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import RuntimeProfileResolution, resolve_required_profile_parameters
from strategies.movement._temporal_evidence import compression_window
from strategies.movement._utils import (
    block_on_required_fields,
    clamp_score,
    make_candidate,
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

STRATEGY_ID = "compression_breakout_v1"
MOVEMENT_TYPE = "COMPRESSION_BREAKOUT"
EMBEDDED_PROFILE_DEFAULTS = {
    "MAX_ATR_RATIO": 0.75,
    "MAX_RANGE_WIDTH_PCT": 0.35,
    "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
    "MIN_COMPRESSION_SCORE": 0.5,
    "MIN_VWAP_ALIGNMENT_PCT": 0.0004,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)
COMPRESSION_LOOKBACK_BARS = 6


def generate_compression_breakout_candidates(ctx: StrategyContext, regime: MovementRegimeResult) -> tuple[StrategyCandidate, ...]:
    """Require completed-bar compression first, then a later current-price breakout."""
    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_compression_score = float(params["MIN_COMPRESSION_SCORE"])
    min_breakout_distance_pct = float(params["MIN_BREAKOUT_DISTANCE_PCT"])
    min_vwap_alignment_pct = float(params["MIN_VWAP_ALIGNMENT_PCT"])

    if block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_thesis_evidence",
        field_specs=(("spot_ltp", ctx.spot_ltp, "positive"), ("vwap", ctx.vwap, "positive"), ("atr_short", ctx.atr_short, "positive"), ("atr_long", ctx.atr_long, "positive")),
    ):
        return ()
    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    temporal = compression_window(ctx, lookback=COMPRESSION_LOOKBACK_BARS)
    if temporal is None:
        return ()
    upper_level, lower_level, completed_range_width_pct = temporal
    compression_score = _compression_evidence_score(completed_range_width_pct, ctx, regime, params)
    if compression_score < min_compression_score:
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None:
        return ()
    candidates: list[StrategyCandidate] = []
    upside = (spot - upper_level) / abs(upper_level)
    if upside >= min_breakout_distance_pct and vwap_move >= min_vwap_alignment_pct:
        candidates.append(_build_candidate(ctx, regime, profile, "BUY_CALL", compression_score, upside, abs(vwap_move), upper_level, lower_level, completed_range_width_pct))
    downside = (lower_level - spot) / abs(lower_level)
    if downside >= min_breakout_distance_pct and vwap_move <= -min_vwap_alignment_pct:
        candidates.append(_build_candidate(ctx, regime, profile, "BUY_PUT", compression_score, downside, abs(vwap_move), lower_level, upper_level, completed_range_width_pct))
    return tuple(candidates)


def _build_candidate(ctx, regime, profile: RuntimeProfileResolution, direction, compression_score, breakout_distance, vwap_alignment, breakout_level, opposite_level, completed_range_width_pct):
    params = dict(profile.parameters)
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * compression_score
        + 0.35 * ratio_score(breakout_distance, start=float(params["MIN_BREAKOUT_DISTANCE_PCT"]), full=0.006)
        + 0.20 * ratio_score(vwap_alignment, start=float(params["MIN_VWAP_ALIGNMENT_PCT"]), full=0.004)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "completed_bar_history": True,
        "compression_lookback_bars": COMPRESSION_LOOKBACK_BARS,
        "completed_range_width_pct": completed_range_width_pct,
        "atr_short": ctx.atr_short,
        "atr_long": ctx.atr_long,
        "atr_short_long_ratio": _atr_ratio(ctx),
        "compression_score": compression_score,
        "breakout_level": breakout_level,
        "opposite_range_level": opposite_level,
        "breakout_distance_pct": breakout_distance,
        "vwap_alignment_abs_pct": vwap_alignment,
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    return make_candidate(
        ctx=ctx, regime=regime, strategy_id=STRATEGY_ID, movement_type=MOVEMENT_TYPE,
        direction=direction, price_structure_score=price_structure_score, side=side,
        entry_trigger="completed_compression_window_then_later_range_breakout",
        invalid_if="price_returns_inside_frozen_compression_range",
        rank_reason="strictly prior completed bars compressed before a later directional release",
        evidence=evidence, warnings=(), confluence_tags=("compression", "range_breakout", "completed_bar_history"),
        strategy_version="v1", params_used=params, params_hash=profile.parameter_hash, promotion_state="ADVISORY_ONLY",
    )


def _compression_evidence_score(completed_range_width_pct: float, ctx: StrategyContext, regime: MovementRegimeResult, params: dict[str, object]) -> float:
    max_range_width_pct = float(params["MAX_RANGE_WIDTH_PCT"])
    max_atr_ratio = float(params["MAX_ATR_RATIO"])
    atr_ratio = _atr_ratio(ctx)
    if atr_ratio is None or completed_range_width_pct < 0:
        return 0.0
    parts = [
        clamp_score((max_range_width_pct - completed_range_width_pct) / max_range_width_pct),
        clamp_score((max_atr_ratio - atr_ratio) / max_atr_ratio),
    ]
    regime_score = safe_float(regime.scores.get("COMPRESSION"))
    if regime_score is not None:
        parts.append(regime_score)
    return clamp_score(sum(parts) / len(parts))


def _atr_ratio(ctx: StrategyContext) -> float | None:
    atr_short = safe_float(ctx.atr_short)
    atr_long = safe_float(ctx.atr_long)
    if atr_short is None or atr_long is None or atr_long <= 0:
        return None
    return atr_short / atr_long


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_compression_breakout_candidates"]
