"""Deterministic read-only bullish / no-trade / bearish classifier.

This module is intentionally execution-inert.  It consumes already-authoritative
live features and returns a market-state decision plus structural levels.  It
never fetches broker data, selects an option, creates order intent, or calls a
broker API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping

SCHEMA_VERSION = 1
SOURCE = "MARKET_STATE_ENGINE_V1"

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NO_TRADE = "NO_TRADE"

ENTRY_BULL = 45.0
EXIT_BULL = 25.0
ENTRY_BEAR = -45.0
EXIT_BEAR = -25.0

WEIGHTS = {
    "vwap": 25.0,
    "ema": 20.0,
    "structure": 15.0,
    "momentum": 15.0,
    "breadth": 10.0,
    "open": 10.0,
    "futures": 5.0,
}

CRITICAL_KEYS = ("price", "vwap", "atr", "quote_age_sec")


@dataclass(frozen=True)
class MarketStateDecision:
    symbol: str
    zone: str
    score: float
    confidence: float
    entry_state: str
    bull_trend_price: float | None
    bull_reversal_price: float | None
    bear_trend_price: float | None
    bear_reversal_price: float | None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    components: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def read_only(self) -> bool:
        return True

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": SOURCE,
            "symbol": self.symbol,
            "zone": self.zone,
            "score": self.score,
            "confidence": self.confidence,
            "entry_state": self.entry_state,
            "levels": {
                "bull_trend_price": self.bull_trend_price,
                "bull_reversal_price": self.bull_reversal_price,
                "bear_trend_price": self.bear_trend_price,
                "bear_reversal_price": self.bear_reversal_price,
            },
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "components": dict(self.components),
            "diagnostics": dict(self.diagnostics),
            "read_only": True,
            "execution_capable": False,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_execution_authorized": False,
            "is_order_action": False,
            "broker_api_called": False,
        }


def classify_market_state(
    snapshot: Mapping[str, Any] | None,
    *,
    symbol: str,
    previous_zone: str | None = None,
    max_quote_age_sec: float = 5.0,
) -> MarketStateDecision:
    data = dict(snapshot or {})
    clean_symbol = str(symbol or "MARKET").upper()
    blockers = _critical_blockers(data, max_quote_age_sec=max_quote_age_sec)
    if blockers:
        return MarketStateDecision(
            symbol=clean_symbol,
            zone=NO_TRADE,
            score=0.0,
            confidence=0.0,
            entry_state="BLOCKED",
            bull_trend_price=None,
            bull_reversal_price=None,
            bear_trend_price=None,
            bear_reversal_price=None,
            blockers=tuple(blockers),
            diagnostics={"fail_closed": True},
        )

    price = _f(data["price"])
    vwap = _f(data["vwap"])
    atr = _f(data["atr"])
    assert price is not None and vwap is not None and atr is not None and atr > 0

    components = {
        "vwap": _clip((price - vwap) / atr),
        "ema": _ema_component(data, atr),
        "structure": _clip(_f(data.get("structure_score")) or 0.0),
        "momentum": _clip(_f(data.get("momentum_score")) or 0.0),
        "breadth": _breadth_component(data),
        "open": _clip(_f(data.get("open_location_score")) or 0.0),
        "futures": _clip(_f(data.get("futures_confirmation_score")) or 0.0),
    }
    score = round(sum(WEIGHTS[name] * value for name, value in components.items()), 2)
    zone = _zone_with_hysteresis(score, previous_zone)

    warnings: list[str] = []
    entry_state = "ELIGIBLE_DIRECTIONALLY" if zone != NO_TRADE else "WAIT"
    distance_atr = abs(price - vwap) / atr
    resistance = _f(data.get("resistance"))
    support = _f(data.get("support"))
    if distance_atr >= 1.25:
        warnings.append("PRICE_EXTENDED_FROM_VWAP")
        entry_state = "NO_TRADE_EXTENDED"
    if zone == BULLISH and resistance is not None and 0 <= resistance - price <= 0.25 * atr:
        warnings.append("NEAR_RESISTANCE")
        entry_state = "WAIT_PULLBACK"
    if zone == BEARISH and support is not None and 0 <= price - support <= 0.25 * atr:
        warnings.append("NEAR_SUPPORT")
        entry_state = "WAIT_PULLBACK"

    levels = _levels(data, price=price, vwap=vwap, atr=atr)
    confidence = _confidence(score=score, components=components, blockers=blockers)
    return MarketStateDecision(
        symbol=clean_symbol,
        zone=zone,
        score=score,
        confidence=confidence,
        entry_state=entry_state,
        bull_trend_price=levels["bull_trend_price"],
        bull_reversal_price=levels["bull_reversal_price"],
        bear_trend_price=levels["bear_trend_price"],
        bear_reversal_price=levels["bear_reversal_price"],
        blockers=(),
        warnings=tuple(sorted(set(warnings))),
        components={k: round(v, 4) for k, v in components.items()},
        diagnostics={
            "distance_from_vwap_atr": round((price - vwap) / atr, 4),
            "previous_zone": previous_zone,
            "hysteresis": {
                "enter_bull": ENTRY_BULL,
                "exit_bull": EXIT_BULL,
                "enter_bear": ENTRY_BEAR,
                "exit_bear": EXIT_BEAR,
            },
        },
    )


def classify_cross_index_consensus(states: Mapping[str, MarketStateDecision]) -> dict[str, Any]:
    usable = [s for s in states.values() if not s.blockers]
    if len(usable) < 2:
        return {"consensus": NO_TRADE, "reason": "INSUFFICIENT_CROSS_INDEX_AUTHORITY", "read_only": True}
    bull = sum(s.zone == BULLISH for s in usable)
    bear = sum(s.zone == BEARISH for s in usable)
    if bull >= 2 and bear == 0:
        consensus = BULLISH
        reason = "CROSS_INDEX_BULL_CONFIRMATION"
    elif bear >= 2 and bull == 0:
        consensus = BEARISH
        reason = "CROSS_INDEX_BEAR_CONFIRMATION"
    else:
        consensus = NO_TRADE
        reason = "CROSS_INDEX_CONFLICT"
    return {
        "consensus": consensus,
        "reason": reason,
        "members": {k: v.zone for k, v in states.items()},
        "read_only": True,
        "execution_capable": False,
    }


def _critical_blockers(data: Mapping[str, Any], *, max_quote_age_sec: float) -> list[str]:
    blockers: list[str] = []
    for key in CRITICAL_KEYS:
        value = _f(data.get(key))
        if value is None:
            blockers.append(f"MISSING_{key.upper()}")
    atr = _f(data.get("atr"))
    if atr is not None and atr <= 0:
        blockers.append("ATR_NON_POSITIVE")
    age = _f(data.get("quote_age_sec"))
    if age is not None and age > max_quote_age_sec:
        blockers.append("STALE_QUOTE")
    if data.get("feed_authority") is False:
        blockers.append("FEED_AUTHORITY_BLOCKED")
    if data.get("session_open") is False:
        blockers.append("SESSION_NOT_OPEN")
    return sorted(set(blockers))


def _ema_component(data: Mapping[str, Any], atr: float) -> float:
    fast = _f(data.get("ema_fast"))
    slow = _f(data.get("ema_slow"))
    slope = _f(data.get("ema_slope_atr"))
    parts: list[float] = []
    if fast is not None and slow is not None:
        parts.append(_clip((fast - slow) / atr))
    if slope is not None:
        parts.append(_clip(slope))
    return sum(parts) / len(parts) if parts else 0.0


def _breadth_component(data: Mapping[str, Any]) -> float:
    weighted = _f(data.get("weighted_breadth"))
    plain = _f(data.get("breadth"))
    momentum = _f(data.get("breadth_momentum"))
    parts = [_clip(v) for v in (weighted, plain, momentum) if v is not None]
    return sum(parts) / len(parts) if parts else 0.0


def _zone_with_hysteresis(score: float, previous_zone: str | None) -> str:
    previous = str(previous_zone or "").upper()
    if previous == BULLISH and score >= EXIT_BULL:
        return BULLISH
    if previous == BEARISH and score <= EXIT_BEAR:
        return BEARISH
    if score >= ENTRY_BULL:
        return BULLISH
    if score <= ENTRY_BEAR:
        return BEARISH
    return NO_TRADE


def _levels(data: Mapping[str, Any], *, price: float, vwap: float, atr: float) -> dict[str, float]:
    buffer_ = max(0.10 * atr, _f(data.get("minimum_level_buffer")) or 0.0)
    orb_high = _f(data.get("orb_high"))
    orb_low = _f(data.get("orb_low"))
    swing_high = _f(data.get("swing_high"))
    swing_low = _f(data.get("swing_low"))
    resistance = _f(data.get("resistance"))
    support = _f(data.get("support"))

    bull_candidates = [vwap + buffer_]
    bear_candidates = [vwap - buffer_]
    if orb_high is not None:
        bull_candidates.append(orb_high + buffer_)
    if swing_high is not None:
        bull_candidates.append(swing_high + buffer_)
    if orb_low is not None:
        bear_candidates.append(orb_low - buffer_)
    if swing_low is not None:
        bear_candidates.append(swing_low - buffer_)

    bull_reversal_candidates = [vwap - buffer_]
    bear_reversal_candidates = [vwap + buffer_]
    if swing_low is not None:
        bull_reversal_candidates.append(swing_low - buffer_)
    if support is not None:
        bull_reversal_candidates.append(support - buffer_)
    if swing_high is not None:
        bear_reversal_candidates.append(swing_high + buffer_)
    if resistance is not None:
        bear_reversal_candidates.append(resistance + buffer_)

    return {
        "bull_trend_price": round(max(bull_candidates), 2),
        "bull_reversal_price": round(max(bull_reversal_candidates), 2),
        "bear_trend_price": round(min(bear_candidates), 2),
        "bear_reversal_price": round(min(bear_reversal_candidates), 2),
    }


def _confidence(*, score: float, components: Mapping[str, float], blockers: list[str]) -> float:
    if blockers:
        return 0.0
    directional_agreement = sum(1 for v in components.values() if (v > 0 and score > 0) or (v < 0 and score < 0))
    agreement = directional_agreement / max(1, len(components))
    magnitude = min(1.0, abs(score) / 75.0)
    return round(min(1.0, 0.55 * magnitude + 0.45 * agreement), 4)


def _f(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


__all__ = [
    "BEARISH", "BULLISH", "NO_TRADE", "MarketStateDecision",
    "classify_market_state", "classify_cross_index_consensus",
]
