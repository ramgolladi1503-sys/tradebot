from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegimeEngineConfig:
    trend_strength_threshold: float = 0.60
    volatile_atr_ratio_threshold: float = 0.018
    low_vol_atr_ratio_threshold: float = 0.006
    breadth_trend_threshold: float = 0.55
    chop_band_threshold: float = 0.25
    momentum_threshold: float = 0.004


@dataclass(frozen=True)
class RegimeSnapshot:
    symbol: str
    last_price: float
    vwap_distance_pct: float
    ema_fast_above_slow: bool
    atr_ratio: float
    realized_volatility: float
    breadth_score: float
    range_position: float
    momentum_5m_pct: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeDecision:
    symbol: str
    regime: str
    confidence: float
    tags: tuple[str, ...]
    diagnostics: dict[str, float]


class RegimeEngine:
    def __init__(self, config: RegimeEngineConfig | None = None):
        self.config = config or RegimeEngineConfig()

    def evaluate(self, snapshot: RegimeSnapshot) -> RegimeDecision:
        cfg = self.config
        score_trending = 0.0
        score_ranging = 0.0
        score_volatile = 0.0
        score_low_vol = 0.0
        tags: list[str] = []

        if snapshot.ema_fast_above_slow:
            score_trending += 0.22
            tags.append("ema_alignment")
        else:
            score_ranging += 0.08

        if abs(snapshot.vwap_distance_pct) >= cfg.momentum_threshold:
            score_trending += 0.18
            tags.append("vwap_extension")
        else:
            score_ranging += 0.12

        if snapshot.atr_ratio >= cfg.volatile_atr_ratio_threshold:
            score_volatile += 0.42
            tags.append("high_atr")
        elif snapshot.atr_ratio <= cfg.low_vol_atr_ratio_threshold:
            score_low_vol += 0.35
            tags.append("low_atr")
        else:
            score_trending += 0.10
            score_ranging += 0.10

        if snapshot.breadth_score >= cfg.breadth_trend_threshold:
            score_trending += 0.22
            tags.append("supportive_breadth")
        elif snapshot.breadth_score <= (1.0 - cfg.breadth_trend_threshold):
            score_volatile += 0.10
            score_ranging += 0.06
        else:
            score_ranging += 0.10

        if abs(snapshot.range_position - 0.5) <= cfg.chop_band_threshold:
            score_ranging += 0.22
            tags.append("mid_range")
        else:
            score_trending += 0.10

        if abs(snapshot.momentum_5m_pct) >= (cfg.momentum_threshold * 2.0):
            score_trending += 0.18
            score_volatile += 0.08
            tags.append("impulse_move")
        elif abs(snapshot.momentum_5m_pct) < cfg.momentum_threshold:
            score_low_vol += 0.10

        regime_scores = {
            "TRENDING": score_trending,
            "RANGING": score_ranging,
            "VOLATILE": score_volatile,
            "LOW_VOL": score_low_vol,
        }
        regime = max(regime_scores, key=regime_scores.get)
        score_total = sum(regime_scores.values()) or 1.0
        confidence = max(0.0, min(1.0, regime_scores[regime] / score_total))
        return RegimeDecision(
            symbol=snapshot.symbol,
            regime=regime,
            confidence=round(confidence, 4),
            tags=tuple(sorted(set(tags))),
            diagnostics={k.lower(): round(v, 4) for k, v in regime_scores.items()},
        )


def build_regime_snapshot(source: dict[str, Any]) -> RegimeSnapshot:
    return RegimeSnapshot(
        symbol=str(source.get("symbol") or "UNKNOWN"),
        last_price=float(source.get("last_price") or source.get("ltp") or 0.0),
        vwap_distance_pct=float(source.get("vwap_distance_pct") or 0.0),
        ema_fast_above_slow=bool(source.get("ema_fast_above_slow", False)),
        atr_ratio=float(source.get("atr_ratio") or 0.0),
        realized_volatility=float(source.get("realized_volatility") or 0.0),
        breadth_score=float(source.get("breadth_score") or 0.5),
        range_position=float(source.get("range_position") or 0.5),
        momentum_5m_pct=float(source.get("momentum_5m_pct") or 0.0),
        metadata=dict(source.get("metadata") or {}),
    )
