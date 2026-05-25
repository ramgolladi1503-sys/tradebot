"""Read-only MarketState model contract.

EDGE-63 creates a descriptive market-state evidence model only. It does not
select strategies, rank candidates, tune live thresholds, write runtime files,
call brokers, or create order intent. EDGE-64 can later consume this contract to
build a regime state machine.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

MARKET_STATE_SCHEMA_VERSION = 1
MARKET_STATE_SOURCE = "market_state_model_v1"
UNKNOWN = "UNKNOWN"

TREND_UP = "UP"
TREND_DOWN = "DOWN"
TREND_SIDEWAYS = "SIDEWAYS"

VOL_LOW = "LOW"
VOL_NORMAL = "NORMAL"
VOL_HIGH = "HIGH"
VOL_EXTREME = "EXTREME"

BREADTH_BULLISH = "BULLISH"
BREADTH_BEARISH = "BEARISH"
BREADTH_MIXED = "MIXED"

LIQUIDITY_THIN = "THIN"
LIQUIDITY_NORMAL = "NORMAL"
LIQUIDITY_DEEP = "DEEP"

SESSION_PREOPEN = "PREOPEN"
SESSION_OPENING = "OPENING"
SESSION_MIDDAY = "MIDDAY"
SESSION_CLOSING = "CLOSING"
SESSION_CLOSED = "CLOSED"

MARKET_STATE_INSUFFICIENT_EVIDENCE = "market_state_insufficient_evidence"
_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_SNAPSHOT_KEYS: tuple[str, ...] = (
    "index_change_pct",
    "vwap_distance_pct",
    "ema_slope_pct",
    "atr_pct",
    "realized_vol_pct",
    "india_vix",
    "advance_decline_ratio",
    "sector_positive_pct",
    "avg_spread_bps",
    "depth_score",
    "quote_age_sec",
    "market_minute",
    "session_phase",
)


@dataclass(frozen=True)
class MarketStateDimension:
    """One classified market-state dimension with evidence."""

    name: str
    value: str
    confidence: float
    reasons: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class MarketState:
    """Read-only descriptive market-state model."""

    schema_version: int
    read_only: bool
    append: bool
    source: str
    mode: str
    symbol: str
    trend: MarketStateDimension
    volatility: MarketStateDimension
    breadth: MarketStateDimension
    liquidity: MarketStateDimension
    session: MarketStateDimension
    confidence: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_snapshot: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "mode": self.mode,
            "symbol": self.symbol,
            "trend": self.trend.to_payload(),
            "volatility": self.volatility.to_payload(),
            "breadth": self.breadth.to_payload(),
            "liquidity": self.liquidity.to_payload(),
            "session": self.session.to_payload(),
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence_snapshot": dict(self.evidence_snapshot),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_market_state(
    snapshot: Mapping[str, Any] | None,
    *,
    symbol: str = "MARKET",
    mode: str | None = "PAPER",
    source: str = MARKET_STATE_SOURCE,
) -> MarketState:
    """Build a descriptive market-state evidence object from one snapshot."""

    clean_snapshot = _sanitize_snapshot(snapshot)
    trend = _classify_trend(clean_snapshot)
    volatility = _classify_volatility(clean_snapshot)
    breadth = _classify_breadth(clean_snapshot)
    liquidity = _classify_liquidity(clean_snapshot)
    session = _classify_session(clean_snapshot)
    dimensions = (trend, volatility, breadth, liquidity, session)
    blockers = tuple(
        sorted({MARKET_STATE_INSUFFICIENT_EVIDENCE for dimension in dimensions if dimension.value == UNKNOWN})
    )
    warnings = tuple(
        sorted({reason for dimension in dimensions for reason in dimension.reasons if reason.endswith("_missing")})
    )
    confidence = _round_confidence(sum(dimension.confidence for dimension in dimensions) / len(dimensions))
    return MarketState(
        schema_version=MARKET_STATE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        mode=str(mode or "UNKNOWN").strip().upper() or UNKNOWN,
        symbol=str(symbol or "MARKET").strip().upper() or "MARKET",
        trend=trend,
        volatility=volatility,
        breadth=breadth,
        liquidity=liquidity,
        session=session,
        confidence=confidence,
        blockers=blockers,
        warnings=warnings,
        evidence_snapshot=clean_snapshot,
        metadata={
            "model": MARKET_STATE_SOURCE,
            "scope": "read_only_descriptive_market_state_no_strategy_selection",
            "dimension_count": len(dimensions),
        },
    )


def _classify_trend(snapshot: Mapping[str, Any]) -> MarketStateDimension:
    index_change = _safe_float(snapshot.get("index_change_pct"))
    vwap_distance = _safe_float(snapshot.get("vwap_distance_pct"))
    ema_slope = _safe_float(snapshot.get("ema_slope_pct"))
    evidence = {
        "index_change_pct": index_change,
        "vwap_distance_pct": vwap_distance,
        "ema_slope_pct": ema_slope,
    }
    values = [value for value in (index_change, vwap_distance, ema_slope) if value is not None]
    if not values:
        return _unknown_dimension("trend", "trend_evidence_missing", evidence)
    score = sum(values) / len(values)
    if score >= 0.25:
        return _dimension("trend", TREND_UP, 0.75 if len(values) >= 2 else 0.55, ("positive_trend_evidence",), evidence)
    if score <= -0.25:
        return _dimension("trend", TREND_DOWN, 0.75 if len(values) >= 2 else 0.55, ("negative_trend_evidence",), evidence)
    return _dimension("trend", TREND_SIDEWAYS, 0.65 if len(values) >= 2 else 0.50, ("muted_trend_evidence",), evidence)


def _classify_volatility(snapshot: Mapping[str, Any]) -> MarketStateDimension:
    atr_pct = _safe_float(snapshot.get("atr_pct"))
    realized_vol_pct = _safe_float(snapshot.get("realized_vol_pct"))
    india_vix = _safe_float(snapshot.get("india_vix"))
    evidence = {"atr_pct": atr_pct, "realized_vol_pct": realized_vol_pct, "india_vix": india_vix}
    if atr_pct is None and realized_vol_pct is None and india_vix is None:
        return _unknown_dimension("volatility", "volatility_evidence_missing", evidence)
    high_ref = max(value for value in (atr_pct, realized_vol_pct, 0.0) if value is not None)
    if india_vix is not None and india_vix >= 22.0 or high_ref >= 1.25:
        return _dimension("volatility", VOL_EXTREME, 0.80, ("extreme_volatility_evidence",), evidence)
    if india_vix is not None and india_vix >= 17.0 or high_ref >= 0.75:
        return _dimension("volatility", VOL_HIGH, 0.75, ("high_volatility_evidence",), evidence)
    if india_vix is not None and india_vix <= 12.0 and high_ref <= 0.35:
        return _dimension("volatility", VOL_LOW, 0.70, ("low_volatility_evidence",), evidence)
    return _dimension("volatility", VOL_NORMAL, 0.65, ("normal_volatility_evidence",), evidence)


def _classify_breadth(snapshot: Mapping[str, Any]) -> MarketStateDimension:
    advance_decline = _safe_float(snapshot.get("advance_decline_ratio"))
    sector_positive = _safe_float(snapshot.get("sector_positive_pct"))
    evidence = {"advance_decline_ratio": advance_decline, "sector_positive_pct": sector_positive}
    if advance_decline is None and sector_positive is None:
        return _unknown_dimension("breadth", "breadth_evidence_missing", evidence)
    if (advance_decline is not None and advance_decline >= 1.5) or (sector_positive is not None and sector_positive >= 60.0):
        return _dimension("breadth", BREADTH_BULLISH, 0.70, ("bullish_breadth_evidence",), evidence)
    if (advance_decline is not None and advance_decline <= 0.67) or (sector_positive is not None and sector_positive <= 40.0):
        return _dimension("breadth", BREADTH_BEARISH, 0.70, ("bearish_breadth_evidence",), evidence)
    return _dimension("breadth", BREADTH_MIXED, 0.60, ("mixed_breadth_evidence",), evidence)


def _classify_liquidity(snapshot: Mapping[str, Any]) -> MarketStateDimension:
    spread_bps = _safe_float(snapshot.get("avg_spread_bps"))
    depth_score = _safe_float(snapshot.get("depth_score"))
    quote_age_sec = _safe_float(snapshot.get("quote_age_sec"))
    evidence = {"avg_spread_bps": spread_bps, "depth_score": depth_score, "quote_age_sec": quote_age_sec}
    if spread_bps is None and depth_score is None and quote_age_sec is None:
        return _unknown_dimension("liquidity", "liquidity_evidence_missing", evidence)
    if (spread_bps is not None and spread_bps > 50.0) or (depth_score is not None and depth_score < 0.35) or (
        quote_age_sec is not None and quote_age_sec > 5.0
    ):
        return _dimension("liquidity", LIQUIDITY_THIN, 0.75, ("thin_liquidity_evidence",), evidence)
    if (spread_bps is not None and spread_bps <= 15.0) and (depth_score is not None and depth_score >= 0.75):
        return _dimension("liquidity", LIQUIDITY_DEEP, 0.70, ("deep_liquidity_evidence",), evidence)
    return _dimension("liquidity", LIQUIDITY_NORMAL, 0.60, ("normal_liquidity_evidence",), evidence)


def _classify_session(snapshot: Mapping[str, Any]) -> MarketStateDimension:
    explicit = str(snapshot.get("session_phase") or "").strip().upper()
    minute = _safe_float(snapshot.get("market_minute"))
    evidence = {"session_phase": explicit or None, "market_minute": minute}
    if explicit in {SESSION_PREOPEN, SESSION_OPENING, SESSION_MIDDAY, SESSION_CLOSING, SESSION_CLOSED}:
        return _dimension("session", explicit, 0.85, ("explicit_session_phase",), evidence)
    if minute is None:
        return _unknown_dimension("session", "session_evidence_missing", evidence)
    if minute < 0:
        return _dimension("session", SESSION_PREOPEN, 0.70, ("preopen_market_minute",), evidence)
    if minute <= 30:
        return _dimension("session", SESSION_OPENING, 0.70, ("opening_market_minute",), evidence)
    if minute >= 345:
        return _dimension("session", SESSION_CLOSING, 0.70, ("closing_market_minute",), evidence)
    if minute > 375:
        return _dimension("session", SESSION_CLOSED, 0.70, ("closed_market_minute",), evidence)
    return _dimension("session", SESSION_MIDDAY, 0.65, ("midday_market_minute",), evidence)


def _sanitize_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        return {"payload_present": False, "payload_type": type(snapshot).__name__}
    out: dict[str, Any] = {"payload_present": True}
    for key in _SNAPSHOT_KEYS:
        if key in snapshot:
            out[key] = _safe_json_value(snapshot.get(key))
    out["snapshot_keys"] = sorted(str(key) for key in snapshot.keys())
    return out


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dimension(
    name: str,
    value: str,
    confidence: float,
    reasons: tuple[str, ...],
    evidence: dict[str, Any],
) -> MarketStateDimension:
    return MarketStateDimension(
        name=name,
        value=value,
        confidence=_round_confidence(confidence),
        reasons=reasons,
        evidence=evidence,
    )


def _unknown_dimension(name: str, reason: str, evidence: dict[str, Any]) -> MarketStateDimension:
    return _dimension(name, UNKNOWN, 0.0, (reason,), evidence)


def _round_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


__all__ = [
    "BREADTH_BEARISH",
    "BREADTH_BULLISH",
    "BREADTH_MIXED",
    "LIQUIDITY_DEEP",
    "LIQUIDITY_NORMAL",
    "LIQUIDITY_THIN",
    "MARKET_STATE_INSUFFICIENT_EVIDENCE",
    "MARKET_STATE_SCHEMA_VERSION",
    "MARKET_STATE_SOURCE",
    "SESSION_CLOSED",
    "SESSION_CLOSING",
    "SESSION_MIDDAY",
    "SESSION_OPENING",
    "SESSION_PREOPEN",
    "TREND_DOWN",
    "TREND_SIDEWAYS",
    "TREND_UP",
    "UNKNOWN",
    "VOL_EXTREME",
    "VOL_HIGH",
    "VOL_LOW",
    "VOL_NORMAL",
    "MarketState",
    "MarketStateDimension",
    "build_market_state",
]
