"""Conservative directional exposure normalization for candidate rows.

This module does not generate candidates, rank candidates, or change execution.
It only infers a stable exposure summary from already-emitted candidate data.
Unknown exposure stays conservative and does not invent bullish or bearish bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

EXPOSURE_BULLISH = "BULLISH"
EXPOSURE_BEARISH = "BEARISH"
EXPOSURE_RANGE = "RANGE"
EXPOSURE_UNKNOWN = "UNKNOWN"

SETUP_DIRECTIONAL = "DIRECTIONAL"
SETUP_RANGE_COMPATIBLE = "RANGE_COMPATIBLE"
SETUP_UNKNOWN = "UNKNOWN"

_BULLISH_TOKENS = frozenset({"BUY_CALL", "CALL", "CE", "BULLISH", "BUY", "LONG", "UP"})
_BEARISH_TOKENS = frozenset({"BUY_PUT", "PUT", "PE", "BEARISH", "SELL", "SHORT", "DOWN"})
_RANGE_TOKENS = frozenset(
    {
        "RANGE",
        "SIDEWAYS",
        "MEAN_REVERSION",
        "VWAP_MEAN_REVERSION",
        "VWAP_RECLAIM_REJECTION",
        "OPENING_RANGE_RETEST",
        "FAILED_BREAKOUT_TRAP",
        "EXHAUSTION_REVERSAL",
        "NO_TRADE_CHOP",
    }
)
_DIRECTIONAL_SETUP_TOKENS = frozenset(
    {
        "BREAKOUT",
        "TREND",
        "MOMENTUM",
        "PULLBACK",
        "OPENING_DRIVE",
        "LATE_DAY_MOMENTUM",
        "EVENT_VOLATILITY_EXPANSION",
        "OPTION_PRESSURE_CONFIRMATION",
    }
)
_RANGE_SETUP_TOKENS = frozenset(
    {
        "MEAN_REVERSION",
        "RANGE",
        "SIDEWAYS",
        "RECLAIM",
        "REJECTION",
        "FAILED_BREAKOUT",
        "EXHAUSTION",
        "CHOP",
    }
)
_CHOP_CONTEXT_TOKENS = frozenset({"CHOP", "NOISE", "UNCLEAR"})


@dataclass(frozen=True)
class DirectionalExposure:
    exposure: str
    setup_kind: str
    confidence: float
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "exposure": self.exposure,
            "setup_kind": self.setup_kind,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


def normalize_directional_exposure(row: Mapping[str, Any] | Any) -> DirectionalExposure:
    payload = _row(row)
    bull_score = 0.0
    bear_score = 0.0
    range_score = 0.0
    setup_kind = SETUP_UNKNOWN
    evidence: list[str] = []

    direction = _upper(payload.get("direction") or payload.get("side") or payload.get("direction_family"))
    if direction in _BULLISH_TOKENS:
        bull_score += 1.0
        evidence.append("direction_bullish")
    elif direction in _BEARISH_TOKENS:
        bear_score += 1.0
        evidence.append("direction_bearish")
    elif direction in _RANGE_TOKENS:
        range_score += 1.0
        evidence.append("direction_range")

    option_type = _upper(payload.get("option_type") or payload.get("type") or payload.get("right"))
    if option_type in {"CE", "CALL"}:
        bull_score += 0.8
        evidence.append("option_type_bullish")
    elif option_type in {"PE", "PUT"}:
        bear_score += 0.8
        evidence.append("option_type_bearish")

    signal_direction = _upper(payload.get("signal_direction") or payload.get("signal"))
    if signal_direction:
        if signal_direction in _RANGE_TOKENS or any(token in signal_direction for token in ("RANGE", "MEAN_REVERSION", "SIDEWAYS", "CHOP", "NOISE", "UNCLEAR")):
            range_score += 0.8
            evidence.append("signal_range")
        elif signal_direction in _BULLISH_TOKENS or any(token in signal_direction for token in ("UP", "LONG", "CALL", "CE")):
            bull_score += 0.6
            evidence.append("signal_bullish")
        elif signal_direction in _BEARISH_TOKENS or any(token in signal_direction for token in ("DOWN", "SHORT", "PUT", "PE")):
            bear_score += 0.6
            evidence.append("signal_bearish")

    strategy_family = _lower(payload.get("strategy_family"))
    movement_type = _upper(payload.get("movement_type"))
    regime = _upper(payload.get("regime"))

    if any(token in strategy_family for token in ("mean_reversion", "range")) or any(token in movement_type for token in _RANGE_TOKENS) or regime in {"RANGE", "SIDEWAYS"}:
        range_score += 1.1
        setup_kind = SETUP_RANGE_COMPATIBLE
        evidence.append("setup_range_compatible")
    elif any(token in strategy_family for token in ("breakout", "trend", "momentum", "pullback")) or any(token in movement_type for token in _DIRECTIONAL_SETUP_TOKENS) or regime in {"TREND_UP", "TREND_DOWN", "TREND"}:
        setup_kind = SETUP_DIRECTIONAL
        evidence.append("setup_directional")

    if bull_score > bear_score and bull_score > range_score:
        exposure = EXPOSURE_BULLISH
    elif bear_score > bull_score and bear_score > range_score:
        exposure = EXPOSURE_BEARISH
    elif range_score > 0.0 and range_score >= bull_score and range_score >= bear_score:
        exposure = EXPOSURE_RANGE
    else:
        exposure = EXPOSURE_UNKNOWN

    if exposure == EXPOSURE_UNKNOWN and setup_kind == SETUP_RANGE_COMPATIBLE and range_score > 0.0:
        exposure = EXPOSURE_RANGE
    if exposure == EXPOSURE_UNKNOWN and regime in _CHOP_CONTEXT_TOKENS and setup_kind == SETUP_RANGE_COMPATIBLE:
        exposure = EXPOSURE_RANGE

    confidence = _clamp01(max(bull_score, bear_score, range_score) / 2.0)
    return DirectionalExposure(
        exposure=exposure,
        setup_kind=setup_kind,
        confidence=confidence,
        evidence=tuple(sorted(set(evidence))) if evidence else (),
    )


def _row(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    to_dict = getattr(row, "to_dict", None)
    if callable(to_dict):
        candidate = to_dict()
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return dict(getattr(row, "__dict__", {}) or {})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "DirectionalExposure",
    "EXPOSURE_BEARISH",
    "EXPOSURE_BULLISH",
    "EXPOSURE_RANGE",
    "EXPOSURE_UNKNOWN",
    "SETUP_DIRECTIONAL",
    "SETUP_RANGE_COMPATIBLE",
    "SETUP_UNKNOWN",
    "normalize_directional_exposure",
]
