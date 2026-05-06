"""
Pro Strategy Engine.

This layer is intentionally separate from the legacy ensemble. It produces
orthogonal, regime-aware alpha signals that can be converted into decision
engine candidates by pro_decision_adapter.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class ProSignal:
    name: str
    direction: str
    score: float
    confidence: float
    reason: str
    family: str = "unknown"
    regime_tags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


class StrategyBase:
    family = "unknown"
    regimes: set[str] = {"TREND", "RANGE", "VOLATILE", "EVENT", "NEUTRAL", "EXPIRY"}

    def generate(self, market_data: dict) -> Optional[ProSignal]:
        raise NotImplementedError


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _norm_regime(value: Any) -> str:
    text = str(value or "NEUTRAL").strip().upper()
    if text in {"", "UNKNOWN"}:
        return "NEUTRAL"
    if text in {"PANIC", "NEWS"}:
        return "EVENT"
    if text in {"TRENDING", "TREND_STRONG", "VOLATILE_TREND"}:
        return "TREND"
    if text in {"MEAN_REVERT", "MEANREVERT", "SIDEWAYS"}:
        return "RANGE"
    if text in {"RANGE_VOLATILE"}:
        return "VOLATILE"
    return text


def _direction_from_delta(delta: float) -> str:
    return "BUY_CALL" if float(delta) > 0 else "BUY_PUT"


def _quote_age_sec(market_data: dict[str, Any]) -> float:
    return _safe_float(market_data.get("quote_age_sec"), 999.0)


def _spread_pct(market_data: dict[str, Any]) -> float:
    return _safe_float(market_data.get("spread_pct"), 999.0)


def _fresh_and_tight(market_data: dict[str, Any], *, max_age_sec: float = 6.0, max_spread_pct: float = 0.02) -> bool:
    return _quote_age_sec(market_data) <= max_age_sec and _spread_pct(market_data) <= max_spread_pct


def _make_signal(name: str, direction: str, edge: float, confidence: float, reason: str, *, family: str, regime: str, evidence: dict[str, Any]) -> ProSignal:
    return ProSignal(
        name=name,
        direction=direction,
        score=round(_clamp01(edge), 4),
        confidence=round(_clamp01(confidence), 4),
        reason=reason,
        family=family,
        regime_tags=[regime],
        evidence=evidence,
    )


class VolatilityExpansionStrategy(StrategyBase):
    family = "volatility_expansion"
    regimes = {"TREND", "VOLATILE", "EVENT", "EXPIRY"}

    def generate(self, market_data):
        atr = _safe_float(market_data.get("atr"))
        ltp_change = _safe_float(market_data.get("ltp_change_window", market_data.get("ltp_change")))
        vol_z = _safe_float(market_data.get("vol_z"))
        if atr <= 0 or not _fresh_and_tight(market_data, max_age_sec=6.0, max_spread_pct=0.02):
            return None
        move_atr = abs(ltp_change) / max(atr, 1e-6)
        if move_atr < 0.75 and vol_z < 1.0:
            return None
        edge = 0.54 + min(0.24, move_atr * 0.14) + min(0.10, max(vol_z, 0.0) * 0.04)
        confidence = 0.52 + min(0.26, move_atr * 0.16) + min(0.10, max(vol_z, 0.0) * 0.05)
        return _make_signal(
            "vol_expansion",
            _direction_from_delta(ltp_change),
            edge,
            confidence,
            "ATR/volume expansion directional move",
            family=self.family,
            regime=_norm_regime(market_data.get("regime")),
            evidence={"move_atr": round(move_atr, 4), "vol_z": vol_z},
        )


class LiquidityImbalanceStrategy(StrategyBase):
    family = "order_flow"
    regimes = {"TREND", "VOLATILE", "EVENT", "EXPIRY", "NEUTRAL"}

    def generate(self, market_data):
        bid_qty = _safe_float(market_data.get("bid_qty"))
        ask_qty = _safe_float(market_data.get("ask_qty"))
        spread_pct = _spread_pct(market_data)
        if bid_qty <= 0 or ask_qty <= 0:
            return None
        imbalance = (bid_qty - ask_qty) / max(bid_qty + ask_qty, 1.0)
        if abs(imbalance) < 0.35:
            return None
        if not _fresh_and_tight(market_data, max_age_sec=6.0, max_spread_pct=0.02):
            return None
        direction = "BUY_CALL" if imbalance > 0 else "BUY_PUT"
        strength = abs(imbalance)
        edge = 0.53 + min(0.26, strength * 0.45)
        confidence = 0.50 + min(0.30, strength * 0.50)
        return _make_signal(
            "liquidity_imbalance",
            direction,
            edge,
            confidence,
            "Depth imbalance with acceptable spread",
            family=self.family,
            regime=_norm_regime(market_data.get("regime")),
            evidence={"imbalance": round(imbalance, 4), "spread_pct": spread_pct},
        )


class VWAPMeanReversionStrategy(StrategyBase):
    family = "mean_reversion"
    regimes = {"RANGE", "NEUTRAL"}

    def generate(self, market_data):
        ltp = _safe_float(market_data.get("ltp"))
        vwap = _safe_float(market_data.get("vwap"))
        rsi = _safe_float(market_data.get("rsi", market_data.get("rsi_mom")))
        if ltp <= 0 or vwap <= 0 or not _fresh_and_tight(market_data, max_age_sec=6.0, max_spread_pct=0.02):
            return None
        dev = (ltp - vwap) / vwap
        if abs(dev) < 0.0045:
            return None
        if dev > 0 and rsi < 0.35:
            return None
        if dev < 0 and rsi > -0.35:
            return None
        direction = "BUY_PUT" if dev > 0 else "BUY_CALL"
        edge = 0.51 + min(0.24, abs(dev) * 42)
        confidence = 0.49 + min(0.22, abs(dev) * 36)
        return _make_signal(
            "vwap_mean_reversion",
            direction,
            edge,
            confidence,
            "VWAP extension mean reversion",
            family=self.family,
            regime=_norm_regime(market_data.get("regime")),
            evidence={"vwap_dev": round(dev, 5), "rsi_mom": rsi},
        )


class OptionsFlowStrategy(StrategyBase):
    family = "options_flow"
    regimes = {"TREND", "VOLATILE", "EVENT", "EXPIRY", "NEUTRAL"}

    def generate(self, market_data):
        call_oi_delta = _safe_float(market_data.get("call_oi_delta"))
        put_oi_delta = _safe_float(market_data.get("put_oi_delta"))
        iv_change = _safe_float(market_data.get("iv_change"))
        price_delta = _safe_float(market_data.get("ltp_change_window", market_data.get("ltp_change")))
        if not _fresh_and_tight(market_data, max_age_sec=6.0, max_spread_pct=0.02):
            return None
        oi_pressure = put_oi_delta - call_oi_delta
        if abs(oi_pressure) < 1 and abs(iv_change) < 0.03:
            return None
        aligned = (oi_pressure > 0 and price_delta > 0) or (oi_pressure < 0 and price_delta < 0)
        if not aligned:
            return None
        direction = "BUY_CALL" if price_delta > 0 else "BUY_PUT"
        strength = min(1.0, abs(oi_pressure) / max(abs(call_oi_delta) + abs(put_oi_delta), 1.0))
        edge = 0.53 + min(0.22, strength * 0.30) + min(0.08, abs(iv_change) * 1.5)
        confidence = 0.50 + min(0.22, strength * 0.30) + min(0.08, abs(iv_change) * 1.2)
        return _make_signal(
            "options_flow_alignment",
            direction,
            edge,
            confidence,
            "OI/IV pressure aligned with price move",
            family=self.family,
            regime=_norm_regime(market_data.get("regime")),
            evidence={"oi_pressure": oi_pressure, "iv_change": iv_change, "price_delta": price_delta},
        )


class TimeWindowStrategy(StrategyBase):
    family = "time_window"
    regimes = {"TREND", "VOLATILE", "EVENT", "EXPIRY", "NEUTRAL"}

    def generate(self, market_data):
        hour = int(_safe_float(market_data.get("hour"), -1))
        minute = int(_safe_float(market_data.get("minute"), 0))
        ltp_change = _safe_float(market_data.get("ltp_change_window", market_data.get("ltp_change")))
        if hour < 0 or abs(ltp_change) <= 0:
            return None
        mins = (hour * 60) + minute
        is_open = (9 * 60 + 20) <= mins <= (10 * 60)
        is_close = (14 * 60 + 15) <= mins <= (15 * 60 + 10)
        if not (is_open or is_close):
            return None
        edge = 0.44 if is_open else 0.47
        confidence = 0.40 if is_open else 0.43
        return _make_signal(
            "time_window_momentum",
            _direction_from_delta(ltp_change),
            edge,
            confidence,
            "Opening/closing momentum window",
            family=self.family,
            regime=_norm_regime(market_data.get("regime")),
            evidence={"hour": hour, "minute": minute, "ltp_change": ltp_change},
        )


class ProSignalAggregator:
    def aggregate(self, signals: Iterable[ProSignal]) -> list[ProSignal]:
        signals = list(signals or [])
        if not signals:
            return []
        primary = [s for s in signals if s.family != "time_window"]
        boosters = [s for s in signals if s.family == "time_window"]
        if not primary:
            return []

        call_strength = sum(s.score * s.confidence for s in primary if s.direction == "BUY_CALL")
        put_strength = sum(s.score * s.confidence for s in primary if s.direction == "BUY_PUT")
        if call_strength and put_strength:
            stronger = "BUY_CALL" if call_strength > put_strength else "BUY_PUT"
            weaker_strength = min(call_strength, put_strength)
            stronger_strength = max(call_strength, put_strength)
            conflict_ratio = weaker_strength / max(stronger_strength, 1e-6)
            if conflict_ratio >= 0.55:
                return []
            kept: list[ProSignal] = []
            for sig in primary:
                if sig.direction == stronger:
                    sig.evidence = {**sig.evidence, "conflict_ratio": round(conflict_ratio, 4)}
                    kept.append(sig)
            primary = kept

        if boosters and primary:
            booster = max(boosters, key=lambda s: s.score * s.confidence)
            for sig in primary:
                if sig.direction == booster.direction:
                    sig.evidence = {
                        **sig.evidence,
                        "time_window_boost": round(booster.score * booster.confidence, 4),
                    }

        kept = [sig for sig in primary if sig.score >= 0.64 and sig.confidence >= 0.60]
        if not kept:
            return []
        ranked = sorted(kept, key=lambda s: (s.score * s.confidence, s.score, s.confidence, s.name), reverse=True)
        top = ranked[0]
        top_strength = top.score * top.confidence
        next_strength = ranked[1].score * ranked[1].confidence if len(ranked) > 1 else 0.0
        if len(ranked) > 1 and (top_strength - next_strength) < 0.04:
            return []
        return [top]


class ProStrategyEngine:
    def __init__(self):
        self.strategies: List[StrategyBase] = [
            VolatilityExpansionStrategy(),
            LiquidityImbalanceStrategy(),
            VWAPMeanReversionStrategy(),
            OptionsFlowStrategy(),
            TimeWindowStrategy(),
        ]
        self.aggregator = ProSignalAggregator()
        self.last_errors: list[str] = []

    def run(self, market_data: dict, *, error_sink: list[str] | None = None) -> List[ProSignal]:
        regime = _norm_regime(market_data.get("regime"))
        signals: list[ProSignal] = []
        self.last_errors = []
        for strat in self.strategies:
            if regime not in getattr(strat, "regimes", {regime}) and "NEUTRAL" not in getattr(strat, "regimes", set()):
                continue
            try:
                sig = strat.generate(market_data)
                if sig:
                    signals.append(sig)
            except Exception as exc:
                err = f"strategy_failed:{getattr(strat, 'family', 'unknown')}:{type(exc).__name__}:{exc}"
                self.last_errors.append(err)
                if error_sink is not None:
                    error_sink.append(err)
                logger.exception("pro_strategy_engine_strategy_failed family=%s err=%s", getattr(strat, "family", "unknown"), exc)
                continue
        return self.aggregator.aggregate(signals)
