"""Failed Breakout / Trap movement strategy.

Detects bull-trap and bear-trap style range re-entry after ORB/day-level breaks.
This emits read-only StrategyCandidate objects only and does not alter execution.
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
)

STRATEGY_ID = "failed_breakout_trap_v1"
MOVEMENT_TYPE = "FAILED_BREAKOUT_TRAP"


def generate_failed_breakout_trap_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate opposite-side candidates after failed breakout/breakdown."""

    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_trap_evidence_score = float(params.get("MIN_TRAP_EVIDENCE_SCORE", 0.45))

    spot = safe_float(ctx.spot_ltp)
    if spot is None:
        return ()

    candidates: list[StrategyCandidate] = []
    bull_trap_score = _bull_trap_score(ctx, regime)
    if bull_trap_score >= min_trap_evidence_score:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                "BUY_PUT",
                bull_trap_score,
                "failed_upside_breakout_reentry",
            )
        )

    bear_trap_score = _bear_trap_score(ctx, regime)
    if bear_trap_score >= min_trap_evidence_score:
        candidates.append(
            _build_candidate(
                ctx,
                regime,
                "BUY_CALL",
                bear_trap_score,
                "failed_downside_breakdown_reentry",
            )
        )

    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    direction: str,
    trap_score: float,
    trap_type: str,
) -> StrategyCandidate:
    side = side_evidence(ctx, direction)
    price_structure_score = clamp_score(
        0.55 * trap_score
        + 0.25 * clamp_score(regime.scores.get("TRAP_RISK", 0.0))
        + 0.20 * ratio_score(abs(safe_float(ctx.volume_z) or 0.0), start=0.4, full=2.0)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "day_high": ctx.day_high,
        "day_low": ctx.day_low,
        "orb_high": ctx.orb_high,
        "orb_low": ctx.orb_low,
        "trap_type": trap_type,
        "trap_score": trap_score,
        "previous_break_high": _metadata_float(ctx, "previous_break_high"),
        "previous_break_low": _metadata_float(ctx, "previous_break_low"),
        "price_reentered_range": _metadata_bool(ctx, "price_reentered_range"),
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    suppression_tags = ("suppress_weak_breakout_followthrough",)
    return make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction=direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="failed_breakout_reentry_with_opposite_option_confirmation",
        invalid_if="price_rebreaks_failed_level_or_option_quote_degrades",
        rank_reason="failed breakout/breakdown re-entered range with opposite option confirmation",
        evidence=evidence,
        warnings=(),
        confluence_tags=("trap", "range_reentry", "opposite_option_confirmation"),
        suppression_tags=suppression_tags,
        strategy_version="v1",
        params_used=params,
        params_hash=profile.params_hash if profile else None,
        promotion_state="ADVISORY_ONLY",
    )


def _bull_trap_score(ctx: StrategyContext, regime: MovementRegimeResult) -> float:

    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    max_reentry_distance_pct = float(params.get("MAX_REENTRY_DISTANCE_PCT", 0.0035))
    min_failed_break_distance_pct = float(
        params.get("MIN_FAILED_BREAK_DISTANCE_PCT", 0.0006)
    )
    spot = safe_float(ctx.spot_ltp)
    failed_high = _failed_high_level(ctx)
    if spot is None or failed_high is None or spot >= failed_high:
        return 0.0
    reentry_distance = (failed_high - spot) / abs(failed_high)
    if reentry_distance > max_reentry_distance_pct:
        return 0.0
    previous_break = _metadata_float(ctx, "previous_break_high")
    had_break = previous_break is not None and previous_break > failed_high
    explicit_reentry = _metadata_bool(ctx, "price_reentered_range") or _metadata_bool(
        ctx, "failed_breakout_confirmed"
    )
    if not had_break and not explicit_reentry:
        return 0.0
    option_stall = _option_stall_for_failed_upside(ctx)
    return clamp_score(
        0.40
        * ratio_score(
            reentry_distance,
            start=min_failed_break_distance_pct,
            full=max_reentry_distance_pct,
        )
        + 0.25 * clamp_score(regime.scores.get("TRAP_RISK", 0.0))
        + 0.20 * option_stall
        + 0.15 * (1.0 if explicit_reentry else 0.5)
    )


def _bear_trap_score(ctx: StrategyContext, regime: MovementRegimeResult) -> float:

    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    max_reentry_distance_pct = float(params.get("MAX_REENTRY_DISTANCE_PCT", 0.0035))
    min_failed_break_distance_pct = float(
        params.get("MIN_FAILED_BREAK_DISTANCE_PCT", 0.0006)
    )
    spot = safe_float(ctx.spot_ltp)
    failed_low = _failed_low_level(ctx)
    if spot is None or failed_low is None or spot <= failed_low:
        return 0.0
    reentry_distance = (spot - failed_low) / abs(failed_low)
    if reentry_distance > max_reentry_distance_pct:
        return 0.0
    previous_break = _metadata_float(ctx, "previous_break_low")
    had_break = previous_break is not None and previous_break < failed_low
    explicit_reentry = _metadata_bool(ctx, "price_reentered_range") or _metadata_bool(
        ctx, "failed_breakdown_confirmed"
    )
    if not had_break and not explicit_reentry:
        return 0.0
    option_stall = _option_stall_for_failed_downside(ctx)
    return clamp_score(
        0.40
        * ratio_score(
            reentry_distance,
            start=min_failed_break_distance_pct,
            full=max_reentry_distance_pct,
        )
        + 0.25 * clamp_score(regime.scores.get("TRAP_RISK", 0.0))
        + 0.20 * option_stall
        + 0.15 * (1.0 if explicit_reentry else 0.5)
    )


def _failed_high_level(ctx: StrategyContext) -> float | None:
    for value in (ctx.orb_high, ctx.day_high, ctx.nearest_resistance):
        level = safe_float(value)
        if level is not None and level > 0:
            return level
    return None


def _failed_low_level(ctx: StrategyContext) -> float | None:
    for value in (ctx.orb_low, ctx.day_low, ctx.nearest_support):
        level = safe_float(value)
        if level is not None and level > 0:
            return level
    return None


def _option_stall_for_failed_upside(ctx: StrategyContext) -> float:
    ce_change = safe_float(ctx.ce_premium_change)
    pe_change = safe_float(ctx.pe_premium_change)
    ce_stall = 1.0 if ce_change is None or ce_change <= 0 else 0.0
    pe_confirm = ratio_score(pe_change, start=0.0, full=15.0)
    return clamp_score(0.55 * ce_stall + 0.45 * pe_confirm)


def _option_stall_for_failed_downside(ctx: StrategyContext) -> float:
    pe_change = safe_float(ctx.pe_premium_change)
    ce_change = safe_float(ctx.ce_premium_change)
    pe_stall = 1.0 if pe_change is None or pe_change <= 0 else 0.0
    ce_confirm = ratio_score(ce_change, start=0.0, full=15.0)
    return clamp_score(0.55 * pe_stall + 0.45 * ce_confirm)


def _metadata_bool(ctx: StrategyContext, key: str) -> bool:
    value = (ctx.metadata or {}).get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _metadata_float(ctx: StrategyContext, key: str) -> float | None:
    value: Any = (ctx.metadata or {}).get(key)
    return safe_float(value)


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_failed_breakout_trap_candidates"]
