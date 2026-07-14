"""Option confirmation assessment layer for movement candidates.

This module is pure/read-only. It assesses CE/PE pressure, quote quality,
freshness, spread, depth, and fallback state. It does not execute, rank, submit,
or mutate live runtime behavior.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

from core.movement_contract import StrategyCandidate, StrategyContext

DominantDirection = Literal["BUY_CALL", "BUY_PUT", "NEUTRAL"]
SuggestedEffect = Literal["PROMOTE", "DEMOTE", "NEUTRAL", "BLOCK"]

MAX_OPTION_LTP_AGE_SEC = 2.5
MAX_OPTION_SPREAD_PCT = 4.0
MIN_OPTION_DEPTH = 1.0
MIN_DOMINANCE_DELTA = 0.12


@dataclass(frozen=True)
class OptionSideAssessment:
    side: str
    direction: str
    option_ltp: float | None
    premium_change: float | None
    spread_pct: float | None
    depth: float | None
    option_ltp_age_sec: float | None
    premium_score: float
    liquidity_score: float
    freshness_score: float
    pressure_score: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def has_hard_blocker(self) -> bool:
        return bool(self.blockers)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data


@dataclass(frozen=True)
class OptionPressureAssessment:
    schema_version: int
    dominant_direction: DominantDirection
    bullish_score: float
    bearish_score: float
    dominance_delta: float
    ce: OptionSideAssessment
    pe: OptionSideAssessment
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ce"] = self.ce.to_dict()
        data["pe"] = self.pe.to_dict()
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


@dataclass(frozen=True)
class CandidateOptionConfirmation:
    candidate_strategy_id: str
    candidate_direction: str
    suggested_effect: SuggestedEffect
    confirmation_score: float
    opposing_score: float
    dominance_delta: float
    dominant_direction: DominantDirection
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def assess_option_pressure(ctx: StrategyContext) -> OptionPressureAssessment:
    """Assess CE/PE pressure without mutating candidates or runtime state."""

    ce = _assess_side(
        side="CE",
        direction="BUY_CALL",
        option_ltp=ctx.option_ce_ltp,
        premium_change=ctx.ce_premium_change,
        spread_pct=ctx.ce_spread_pct,
        depth=ctx.ce_depth,
        option_ltp_age_sec=ctx.option_ltp_age_sec,
        fallback_used=ctx.fallback_used,
        quote_source=ctx.quote_source,
    )
    pe = _assess_side(
        side="PE",
        direction="BUY_PUT",
        option_ltp=ctx.option_pe_ltp,
        premium_change=ctx.pe_premium_change,
        spread_pct=ctx.pe_spread_pct,
        depth=ctx.pe_depth,
        option_ltp_age_sec=ctx.option_ltp_age_sec,
        fallback_used=ctx.fallback_used,
        quote_source=ctx.quote_source,
    )

    pe_weakness = 0.0 if pe.premium_change is None else (1.0 if pe.premium_change <= 0 else clamp_score(1.0 - pe.premium_score))
    ce_weakness = 0.0 if ce.premium_change is None else (1.0 if ce.premium_change <= 0 else clamp_score(1.0 - ce.premium_score))
    bullish_score = clamp_score(0.75 * ce.pressure_score + 0.25 * pe_weakness)
    bearish_score = clamp_score(0.75 * pe.pressure_score + 0.25 * ce_weakness)
    delta = abs(bullish_score - bearish_score)
    if delta < MIN_DOMINANCE_DELTA:
        dominant: DominantDirection = "NEUTRAL"
    elif bullish_score > bearish_score:
        dominant = "BUY_CALL"
    else:
        dominant = "BUY_PUT"

    blockers = tuple(sorted(set(ce.blockers + pe.blockers)))
    warnings = list(sorted(set(ce.warnings + pe.warnings)))
    if dominant == "NEUTRAL":
        warnings.append("no_dominant_option_pressure")
    if ce.pressure_score > 0.45 and pe.pressure_score > 0.45:
        warnings.append("both_option_sides_active")

    evidence = {
        "quote_source": ctx.quote_source,
        "fallback_used": ctx.fallback_used,
        "option_ltp_age_sec": ctx.option_ltp_age_sec,
        "metadata_keys": sorted(str(key) for key in (ctx.metadata or {}).keys()),
    }
    return OptionPressureAssessment(
        schema_version=1,
        dominant_direction=dominant,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        dominance_delta=delta,
        ce=ce,
        pe=pe,
        blockers=blockers,
        warnings=tuple(sorted(set(warnings))),
        evidence=evidence,
    )


def confirm_candidate_option_pressure(
    candidate: StrategyCandidate,
    ctx: StrategyContext,
) -> CandidateOptionConfirmation:
    """Return explainable promotion/demotion evidence for a candidate.

    This function does not edit the candidate and cannot make anything executable.
    """

    assessment = assess_option_pressure(ctx)
    direction = candidate.direction
    if direction == "BUY_CALL":
        confirmation_score = assessment.bullish_score
        opposing_score = assessment.bearish_score
        side_blockers = assessment.ce.blockers
    elif direction == "BUY_PUT":
        confirmation_score = assessment.bearish_score
        opposing_score = assessment.bullish_score
        side_blockers = assessment.pe.blockers
    else:
        confirmation_score = 0.0
        opposing_score = max(assessment.bullish_score, assessment.bearish_score)
        side_blockers = ()

    blockers = tuple(sorted(set(tuple(side_blockers) + tuple(candidate.blockers))))
    warnings = list(assessment.warnings)
    if candidate.has_hard_blocker:
        warnings.append("candidate_already_hard_blocked")

    if blockers:
        effect: SuggestedEffect = "BLOCK"
    elif assessment.dominant_direction == direction and confirmation_score >= 0.45:
        effect = "PROMOTE"
    elif opposing_score > confirmation_score + MIN_DOMINANCE_DELTA:
        effect = "DEMOTE"
    else:
        effect = "NEUTRAL"

    return CandidateOptionConfirmation(
        candidate_strategy_id=candidate.strategy_id,
        candidate_direction=direction,
        suggested_effect=effect,
        confirmation_score=confirmation_score,
        opposing_score=opposing_score,
        dominance_delta=assessment.dominance_delta,
        dominant_direction=assessment.dominant_direction,
        blockers=blockers,
        warnings=tuple(sorted(set(warnings))),
        evidence={"assessment": assessment.to_dict(), "candidate_status": candidate.status},
    )


def _assess_side(
    *,
    side: str,
    direction: str,
    option_ltp: Any,
    premium_change: Any,
    spread_pct: Any,
    depth: Any,
    option_ltp_age_sec: Any,
    fallback_used: bool,
    quote_source: str | None,
) -> OptionSideAssessment:
    ltp = safe_float(option_ltp)
    premium = safe_float(premium_change)
    spread = safe_float(spread_pct)
    depth_value = safe_float(depth)
    age = safe_float(option_ltp_age_sec)

    blockers: list[str] = []
    warnings: list[str] = []
    if fallback_used or "fallback" in str(quote_source or "").lower():
        blockers.append("FALLBACK_QUOTE_ONLY")
    if ltp is None or ltp <= 0:
        blockers.append("OPTION_CONFIRMATION_MISSING")
    if premium is None or premium <= 0:
        blockers.append("OPTION_CONFIRMATION_MISSING")
    if spread is None:
        blockers.append("WIDE_SPREAD")
        warnings.append("spread_missing")
    elif spread > MAX_OPTION_SPREAD_PCT:
        blockers.append("WIDE_SPREAD")
    if depth_value is None:
        blockers.append("MISSING_DEPTH")
        warnings.append("depth_missing")
    elif depth_value < MIN_OPTION_DEPTH:
        blockers.append("MISSING_DEPTH")
    if age is None:
        blockers.append("STALE_OPTION_LTP")
        warnings.append("option_ltp_age_missing")
    elif age > MAX_OPTION_LTP_AGE_SEC:
        blockers.append("STALE_OPTION_LTP")

    premium_score = 0.0 if premium is None else ratio_score(premium, start=0.0, full=20.0)
    if ltp is None or ltp <= 0:
        premium_score = 0.0
    spread_score = 0.0 if spread is None else clamp_score(1.0 - spread / MAX_OPTION_SPREAD_PCT)
    depth_score = 0.0 if depth_value is None else clamp_score(depth_value / 1000.0)
    liquidity_score = clamp_score(0.70 * spread_score + 0.30 * depth_score)
    freshness_score = 0.0 if age is None else clamp_score(1.0 - age / MAX_OPTION_LTP_AGE_SEC)
    pressure_score = clamp_score(
        0.45 * premium_score
        + 0.25 * liquidity_score
        + 0.20 * freshness_score
        + 0.10 * (1.0 if ltp is not None and ltp > 0 else 0.0)
    )

    return OptionSideAssessment(
        side=side,
        direction=direction,
        option_ltp=ltp,
        premium_change=premium,
        spread_pct=spread,
        depth=depth_value,
        option_ltp_age_sec=age,
        premium_score=premium_score,
        liquidity_score=liquidity_score,
        freshness_score=freshness_score,
        pressure_score=pressure_score,
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
    )


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


__all__ = [
    "CandidateOptionConfirmation",
    "DominantDirection",
    "MAX_OPTION_LTP_AGE_SEC",
    "MAX_OPTION_SPREAD_PCT",
    "MIN_DOMINANCE_DELTA",
    "MIN_OPTION_DEPTH",
    "OptionPressureAssessment",
    "OptionSideAssessment",
    "SuggestedEffect",
    "assess_option_pressure",
    "confirm_candidate_option_pressure",
]
