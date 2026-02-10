from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from config import config as cfg
from core.market_data import get_current_regime


REGIME_TREND = "TREND"
REGIME_RANGE = "RANGE"
REGIME_EVENT = "EVENT"
REGIME_NEUTRAL = "NEUTRAL"


def normalize_regime(value: Any) -> str:
    raw = str(value or "").upper().strip()
    if raw in {REGIME_TREND, REGIME_RANGE, REGIME_EVENT, REGIME_NEUTRAL}:
        return raw
    if raw in {"RANGE_VOLATILE"}:
        return REGIME_RANGE
    if raw in {"PANIC"}:
        return REGIME_EVENT
    return REGIME_NEUTRAL


@dataclass(frozen=True)
class RegimeRuleThresholds:
    trend_vwap_slope_abs_min: float
    trend_atr_pct_min: float
    event_atr_pct_min: float
    event_gap_pct_abs_min: float
    range_vwap_slope_abs_max: float
    range_atr_pct_max: float
    range_gap_pct_abs_max: float


class RegimeClassifier:
    """
    Deterministic baseline classifier used for routing and risk gating.
    Inputs are feature-like fields from live market snapshots.
    """

    def __init__(self, thresholds: RegimeRuleThresholds | None = None):
        self.thresholds = thresholds or RegimeRuleThresholds(
            trend_vwap_slope_abs_min=float(getattr(cfg, "REGIME_RULE_TREND_VWAP_SLOPE_ABS_MIN", 0.0015)),
            trend_atr_pct_min=float(getattr(cfg, "REGIME_RULE_TREND_ATR_PCT_MIN", 0.0010)),
            event_atr_pct_min=float(getattr(cfg, "REGIME_RULE_EVENT_ATR_PCT_MIN", 0.0060)),
            event_gap_pct_abs_min=float(getattr(cfg, "REGIME_RULE_EVENT_GAP_PCT_ABS_MIN", 0.0040)),
            range_vwap_slope_abs_max=float(getattr(cfg, "REGIME_RULE_RANGE_VWAP_SLOPE_ABS_MAX", 0.0008)),
            range_atr_pct_max=float(getattr(cfg, "REGIME_RULE_RANGE_ATR_PCT_MAX", 0.0035)),
            range_gap_pct_abs_max=float(getattr(cfg, "REGIME_RULE_RANGE_GAP_PCT_ABS_MAX", 0.0020)),
        )

    def classify(self, features: Mapping[str, Any]) -> str:
        atr_pct = _as_float(features.get("atr_pct"), 0.0)
        vwap_slope = _as_float(features.get("vwap_slope"), 0.0)
        gap_pct = _as_float(features.get("gap_pct"), 0.0)
        event_flag = bool(
            features.get("event_flag")
            or features.get("news_event_flag")
            or features.get("event_mode")
            or (features.get("shock_score") or 0.0) >= float(getattr(cfg, "NEWS_SHOCK_EVENT_THRESHOLD", 0.4))
        )
        return self.classify_values(
            atr_pct=atr_pct,
            vwap_slope=vwap_slope,
            gap_pct=gap_pct,
            event_flag=event_flag,
        )

    def classify_values(self, atr_pct: float, vwap_slope: float, gap_pct: float, event_flag: bool) -> str:
        if event_flag:
            return REGIME_EVENT
        if abs(gap_pct) >= self.thresholds.event_gap_pct_abs_min:
            return REGIME_EVENT
        if atr_pct >= self.thresholds.event_atr_pct_min:
            return REGIME_EVENT
        if abs(vwap_slope) >= self.thresholds.trend_vwap_slope_abs_min and atr_pct >= self.thresholds.trend_atr_pct_min:
            return REGIME_TREND
        if (
            abs(vwap_slope) <= self.thresholds.range_vwap_slope_abs_max
            and atr_pct <= self.thresholds.range_atr_pct_max
            and abs(gap_pct) <= self.thresholds.range_gap_pct_abs_max
        ):
            return REGIME_RANGE
        return REGIME_NEUTRAL


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# LEGACY WRAPPER; DO NOT ADD STRATEGY LOGIC.
def adx(df, period=14):
    return None


# LEGACY WRAPPER; DO NOT ADD STRATEGY LOGIC.
def trend_slope(df, window=20):
    return 0.0


# LEGACY WRAPPER; DO NOT ADD STRATEGY LOGIC.
def detect_regime(df=None):
    snap = get_current_regime("NIFTY")
    return {
        "regime": snap.get("primary_regime", "NEUTRAL"),
        **snap,
    }
