"""Read-only regime state machine built from MarketState evidence.

EDGE-64 consumes the EDGE-63 MarketState contract and converts descriptive market
conditions into one deterministic regime label plus transition metadata. It does
not select strategies, rank candidates, tune live thresholds, write runtime
files, call brokers, or create order intent.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.market_state import (
    BREADTH_BEARISH,
    BREADTH_BULLISH,
    LIQUIDITY_THIN,
    SESSION_CLOSED,
    SESSION_OPENING,
    SESSION_PREOPEN,
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UP,
    UNKNOWN,
    VOL_EXTREME,
    VOL_HIGH,
    VOL_LOW,
    VOL_NORMAL,
    MarketState,
)

REGIME_STATE_SCHEMA_VERSION = 1
REGIME_STATE_SOURCE = "regime_state_machine_v1"

REGIME_UNKNOWN = "UNKNOWN"
REGIME_OUT_OF_SESSION = "OUT_OF_SESSION"
REGIME_OPENING_DISCOVERY = "OPENING_DISCOVERY"
REGIME_BULL_TREND = "BULL_TREND"
REGIME_BEAR_TREND = "BEAR_TREND"
REGIME_RANGE_BOUND = "RANGE_BOUND"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"
REGIME_VOLATILITY_STRESSED = "VOLATILITY_STRESSED"
REGIME_LIQUIDITY_STRESSED = "LIQUIDITY_STRESSED"
REGIME_MIXED_UNCERTAIN = "MIXED_UNCERTAIN"

TRANSITION_UNKNOWN = "UNKNOWN"
TRANSITION_INITIAL = "INITIAL"
TRANSITION_STABLE = "STABLE"
TRANSITION_CHANGED = "CHANGED"

REGIME_INSUFFICIENT_MARKET_STATE = "regime_insufficient_market_state"
REGIME_OUT_OF_SESSION_BLOCKER = "regime_out_of_session"
REGIME_LIQUIDITY_STRESSED_BLOCKER = "regime_liquidity_stressed"
REGIME_VOLATILITY_STRESSED_BLOCKER = "regime_volatility_stressed"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_VALID_REGIMES = {
    REGIME_UNKNOWN,
    REGIME_OUT_OF_SESSION,
    REGIME_OPENING_DISCOVERY,
    REGIME_BULL_TREND,
    REGIME_BEAR_TREND,
    REGIME_RANGE_BOUND,
    REGIME_HIGH_VOLATILITY,
    REGIME_VOLATILITY_STRESSED,
    REGIME_LIQUIDITY_STRESSED,
    REGIME_MIXED_UNCERTAIN,
}


@dataclass(frozen=True)
class RegimeTransition:
    """Regime transition metadata with no execution meaning."""

    previous_regime: str | None
    current_regime: str
    transition_type: str
    changed: bool
    reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "previous_regime": self.previous_regime,
            "current_regime": self.current_regime,
            "transition_type": self.transition_type,
            "changed": self.changed,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RegimeState:
    """Read-only regime state machine output."""

    schema_version: int
    read_only: bool
    append: bool
    source: str
    mode: str
    symbol: str
    regime: str
    transition: RegimeTransition
    confidence: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    market_state_summary: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def stable(self) -> bool:
        return self.transition.transition_type == TRANSITION_STABLE

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "mode": self.mode,
            "symbol": self.symbol,
            "regime": self.regime,
            "transition": self.transition.to_payload(),
            "stable": self.stable,
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "reasons": list(self.reasons),
            "market_state_summary": dict(self.market_state_summary),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


@dataclass(frozen=True)
class _RegimeClassification:
    regime: str
    confidence: float
    reasons: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_regime_state(
    market_state: MarketState | Mapping[str, Any] | None,
    *,
    previous_regime: str | None = None,
    source: str = REGIME_STATE_SOURCE,
) -> RegimeState:
    """Build a read-only regime state from MarketState evidence."""

    payload = _market_state_payload(market_state)
    summary = _market_state_summary(payload)
    classification = _classify_regime(summary)
    transition = _build_transition(previous_regime, classification.regime)
    blockers = _dedupe_sorted((*summary["blockers"], *classification.blockers))
    warnings = _dedupe_sorted((*summary["warnings"], *classification.warnings))
    confidence = _round_confidence(summary["confidence"] * classification.confidence)

    return RegimeState(
        schema_version=REGIME_STATE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        mode=summary["mode"],
        symbol=summary["symbol"],
        regime=classification.regime,
        transition=transition,
        confidence=confidence,
        blockers=blockers,
        warnings=warnings,
        reasons=classification.reasons,
        market_state_summary=summary,
        metadata={
            "model": REGIME_STATE_SOURCE,
            "scope": "read_only_descriptive_regime_state_no_strategy_selection",
            "uses_market_state_schema_version": summary["schema_version"],
        },
    )


def _classify_regime(summary: Mapping[str, Any]) -> _RegimeClassification:
    dimensions = summary["dimensions"]
    trend = dimensions["trend"]
    volatility = dimensions["volatility"]
    breadth = dimensions["breadth"]
    liquidity = dimensions["liquidity"]
    session = dimensions["session"]

    if summary["has_blockers"] or UNKNOWN in dimensions.values():
        return _RegimeClassification(
            regime=REGIME_UNKNOWN,
            confidence=0.0,
            reasons=("market_state_not_complete",),
            blockers=(REGIME_INSUFFICIENT_MARKET_STATE,),
        )
    if session in {SESSION_PREOPEN, SESSION_CLOSED}:
        return _RegimeClassification(
            regime=REGIME_OUT_OF_SESSION,
            confidence=0.90,
            reasons=("session_not_tradeable",),
            blockers=(REGIME_OUT_OF_SESSION_BLOCKER,),
        )
    if liquidity == LIQUIDITY_THIN:
        return _RegimeClassification(
            regime=REGIME_LIQUIDITY_STRESSED,
            confidence=0.85,
            reasons=("thin_liquidity_priority",),
            blockers=(REGIME_LIQUIDITY_STRESSED_BLOCKER,),
        )
    if volatility == VOL_EXTREME:
        return _RegimeClassification(
            regime=REGIME_VOLATILITY_STRESSED,
            confidence=0.85,
            reasons=("extreme_volatility_priority",),
            blockers=(REGIME_VOLATILITY_STRESSED_BLOCKER,),
        )
    if session == SESSION_OPENING:
        return _RegimeClassification(
            regime=REGIME_OPENING_DISCOVERY,
            confidence=0.70,
            reasons=("opening_session_discovery",),
            warnings=("opening_session_regime_unstable",),
        )
    if trend == TREND_UP and breadth == BREADTH_BULLISH:
        return _RegimeClassification(
            regime=REGIME_BULL_TREND,
            confidence=0.85,
            reasons=("uptrend_with_bullish_breadth",),
        )
    if trend == TREND_DOWN and breadth == BREADTH_BEARISH:
        return _RegimeClassification(
            regime=REGIME_BEAR_TREND,
            confidence=0.85,
            reasons=("downtrend_with_bearish_breadth",),
        )
    if trend == TREND_SIDEWAYS and volatility in {VOL_LOW, VOL_NORMAL}:
        return _RegimeClassification(
            regime=REGIME_RANGE_BOUND,
            confidence=0.75,
            reasons=("sideways_low_to_normal_volatility",),
        )
    if volatility == VOL_HIGH:
        return _RegimeClassification(
            regime=REGIME_HIGH_VOLATILITY,
            confidence=0.70,
            reasons=("high_volatility_without_clear_direction",),
            warnings=("high_volatility_regime_requires_tighter_future_controls",),
        )
    return _RegimeClassification(
        regime=REGIME_MIXED_UNCERTAIN,
        confidence=0.55,
        reasons=("mixed_market_state_evidence",),
        warnings=("mixed_regime_uncertain",),
    )


def _build_transition(previous_regime: str | None, current_regime: str) -> RegimeTransition:
    previous = _normalize_previous_regime(previous_regime)
    if current_regime == REGIME_UNKNOWN:
        return RegimeTransition(
            previous_regime=previous,
            current_regime=current_regime,
            transition_type=TRANSITION_UNKNOWN,
            changed=False,
            reasons=("current_regime_unknown",),
        )
    if previous is None:
        return RegimeTransition(
            previous_regime=None,
            current_regime=current_regime,
            transition_type=TRANSITION_INITIAL,
            changed=False,
            reasons=("no_previous_regime",),
        )
    if previous == current_regime:
        return RegimeTransition(
            previous_regime=previous,
            current_regime=current_regime,
            transition_type=TRANSITION_STABLE,
            changed=False,
            reasons=("regime_unchanged",),
        )
    return RegimeTransition(
        previous_regime=previous,
        current_regime=current_regime,
        transition_type=TRANSITION_CHANGED,
        changed=True,
        reasons=("regime_changed",),
    )


def _market_state_payload(market_state: MarketState | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(market_state, MarketState):
        return market_state.to_payload()
    if isinstance(market_state, Mapping):
        return dict(market_state)
    return {
        "schema_version": None,
        "mode": UNKNOWN,
        "symbol": "MARKET",
        "confidence": 0.0,
        "blockers": ("market_state_payload_missing",),
        "warnings": (),
    }


def _market_state_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    dimensions = {
        "trend": _dimension_value(payload, "trend"),
        "volatility": _dimension_value(payload, "volatility"),
        "breadth": _dimension_value(payload, "breadth"),
        "liquidity": _dimension_value(payload, "liquidity"),
        "session": _dimension_value(payload, "session"),
    }
    blockers = tuple(str(item) for item in payload.get("blockers") or ())
    warnings = tuple(str(item) for item in payload.get("warnings") or ())
    return {
        "schema_version": payload.get("schema_version"),
        "source": str(payload.get("source") or UNKNOWN),
        "mode": str(payload.get("mode") or UNKNOWN).strip().upper() or UNKNOWN,
        "symbol": str(payload.get("symbol") or "MARKET").strip().upper() or "MARKET",
        "confidence": _round_confidence(_safe_float(payload.get("confidence")) or 0.0),
        "blockers": blockers,
        "warnings": warnings,
        "dimensions": dimensions,
        "has_blockers": bool(blockers),
    }


def _dimension_value(payload: Mapping[str, Any], name: str) -> str:
    dimension = payload.get(name)
    if not isinstance(dimension, Mapping):
        return UNKNOWN
    value = str(dimension.get("value") or UNKNOWN).strip().upper()
    return value or UNKNOWN


def _normalize_previous_regime(previous_regime: str | None) -> str | None:
    if previous_regime in (None, "", "None"):
        return None
    regime = str(previous_regime).strip().upper()
    if not regime or regime == REGIME_UNKNOWN:
        return None
    if regime in _VALID_REGIMES:
        return regime
    return REGIME_UNKNOWN


def _dedupe_sorted(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _round_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


__all__ = [
    "REGIME_BEAR_TREND",
    "REGIME_BULL_TREND",
    "REGIME_HIGH_VOLATILITY",
    "REGIME_INSUFFICIENT_MARKET_STATE",
    "REGIME_LIQUIDITY_STRESSED",
    "REGIME_LIQUIDITY_STRESSED_BLOCKER",
    "REGIME_MIXED_UNCERTAIN",
    "REGIME_OPENING_DISCOVERY",
    "REGIME_OUT_OF_SESSION",
    "REGIME_OUT_OF_SESSION_BLOCKER",
    "REGIME_RANGE_BOUND",
    "REGIME_STATE_SCHEMA_VERSION",
    "REGIME_STATE_SOURCE",
    "REGIME_UNKNOWN",
    "REGIME_VOLATILITY_STRESSED",
    "REGIME_VOLATILITY_STRESSED_BLOCKER",
    "TRANSITION_CHANGED",
    "TRANSITION_INITIAL",
    "TRANSITION_STABLE",
    "TRANSITION_UNKNOWN",
    "RegimeState",
    "RegimeTransition",
    "build_regime_state",
]
