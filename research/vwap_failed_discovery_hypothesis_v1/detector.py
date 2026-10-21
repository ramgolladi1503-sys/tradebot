"""Causal, research-only detector for VWAP failed-discovery events.

This module detects the market event defined by the frozen hypothesis contract.
It intentionally contains no option logic, entries, exits, stops, targets,
position sizing, capital allocation, broker calls, or runtime wiring.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def validate(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("NON_FINITE_BAR_VALUE")
        if self.volume <= 0:
            raise ValueError("AUTHORITATIVE_POSITIVE_VOLUME_REQUIRED")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("POSITIVE_PRICE_REQUIRED")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("INVALID_OHLC_HIGH")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("INVALID_OHLC_LOW")


@dataclass(frozen=True)
class DetectorConfig:
    band_sigma: float = 1.0
    acceptance_window: int = 5
    acceptance_required_closes: int = 4
    efficiency_lookback: int = 10
    discovery_efficiency_min: float = 0.55
    slope_lookback: int = 10
    discovery_slope_atr_min: float = 0.05
    atr_lookback: int = 14
    failure_lookback_bars: int = 8
    failure_reentry_z_abs_max: float = 0.75
    minimum_history_bars: int = 20

    def validate(self) -> None:
        if self.band_sigma <= 0:
            raise ValueError("BAND_SIGMA_POSITIVE_REQUIRED")
        if not 1 <= self.acceptance_required_closes <= self.acceptance_window:
            raise ValueError("INVALID_ACCEPTANCE_COUNT")
        if min(
            self.acceptance_window,
            self.efficiency_lookback,
            self.slope_lookback,
            self.atr_lookback,
            self.failure_lookback_bars,
            self.minimum_history_bars,
        ) <= 0:
            raise ValueError("POSITIVE_LOOKBACK_REQUIRED")
        if not 0 <= self.discovery_efficiency_min <= 1:
            raise ValueError("EFFICIENCY_THRESHOLD_OUT_OF_RANGE")
        if not 0 < self.failure_reentry_z_abs_max < self.band_sigma:
            raise ValueError("REENTRY_MUST_BE_INSIDE_DISCOVERY_BAND")


DEFAULT_CONFIG = DetectorConfig()


@dataclass(frozen=True)
class Feature:
    ts: datetime
    close: float
    vwap: float
    sigma: float
    z: float
    atr: float
    atr_pct: float
    efficiency: float
    vwap_slope_atr: float


@dataclass(frozen=True)
class FailedDiscoveryEvent:
    ts: datetime
    side: str  # UP_FAILED or DOWN_FAILED
    expected_rotation: str  # DOWN_TO_VWAP or UP_TO_VWAP
    event_close: float
    frozen_vwap: float
    frozen_discovery_extreme: float
    discovery_accepted_ts: datetime
    discovery_z: float
    failure_z: float
    atr_pct: float
    vwap_slope_atr_at_acceptance: float
    efficiency_at_acceptance: float


def _validate_session(bars: Sequence[Bar]) -> None:
    if not bars:
        raise ValueError("EMPTY_SESSION")
    prior: datetime | None = None
    session_date = bars[0].ts.date()
    for bar in bars:
        bar.validate()
        if bar.ts.date() != session_date:
            raise ValueError("ONE_SESSION_PER_CALL_REQUIRED")
        if prior is not None and bar.ts <= prior:
            raise ValueError("TIMESTAMPS_MUST_BE_STRICTLY_INCREASING")
        prior = bar.ts


def _true_range(current: Bar, previous_close: float | None) -> float:
    if previous_close is None:
        return current.high - current.low
    return max(
        current.high - current.low,
        abs(current.high - previous_close),
        abs(current.low - previous_close),
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_features(
    bars: Sequence[Bar], cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[Feature, ...]:
    """Compute features using information available through each completed bar only."""
    cfg.validate()
    _validate_session(bars)

    running_weight = 0.0
    running_tp_weight = 0.0
    running_tp2_weight = 0.0
    vwaps: list[float] = []
    closes: list[float] = []
    true_ranges: list[float] = []
    out: list[Feature] = []

    for idx, bar in enumerate(bars):
        tp = (bar.high + bar.low + bar.close) / 3.0
        running_weight += bar.volume
        running_tp_weight += tp * bar.volume
        running_tp2_weight += tp * tp * bar.volume
        vwap = running_tp_weight / running_weight
        variance = max(running_tp2_weight / running_weight - vwap * vwap, 0.0)
        sigma = math.sqrt(variance)
        z = (bar.close - vwap) / sigma if sigma > 1e-12 else 0.0

        previous_close = closes[-1] if closes else None
        true_ranges.append(_true_range(bar, previous_close))
        atr = _mean(true_ranges[max(0, len(true_ranges) - cfg.atr_lookback) :])
        atr_pct = atr / bar.close if bar.close > 0 else 0.0

        closes.append(bar.close)
        er_start = max(0, idx - cfg.efficiency_lookback)
        if idx - er_start >= 1:
            numerator = abs(closes[idx] - closes[er_start])
            denominator = sum(abs(closes[k] - closes[k - 1]) for k in range(er_start + 1, idx + 1))
            efficiency = numerator / denominator if denominator > 1e-12 else 0.0
        else:
            efficiency = 0.0

        vwaps.append(vwap)
        slope_start = idx - cfg.slope_lookback
        if slope_start >= 0 and atr > 1e-12:
            vwap_slope_atr = (vwap - vwaps[slope_start]) / atr
        else:
            vwap_slope_atr = 0.0

        out.append(
            Feature(
                ts=bar.ts,
                close=bar.close,
                vwap=vwap,
                sigma=sigma,
                z=z,
                atr=atr,
                atr_pct=atr_pct,
                efficiency=efficiency,
                vwap_slope_atr=vwap_slope_atr,
            )
        )
    return tuple(out)


def _accepted_side(
    features: Sequence[Feature], idx: int, cfg: DetectorConfig
) -> str | None:
    if idx + 1 < max(cfg.minimum_history_bars, cfg.acceptance_window):
        return None
    start = idx - cfg.acceptance_window + 1
    window = features[start : idx + 1]
    up_count = sum(f.z >= cfg.band_sigma for f in window)
    down_count = sum(f.z <= -cfg.band_sigma for f in window)
    current = features[idx]

    if (
        up_count >= cfg.acceptance_required_closes
        and current.efficiency >= cfg.discovery_efficiency_min
        and current.vwap_slope_atr >= cfg.discovery_slope_atr_min
    ):
        return "UP"
    if (
        down_count >= cfg.acceptance_required_closes
        and current.efficiency >= cfg.discovery_efficiency_min
        and current.vwap_slope_atr <= -cfg.discovery_slope_atr_min
    ):
        return "DOWN"
    return None


def accepted_discoveries(
    bars: Sequence[Bar], cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[str | None, ...]:
    features = compute_features(bars, cfg)
    return tuple(_accepted_side(features, idx, cfg) for idx in range(len(features)))


def detect_failed_discoveries(
    bars: Sequence[Bar], cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[FailedDiscoveryEvent, ...]:
    """Detect at most one causal failure event per accepted discovery episode.

    Accepted discovery can persist across several consecutive bars. Those bars
    are one episode, not independent observations. A failure consumes the whole
    active episode; another failure cannot be emitted until a new accepted
    discovery occurs after that failure.
    """
    cfg.validate()
    features = compute_features(bars, cfg)
    accepted = [_accepted_side(features, idx, cfg) for idx in range(len(features))]
    events: list[FailedDiscoveryEvent] = []

    active_side: str | None = None
    active_acceptance_idx: int | None = None
    active_episode_start: int | None = None
    episode_consumed = False

    for idx in range(cfg.minimum_history_bars, len(bars)):
        current = features[idx]
        accepted_now = accepted[idx]

        if accepted_now is not None:
            # A post-failure accepted discovery starts a new episode, even if it
            # is in the same direction as the previous consumed episode.
            if active_side != accepted_now or episode_consumed or active_acceptance_idx is None:
                active_side = accepted_now
                active_episode_start = max(0, idx - cfg.acceptance_window + 1)
                episode_consumed = False
            active_acceptance_idx = idx
            continue

        if (
            active_side is None
            or active_acceptance_idx is None
            or active_episode_start is None
            or episode_consumed
        ):
            continue

        if idx - active_acceptance_idx > cfg.failure_lookback_bars:
            active_side = None
            active_acceptance_idx = None
            active_episode_start = None
            episode_consumed = False
            continue

        if current.sigma <= 1e-12:
            continue

        same_side_reentry = (
            active_side == "UP" and 0.0 < current.z <= cfg.failure_reentry_z_abs_max
        ) or (
            active_side == "DOWN" and -cfg.failure_reentry_z_abs_max <= current.z < 0.0
        )
        if not same_side_reentry:
            continue

        episode = bars[active_episode_start : idx + 1]
        extreme = (
            max(bar.high for bar in episode)
            if active_side == "UP"
            else min(bar.low for bar in episode)
        )
        accepted_feature = features[active_acceptance_idx]
        events.append(
            FailedDiscoveryEvent(
                ts=bars[idx].ts,
                side=f"{active_side}_FAILED",
                expected_rotation=(
                    "DOWN_TO_VWAP" if active_side == "UP" else "UP_TO_VWAP"
                ),
                event_close=bars[idx].close,
                frozen_vwap=current.vwap,
                frozen_discovery_extreme=extreme,
                discovery_accepted_ts=bars[active_acceptance_idx].ts,
                discovery_z=accepted_feature.z,
                failure_z=current.z,
                atr_pct=current.atr_pct,
                vwap_slope_atr_at_acceptance=accepted_feature.vwap_slope_atr,
                efficiency_at_acceptance=accepted_feature.efficiency,
            )
        )
        episode_consumed = True

    return tuple(events)


def detect_corpus(
    sessions: Iterable[Sequence[Bar]], cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[FailedDiscoveryEvent, ...]:
    events: list[FailedDiscoveryEvent] = []
    for bars in sessions:
        events.extend(detect_failed_discoveries(tuple(bars), cfg))
    events.sort(key=lambda e: e.ts)
    return tuple(events)
