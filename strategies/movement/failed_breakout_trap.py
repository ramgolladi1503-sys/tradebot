"""Failed Breakout / Trap movement strategy.

A trap is valid only when completed bars prove a break first and a strictly later
re-entry second. Metadata flags are retained only as diagnostics and never as
sufficient proof of the setup. Missing option-pressure evidence never counts as
stall confirmation.
"""
from __future__ import annotations

from core.movement_contract import StrategyCandidate, StrategyContext
from core.strategy_parameter_profiles import get_default_profile
from core.movement_regime import MovementRegimeResult
from strategies.movement._temporal_evidence import failed_break_reentry
from strategies.movement._utils import clamp_score, make_candidate, ratio_score, safe_float, side_evidence

STRATEGY_ID = "failed_breakout_trap_v1"
MOVEMENT_TYPE = "FAILED_BREAKOUT_TRAP"


def generate_failed_breakout_trap_candidates(ctx: StrategyContext, regime: MovementRegimeResult) -> tuple[StrategyCandidate, ...]:
    """Generate opposite-side candidates only after completed-bar break/re-entry proof."""
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    min_score = float(params.get("MIN_TRAP_EVIDENCE_SCORE", 0.45))
    min_break = float(params.get("MIN_FAILED_BREAK_DISTANCE_PCT", 0.0006))
    max_reentry = float(params.get("MAX_REENTRY_DISTANCE_PCT", 0.0035))
    spot = safe_float(ctx.spot_ltp)
    if spot is None:
        return ()

    candidates: list[StrategyCandidate] = []
    high = _failed_high_level(ctx)
    if high is not None and spot < high:
        proof = failed_break_reentry(ctx, level=high, side="UP", min_break_distance_pct=min_break)
        if proof is not None:
            distance = (high - spot) / abs(high)
            if distance <= max_reentry:
                option_stall = _option_stall_for_failed_upside(ctx)
                if option_stall is not None:
                    score = _trap_score(ctx, regime, distance, max_reentry, option_stall)
                    if score >= min_score:
                        candidates.append(_build_candidate(ctx, regime, "BUY_PUT", score, "failed_upside_breakout_reentry", high, proof))

    low = _failed_low_level(ctx)
    if low is not None and spot > low:
        proof = failed_break_reentry(ctx, level=low, side="DOWN", min_break_distance_pct=min_break)
        if proof is not None:
            distance = (spot - low) / abs(low)
            if distance <= max_reentry:
                option_stall = _option_stall_for_failed_downside(ctx)
                if option_stall is not None:
                    score = _trap_score(ctx, regime, distance, max_reentry, option_stall)
                    if score >= min_score:
                        candidates.append(_build_candidate(ctx, regime, "BUY_CALL", score, "failed_downside_breakdown_reentry", low, proof))
    return tuple(candidates)


def _trap_score(ctx: StrategyContext, regime: MovementRegimeResult, reentry_distance: float, max_reentry: float, option_stall: float) -> float:
    return clamp_score(
        0.40 * ratio_score(reentry_distance, start=0.0, full=max_reentry)
        + 0.30 * clamp_score(regime.scores.get("TRAP_RISK", 0.0))
        + 0.20 * option_stall
        + 0.10 * ratio_score(abs(safe_float(ctx.volume_z) or 0.0), start=0.4, full=2.0)
    )


def _build_candidate(ctx: StrategyContext, regime: MovementRegimeResult, direction: str, trap_score: float, trap_type: str, failed_level: float, proof: dict[str, float]) -> StrategyCandidate:
    profile = get_default_profile(STRATEGY_ID, "v1")
    params = profile.params if profile else {}
    side = side_evidence(ctx, direction)
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "day_high": ctx.day_high,
        "day_low": ctx.day_low,
        "orb_high": ctx.orb_high,
        "orb_low": ctx.orb_low,
        "completed_bar_history": True,
        "trap_type": trap_type,
        "trap_score": trap_score,
        "failed_level": failed_level,
        "break_extreme": proof["break_extreme"],
        "reentry_close": proof["reentry_close"],
        "break_index": proof["break_index"],
        "reentry_index": proof["reentry_index"],
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
        price_structure_score=trap_score,
        side=side,
        entry_trigger="completed_break_then_later_completed_reentry_with_opposite_option_confirmation",
        invalid_if="price_rebreaks_failed_level_or_option_quote_degrades",
        rank_reason="completed bars prove a break followed by a later range re-entry",
        evidence=evidence,
        warnings=(),
        confluence_tags=("trap", "range_reentry", "completed_bar_history", "opposite_option_confirmation"),
        suppression_tags=("suppress_weak_breakout_followthrough",),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.params_hash if profile else None,
        promotion_state="ADVISORY_ONLY",
    )


def _failed_high_level(ctx: StrategyContext) -> float | None:
    for value in (ctx.orb_high, ctx.nearest_resistance):
        level = safe_float(value)
        if level is not None and level > 0:
            return level
    return None


def _failed_low_level(ctx: StrategyContext) -> float | None:
    for value in (ctx.orb_low, ctx.nearest_support):
        level = safe_float(value)
        if level is not None and level > 0:
            return level
    return None


def _option_stall_for_failed_upside(ctx: StrategyContext) -> float | None:
    ce_change = safe_float(ctx.ce_premium_change)
    pe_change = safe_float(ctx.pe_premium_change)
    if ce_change is None or pe_change is None:
        return None
    ce_stall = 1.0 if ce_change <= 0 else clamp_score(1.0 - ratio_score(ce_change, start=0.0, full=12.0))
    pe_confirm = ratio_score(pe_change, start=0.0, full=15.0)
    return clamp_score(0.55 * ce_stall + 0.45 * pe_confirm)


def _option_stall_for_failed_downside(ctx: StrategyContext) -> float | None:
    pe_change = safe_float(ctx.pe_premium_change)
    ce_change = safe_float(ctx.ce_premium_change)
    if pe_change is None or ce_change is None:
        return None
    pe_stall = 1.0 if pe_change <= 0 else clamp_score(1.0 - ratio_score(pe_change, start=0.0, full=12.0))
    ce_confirm = ratio_score(ce_change, start=0.0, full=15.0)
    return clamp_score(0.55 * pe_stall + 0.45 * ce_confirm)


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_failed_breakout_trap_candidates"]
