"""Movement regime classifier for the opportunity engine.

This module is read-only and deterministic. It classifies market movement state
for future strategy activation. It does not emit trades, call brokers, call order
APIs, change execution gates, touch depth subscriptions, or tune strategies.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.movement_contract import MovementContractError, StrategyContext

REGIME_LABELS: tuple[str, ...] = (
    "TREND_UP",
    "TREND_DOWN",
    "RANGE",
    "CHOP",
    "COMPRESSION",
    "VOLATILITY_EXPANSION",
    "TRAP_RISK",
    "EXHAUSTION_RISK",
    "EXPIRY_CONTEXT",
    "INCONCLUSIVE",
)

SAFE_PRIMARY_REGIME = "INCONCLUSIVE"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def _score_ratio(value: float | None, *, start: float, full: float) -> float:
    if value is None:
        return 0.0
    if full <= start:
        return 0.0
    return _clamp((float(value) - float(start)) / (float(full) - float(start)))


def _distance_pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return abs(float(a) - float(b)) / abs(float(b))


def _signed_distance_pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return (float(a) - float(b)) / abs(float(b))


def _has_supporting_option_pressure(ctx: StrategyContext, *, direction: str) -> bool:
    if direction == "UP":
        ce = _safe_float(ctx.ce_premium_change)
        pe = _safe_float(ctx.pe_premium_change)
        return (ce is not None and ce > 0) or (pe is not None and pe < 0)
    if direction == "DOWN":
        ce = _safe_float(ctx.ce_premium_change)
        pe = _safe_float(ctx.pe_premium_change)
        return (pe is not None and pe > 0) or (ce is not None and ce < 0)
    return False


def _opposes_option_pressure(ctx: StrategyContext, *, direction: str) -> bool:
    ce = _safe_float(ctx.ce_premium_change)
    pe = _safe_float(ctx.pe_premium_change)
    if direction == "UP":
        return bool((ce is not None and ce <= 0) and (pe is None or pe >= 0))
    if direction == "DOWN":
        return bool((pe is not None and pe <= 0) and (ce is None or ce >= 0))
    return False


def _top_score(scores: dict[str, float]) -> tuple[str, float]:
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return SAFE_PRIMARY_REGIME, 1.0
    label, value = ranked[0]
    if value <= 0.0:
        return SAFE_PRIMARY_REGIME, 1.0
    return label, value


@dataclass(frozen=True)
class MovementRegimeResult:
    """Probability-style regime output for future strategy activation."""

    schema_version: int
    primary_regime: str
    scores: dict[str, float]
    warnings: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    CURRENT_SCHEMA_VERSION: int = 1

    def __post_init__(self) -> None:
        schema = int(self.schema_version)
        if schema != self.CURRENT_SCHEMA_VERSION:
            raise MovementContractError(f"unsupported_movement_regime_schema:{schema}")
        primary = str(self.primary_regime or "").strip().upper()
        if primary not in REGIME_LABELS:
            raise MovementContractError(f"invalid_primary_regime:{primary}")
        if not isinstance(self.scores, dict):
            raise MovementContractError("regime_scores_not_dict")
        normalized_scores: dict[str, float] = {}
        for label in REGIME_LABELS:
            value = _safe_float(self.scores.get(label, 0.0))
            normalized_scores[label] = _clamp(value or 0.0)
        warnings = tuple(str(item).strip() for item in (self.warnings or ()) if str(item).strip())
        evidence = dict(self.evidence or {}) if isinstance(self.evidence, dict) else {}
        object.__setattr__(self, "schema_version", schema)
        object.__setattr__(self, "primary_regime", primary)
        object.__setattr__(self, "scores", normalized_scores)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "generated_epoch", _safe_float(self.generated_epoch) or time.time())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["warnings"] = list(self.warnings)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


class MovementRegimeClassifier:
    """Deterministic movement-state classifier.

    Scores are intentionally heuristic in v1. They exist to activate future
    strategies safely and explainably, not to make execution decisions.
    """

    def classify(self, ctx: StrategyContext | dict[str, Any]) -> MovementRegimeResult:
        if isinstance(ctx, dict):
            ctx = StrategyContext(**ctx)
        if not isinstance(ctx, StrategyContext):
            raise MovementContractError("movement_regime_context_invalid")

        warnings: list[str] = []
        evidence: dict[str, Any] = {}
        spot = _safe_float(ctx.spot_ltp)
        vwap = _safe_float(ctx.vwap)
        day_high = _safe_float(ctx.day_high)
        day_low = _safe_float(ctx.day_low)
        orb_high = _safe_float(ctx.orb_high)
        orb_low = _safe_float(ctx.orb_low)
        atr = _safe_float(ctx.atr)
        atr_short = _safe_float(ctx.atr_short)
        atr_long = _safe_float(ctx.atr_long)
        range_width_pct = _safe_float(ctx.range_width_pct)
        volume_z = _safe_float(ctx.volume_z)
        vwap_slope = _safe_float(ctx.vwap_slope)
        option_age = _safe_float(ctx.option_ltp_age_sec)
        ce_spread = _safe_float(ctx.ce_spread_pct)
        pe_spread = _safe_float(ctx.pe_spread_pct)

        if spot is None:
            warnings.append("spot_ltp_missing")
        if vwap is None:
            warnings.append("vwap_missing")

        signed_vwap_dist = _signed_distance_pct(spot, vwap)
        abs_vwap_dist = _distance_pct(spot, vwap)
        evidence["signed_vwap_distance_pct"] = signed_vwap_dist
        evidence["abs_vwap_distance_pct"] = abs_vwap_dist
        evidence["range_width_pct"] = range_width_pct
        evidence["atr_short"] = atr_short
        evidence["atr_long"] = atr_long
        evidence["volume_z"] = volume_z
        evidence["fallback_used"] = bool(ctx.fallback_used)
        evidence["quote_source"] = ctx.quote_source

        trend_up = 0.0
        trend_down = 0.0
        if signed_vwap_dist is not None:
            trend_strength = _score_ratio(abs(signed_vwap_dist), start=0.0008, full=0.004)
            if signed_vwap_dist > 0:
                trend_up += 0.45 * trend_strength
            elif signed_vwap_dist < 0:
                trend_down += 0.45 * trend_strength
        if vwap_slope is not None:
            slope_strength = _score_ratio(abs(vwap_slope), start=0.005, full=0.08)
            if vwap_slope > 0:
                trend_up += 0.25 * slope_strength
            elif vwap_slope < 0:
                trend_down += 0.25 * slope_strength
        if _has_supporting_option_pressure(ctx, direction="UP"):
            trend_up += 0.20
        if _has_supporting_option_pressure(ctx, direction="DOWN"):
            trend_down += 0.20
        if day_high is not None and day_low is not None and spot is not None and day_high > day_low:
            position = _clamp((spot - day_low) / (day_high - day_low))
            evidence["day_range_position"] = position
            if position >= 0.70:
                trend_up += 0.10 * _score_ratio(position, start=0.70, full=0.95)
            if position <= 0.30:
                trend_down += 0.10 * _score_ratio(1.0 - position, start=0.70, full=0.95)
        else:
            evidence["day_range_position"] = None

        compression = 0.0
        if range_width_pct is not None:
            # Smaller range width means more compression.
            compression += 0.45 * _clamp((0.35 - range_width_pct) / 0.35)
        if atr_short is not None and atr_long is not None and atr_long > 0:
            atr_ratio = atr_short / atr_long
            evidence["atr_short_long_ratio"] = atr_ratio
            if atr_ratio < 0.75:
                compression += 0.35 * _clamp((0.75 - atr_ratio) / 0.75)
            if atr_ratio > 1.15:
                vol_expansion = 0.45 * _clamp((atr_ratio - 1.15) / 0.85)
            else:
                vol_expansion = 0.0
        else:
            evidence["atr_short_long_ratio"] = None
            vol_expansion = 0.0
        if abs_vwap_dist is not None and abs_vwap_dist <= 0.0015:
            compression += 0.20

        range_score = 0.0
        if abs_vwap_dist is not None and abs_vwap_dist <= 0.0025:
            range_score += 0.30
        if range_width_pct is not None and range_width_pct <= 0.55:
            range_score += 0.25
        if volume_z is not None and volume_z < 0.6:
            range_score += 0.15
        range_score += 0.15 * (1.0 - _clamp(max(trend_up, trend_down)))

        chop = 0.0
        if abs_vwap_dist is not None and abs_vwap_dist <= 0.001:
            chop += 0.20
        if range_width_pct is not None and range_width_pct <= 0.25:
            chop += 0.25
        if volume_z is not None and volume_z < 0.25:
            chop += 0.20
        if ctx.fallback_used:
            chop += 0.15
        if option_age is not None and option_age > 3.0:
            chop += 0.10
        if ce_spread is not None and pe_spread is not None and min(ce_spread, pe_spread) > 4.0:
            chop += 0.10

        if volume_z is not None and volume_z > 1.2:
            vol_expansion += 0.25 * _score_ratio(volume_z, start=1.2, full=3.0)
        if abs_vwap_dist is not None:
            vol_expansion += 0.15 * _score_ratio(abs_vwap_dist, start=0.0025, full=0.009)

        trap_risk = 0.0
        above_orb = bool(spot is not None and orb_high is not None and spot > orb_high)
        below_orb = bool(spot is not None and orb_low is not None and spot < orb_low)
        near_day_high = bool(spot is not None and day_high is not None and day_high > 0 and abs(day_high - spot) / day_high <= 0.0015)
        near_day_low = bool(spot is not None and day_low is not None and day_low > 0 and abs(spot - day_low) / day_low <= 0.0015)
        evidence["above_orb_high"] = above_orb
        evidence["below_orb_low"] = below_orb
        evidence["near_day_high"] = near_day_high
        evidence["near_day_low"] = near_day_low
        if (above_orb or near_day_high) and _opposes_option_pressure(ctx, direction="UP"):
            trap_risk += 0.55
        if (below_orb or near_day_low) and _opposes_option_pressure(ctx, direction="DOWN"):
            trap_risk += 0.55
        if ctx.fallback_used:
            trap_risk += 0.10

        exhaustion = 0.0
        if abs_vwap_dist is not None and abs_vwap_dist >= 0.006:
            exhaustion += 0.35 * _score_ratio(abs_vwap_dist, start=0.006, full=0.015)
        if (near_day_high and _opposes_option_pressure(ctx, direction="UP")) or (near_day_low and _opposes_option_pressure(ctx, direction="DOWN")):
            exhaustion += 0.30
        if volume_z is not None and volume_z < 0.5 and abs_vwap_dist is not None and abs_vwap_dist >= 0.004:
            exhaustion += 0.20

        expiry_context = 1.0 if bool(ctx.expiry_context) else 0.0

        inconclusive = 0.0
        missing_core = int(spot is None) + int(vwap is None)
        if missing_core:
            inconclusive += 0.55
        if not any(value is not None for value in (range_width_pct, atr, atr_short, atr_long, volume_z, day_high, day_low)):
            inconclusive += 0.25
        if ctx.fallback_used:
            warnings.append("fallback_used_in_context")
        if option_age is not None and option_age > 3.0:
            warnings.append("option_ltp_stale_for_regime_context")

        scores = {
            "TREND_UP": _clamp(trend_up),
            "TREND_DOWN": _clamp(trend_down),
            "RANGE": _clamp(range_score),
            "CHOP": _clamp(chop),
            "COMPRESSION": _clamp(compression),
            "VOLATILITY_EXPANSION": _clamp(vol_expansion),
            "TRAP_RISK": _clamp(trap_risk),
            "EXHAUSTION_RISK": _clamp(exhaustion),
            "EXPIRY_CONTEXT": _clamp(expiry_context),
            "INCONCLUSIVE": _clamp(inconclusive),
        }

        primary, primary_score = _top_score(scores)
        if primary_score < 0.25:
            primary = SAFE_PRIMARY_REGIME
            scores["INCONCLUSIVE"] = max(scores["INCONCLUSIVE"], 0.5)
            warnings.append("weak_regime_signal")

        evidence["primary_score"] = scores.get(primary, 0.0)
        return MovementRegimeResult(
            schema_version=1,
            primary_regime=primary,
            scores=scores,
            warnings=tuple(warnings),
            evidence=evidence,
        )


def classify_movement_regime(ctx: StrategyContext | dict[str, Any]) -> MovementRegimeResult:
    return MovementRegimeClassifier().classify(ctx)


__all__ = [
    "MovementRegimeClassifier",
    "MovementRegimeResult",
    "REGIME_LABELS",
    "SAFE_PRIMARY_REGIME",
    "classify_movement_regime",
]
