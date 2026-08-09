"""Mean Reversion Extension movement strategy.

Detects range/chop extension back toward VWAP/range mean. This strategy refuses
to fade strong continuation and requires explicit oscillator confirmation before
emitting read-only StrategyCandidate objects.
"""

from __future__ import annotations

from typing import Any

from core.movement_contract import StrategyCandidate, StrategyContext
from core.strategy_parameter_profiles import get_default_profile
from core.movement_regime import MovementRegimeResult
from strategies.movement._utils import (
    clamp_score,
    make_candidate,
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

STRATEGY_ID = "mean_reversion_extension_v1"
MOVEMENT_TYPE = "MEAN_REVERSION_EXTENSION"


def generate_mean_reversion_extension_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate mean-reversion candidates only with anchor and oscillator evidence."""

    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_range_or_chop_score = float(params.get("MIN_RANGE_OR_CHOP_SCORE", 0.45))
    min_extension_from_vwap_pct = float(
        params.get("MIN_EXTENSION_FROM_VWAP_PCT", 0.0035)
    )
    max_extension_from_vwap_pct = float(
        params.get("MAX_EXTENSION_FROM_VWAP_PCT", 0.014)
    )
    max_trend_continuation_score = float(
        params.get("MAX_TREND_CONTINUATION_SCORE", 0.55)
    )

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
    if spot is None or vwap is None:
        return ()

    range_chop_score = max(
        float(regime.scores.get("RANGE", 0.0)), float(regime.scores.get("CHOP", 0.0))
    )
    if range_chop_score < min_range_or_chop_score:
        return ()

    distance = signed_pct_distance(spot, vwap)
    if distance is None or abs(distance) < min_extension_from_vwap_pct:
        return ()
    if abs(distance) > max_extension_from_vwap_pct:
        return ()

    candidates: list[StrategyCandidate] = []
    if (
        distance > 0
        and _trend_continuation_score(ctx, regime, "BUY_CALL")
        <= max_trend_continuation_score
        and _oscillator_confirms_reversion(ctx, "BUY_PUT")
    ):
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                "BUY_PUT",
                range_chop_score,
                abs(distance),
                "upper_extension_reversion",
            )
        )
    if (
        distance < 0
        and _trend_continuation_score(ctx, regime, "BUY_PUT")
        <= max_trend_continuation_score
        and _oscillator_confirms_reversion(ctx, "BUY_CALL")
    ):
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                "BUY_CALL",
                range_chop_score,
                abs(distance),
                "lower_extension_reversion",
            )
        )
    return tuple(candidates)


def _oscillator_snapshot(ctx: StrategyContext) -> dict[str, Any]:
    """Return only explicitly supplied causal oscillator evidence.

    The strategy never invents a default oscillator state. Callers may provide a
    boolean/directional `oscillator_confirmation`, RSI, or z-score in metadata.
    Missing evidence fails closed.
    """

    metadata = ctx.metadata or {}
    confirmation = metadata.get("oscillator_confirmation")
    rsi = safe_float(metadata.get("rsi"))
    zscore = safe_float(metadata.get("zscore", metadata.get("z_score")))
    return {
        "oscillator_confirmation": confirmation,
        "rsi": rsi,
        "zscore": zscore,
    }


def _oscillator_confirms_reversion(ctx: StrategyContext, direction: str) -> bool:
    snapshot = _oscillator_snapshot(ctx)
    explicit = snapshot["oscillator_confirmation"]
    if isinstance(explicit, dict):
        explicit = explicit.get(direction) or explicit.get(direction.lower())
    if isinstance(explicit, bool):
        return explicit
    if isinstance(explicit, str):
        normalized = explicit.strip().upper()
        if normalized in {direction, "CONFIRMED", "TRUE", "YES"}:
            return True
        if normalized in {"FALSE", "NO", "REJECTED"}:
            return False

    rsi = snapshot["rsi"]
    zscore = snapshot["zscore"]
    if direction == "BUY_PUT":
        return bool((rsi is not None and rsi >= 65.0) or (zscore is not None and zscore >= 1.0))
    if direction == "BUY_CALL":
        return bool((rsi is not None and rsi <= 35.0) or (zscore is not None and zscore <= -1.0))
    return False


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    range_chop_score: float,
    extension_abs: float,
    reversion_type: str,
) -> StrategyCandidate:

    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_extension_from_vwap_pct = float(
        params.get("MIN_EXTENSION_FROM_VWAP_PCT", 0.0035)
    )
    max_extension_from_vwap_pct = float(
        params.get("MAX_EXTENSION_FROM_VWAP_PCT", 0.014)
    )
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.45 * range_chop_score
        + 0.35
        * ratio_score(
            extension_abs,
            start=min_extension_from_vwap_pct,
            full=max_extension_from_vwap_pct,
        )
        + 0.20 * _range_boundary_score(ctx, direction)
    )
    oscillator = _oscillator_snapshot(ctx)
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_extension_abs_pct": extension_abs,
        "reversion_type": reversion_type,
        "range_chop_score": range_chop_score,
        "mean_reversion_anchor": "VWAP",
        "oscillator_confirmation": True,
        "oscillator_rsi": oscillator["rsi"],
        "oscillator_zscore": oscillator["zscore"],
        "day_high": ctx.day_high,
        "day_low": ctx.day_low,
        "nearest_support": ctx.nearest_support,
        "nearest_resistance": ctx.nearest_resistance,
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
        entry_trigger="range_extension_with_oscillator_and_opposite_option_confirmation",
        invalid_if="oscillator_confirmation_lost_or_extension_expands_into_trend_continuation_or_option_quote_degrades",
        rank_reason="range/chop extension stretched from VWAP with explicit oscillator reversal confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("mean_reversion", "range_extension", "oscillator_confirmation", "option_confirmation"),
        suppression_tags=("avoid_fading_strong_trend",),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.params_hash if profile else None,
        promotion_state="ADVISORY_ONLY",
    )


def _range_boundary_score(ctx: StrategyContext, direction: str) -> float:
    spot = safe_float(ctx.spot_ltp)
    if spot is None:
        return 0.0
    if direction == "BUY_PUT":
        boundary = safe_float(ctx.nearest_resistance) or safe_float(ctx.day_high)
        if boundary is None or boundary <= 0 or spot > boundary:
            return 0.0
        distance = abs(boundary - spot) / abs(boundary)
        return clamp_score(1.0 - ratio_score(distance, start=0.0, full=0.004))
    if direction == "BUY_CALL":
        boundary = safe_float(ctx.nearest_support) or safe_float(ctx.day_low)
        if boundary is None or boundary <= 0 or spot < boundary:
            return 0.0
        distance = abs(spot - boundary) / abs(boundary)
        return clamp_score(1.0 - ratio_score(distance, start=0.0, full=0.004))
    return 0.0


def _trend_continuation_score(
    ctx: StrategyContext, regime: MovementRegimeResult, direction: str
) -> float:
    if direction == "BUY_CALL":
        premium = safe_float(ctx.ce_premium_change)
        trend = float(regime.scores.get("TREND_UP", 0.0))
    elif direction == "BUY_PUT":
        premium = safe_float(ctx.pe_premium_change)
        trend = float(regime.scores.get("TREND_DOWN", 0.0))
    else:
        premium = None
        trend = 0.0
    volume = safe_float(ctx.volume_z)
    expansion = float(regime.scores.get("VOLATILITY_EXPANSION", 0.0))
    return clamp_score(
        0.40 * trend
        + 0.25 * expansion
        + 0.25 * ratio_score(premium, start=4.0, full=18.0)
        + 0.10 * ratio_score(volume, start=1.0, full=3.0)
    )


__all__ = [
    "STRATEGY_ID",
    "MOVEMENT_TYPE",
    "generate_mean_reversion_extension_candidates",
]
