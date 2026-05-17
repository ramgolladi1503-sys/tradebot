"""Shared helpers for movement strategy candidate generators.

These helpers are deliberately pure and read-only. They do not call brokers,
submit orders, alter execution gates, touch depth subscriptions, or tune live
trading behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult

MAX_OPTION_LTP_AGE_SEC = 2.5
MAX_OPTION_SPREAD_PCT = 4.0
MIN_OPTION_DEPTH = 1.0
MIN_PREMIUM_CONFIRMATION = 0.0


@dataclass(frozen=True)
class SideEvidence:
    direction: str
    option_ltp: float | None
    premium_change: float | None
    spread_pct: float | None
    depth: float | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    option_confirmation_score: float
    liquidity_score: float
    freshness_score: float


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def clamp_score(value: float | None, low: float = 0.0, high: float = 1.0) -> float:
    if value is None or not math.isfinite(float(value)):
        return low
    return max(low, min(high, float(value)))


def ratio_score(value: float | None, *, start: float, full: float) -> float:
    value = safe_float(value)
    if value is None or full <= start:
        return 0.0
    return clamp_score((value - start) / (full - start))


def pct_distance(value: float | None, anchor: float | None) -> float | None:
    value = safe_float(value)
    anchor = safe_float(anchor)
    if value is None or anchor is None or anchor == 0:
        return None
    return abs(value - anchor) / abs(anchor)


def signed_pct_distance(value: float | None, anchor: float | None) -> float | None:
    value = safe_float(value)
    anchor = safe_float(anchor)
    if value is None or anchor is None or anchor == 0:
        return None
    return (value - anchor) / abs(anchor)


def side_evidence(ctx: StrategyContext, direction: str) -> SideEvidence:
    direction = str(direction or "").upper()
    if direction == "BUY_CALL":
        option_ltp = safe_float(ctx.option_ce_ltp)
        premium_change = safe_float(ctx.ce_premium_change)
        spread_pct = safe_float(ctx.ce_spread_pct)
        depth = safe_float(ctx.ce_depth)
    elif direction == "BUY_PUT":
        option_ltp = safe_float(ctx.option_pe_ltp)
        premium_change = safe_float(ctx.pe_premium_change)
        spread_pct = safe_float(ctx.pe_spread_pct)
        depth = safe_float(ctx.pe_depth)
    else:
        raise ValueError(f"unsupported_direction:{direction}")

    blockers: list[str] = []
    warnings: list[str] = []
    if ctx.fallback_used or "fallback" in str(ctx.quote_source or "").lower():
        blockers.append("FALLBACK_QUOTE_ONLY")
    if option_ltp is None or option_ltp <= 0:
        blockers.append("OPTION_CONFIRMATION_MISSING")
    if premium_change is None or premium_change <= MIN_PREMIUM_CONFIRMATION:
        blockers.append("OPTION_CONFIRMATION_MISSING")
    if spread_pct is None:
        blockers.append("WIDE_SPREAD")
        warnings.append("spread_missing")
    elif spread_pct > MAX_OPTION_SPREAD_PCT:
        blockers.append("WIDE_SPREAD")
    if depth is None:
        blockers.append("MISSING_DEPTH")
        warnings.append("depth_missing")
    elif depth < MIN_OPTION_DEPTH:
        blockers.append("MISSING_DEPTH")
    age = safe_float(ctx.option_ltp_age_sec)
    if age is None:
        blockers.append("STALE_OPTION_LTP")
        warnings.append("option_ltp_age_missing")
    elif age > MAX_OPTION_LTP_AGE_SEC:
        blockers.append("STALE_OPTION_LTP")

    option_confirmation_score = 0.0 if premium_change is None else ratio_score(premium_change, start=0.0, full=20.0)
    if option_ltp is None or option_ltp <= 0:
        option_confirmation_score = 0.0

    if spread_pct is None:
        spread_score = 0.0
    else:
        spread_score = clamp_score(1.0 - (spread_pct / MAX_OPTION_SPREAD_PCT))
    if depth is None:
        depth_score = 0.0
    else:
        depth_score = clamp_score(depth / 1000.0)
    liquidity_score = clamp_score((spread_score * 0.7) + (depth_score * 0.3))

    if age is None:
        freshness_score = 0.0
    else:
        freshness_score = clamp_score(1.0 - (age / MAX_OPTION_LTP_AGE_SEC))

    return SideEvidence(
        direction=direction,
        option_ltp=option_ltp,
        premium_change=premium_change,
        spread_pct=spread_pct,
        depth=depth,
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
        option_confirmation_score=option_confirmation_score,
        liquidity_score=liquidity_score,
        freshness_score=freshness_score,
    )


def volume_score(ctx: StrategyContext) -> float:
    return ratio_score(safe_float(ctx.volume_z), start=0.5, full=2.0)


def regime_alignment_score(regime: MovementRegimeResult, direction: str) -> float:
    direction = str(direction or "").upper()
    if direction == "BUY_CALL":
        return clamp_score(
            0.65 * regime.scores.get("TREND_UP", 0.0)
            + 0.20 * regime.scores.get("VOLATILITY_EXPANSION", 0.0)
            + 0.15 * regime.scores.get("COMPRESSION", 0.0)
        )
    if direction == "BUY_PUT":
        return clamp_score(
            0.65 * regime.scores.get("TREND_DOWN", 0.0)
            + 0.20 * regime.scores.get("VOLATILITY_EXPANSION", 0.0)
            + 0.15 * regime.scores.get("COMPRESSION", 0.0)
        )
    return 0.0


def make_candidate(
    *,
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    strategy_id: str,
    movement_type: str,
    direction: str,
    price_structure_score: float,
    side: SideEvidence,
    entry_trigger: str,
    invalid_if: str,
    rank_reason: str,
    evidence: dict[str, Any],
    warnings: tuple[str, ...] = (),
    confluence_tags: tuple[str, ...] = (),
    suppression_tags: tuple[str, ...] = (),
) -> StrategyCandidate:
    blockers = tuple(sorted(set(side.blockers)))
    merged_warnings = tuple(sorted(set(tuple(side.warnings) + tuple(warnings))))
    vol_score = volume_score(ctx)
    align_score = regime_alignment_score(regime, direction)
    timing_score = opening_timing_score(ctx)
    trap_risk_score = clamp_score(regime.scores.get("TRAP_RISK", 0.0))
    confluence_score = clamp_score(
        0.25 * price_structure_score
        + 0.25 * side.option_confirmation_score
        + 0.20 * side.liquidity_score
        + 0.15 * side.freshness_score
        + 0.15 * align_score
    )
    raw_score = confluence_score
    confidence_score = clamp_score(raw_score * (1.0 - (trap_risk_score * 0.25)))
    status = "BLOCKED_CANDIDATE" if blockers else "VALIDATED_CANDIDATE"
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol=ctx.symbol,
        direction=direction,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        raw_score=raw_score,
        confidence_score=confidence_score,
        price_structure_score=clamp_score(price_structure_score),
        option_confirmation_score=side.option_confirmation_score,
        liquidity_score=side.liquidity_score,
        freshness_score=side.freshness_score,
        volatility_score=vol_score,
        regime_alignment_score=align_score,
        timing_score=timing_score,
        trap_risk_score=trap_risk_score,
        confluence_score=confluence_score,
        entry_trigger=entry_trigger,
        invalid_if=invalid_if,
        rank_reason=rank_reason,
        blockers=blockers,
        warnings=merged_warnings,
        confluence_tags=confluence_tags,
        suppression_tags=suppression_tags,
        source_signals=(strategy_id, movement_type),
        regime_scores=regime.scores,
        evidence=evidence,
        lineage={"source": "movement_strategy", "strategy_id": strategy_id},
    )


def opening_timing_score(ctx: StrategyContext) -> float:
    minutes = safe_float(ctx.minutes_since_open)
    if minutes is None:
        return 0.5
    if minutes < 0:
        return 0.0
    if minutes <= 20:
        return 1.0
    if minutes <= 45:
        return clamp_score(1.0 - ((minutes - 20.0) / 25.0))
    return 0.0


__all__ = [
    "MAX_OPTION_LTP_AGE_SEC",
    "MAX_OPTION_SPREAD_PCT",
    "MIN_OPTION_DEPTH",
    "SideEvidence",
    "clamp_score",
    "make_candidate",
    "opening_timing_score",
    "pct_distance",
    "ratio_score",
    "regime_alignment_score",
    "safe_float",
    "side_evidence",
    "signed_pct_distance",
    "volume_score",
]
