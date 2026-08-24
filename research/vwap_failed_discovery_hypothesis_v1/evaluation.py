"""Outcome measurement and matched-control evaluation for the frozen hypothesis.

This is not a trading backtest. It measures whether the market phenomenon exists.
No option prices, fills, stops, targets, sizing, capital or broker/runtime code appear here.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from .detector import (
    Bar,
    DEFAULT_CONFIG,
    DetectorConfig,
    FailedDiscoveryEvent,
    Feature,
    accepted_discoveries,
    compute_features,
    detect_failed_discoveries,
)

HORIZONS = (1, 3, 5, 10, 15, 30)
PRIMARY_HORIZON_MINUTES = 30


@dataclass(frozen=True)
class Outcome:
    ts: datetime
    label: str  # EVENT or CONTROL
    expected_rotation: str
    primary_success: bool
    invalidated: bool
    time_to_vwap_minutes: float | None
    directional_returns_bps: Mapping[int, float | None]
    mfe_bps: float
    mae_bps: float
    atr_pct: float
    time_bucket: int
    volatility_bucket: int


@dataclass(frozen=True)
class ControlCandidate:
    ts: datetime
    expected_rotation: str
    close: float
    frozen_vwap: float
    frozen_extreme: float
    atr_pct: float
    z: float
    time_bucket: int
    volatility_bucket: int


@dataclass(frozen=True)
class MatchedPair:
    event: Outcome
    control: Outcome


@dataclass(frozen=True)
class ComparisonSummary:
    event_count: int
    control_count: int
    event_primary_rate: float
    control_primary_rate: float
    primary_risk_difference: float
    event_median_directional_bps: Mapping[int, float | None]
    control_median_directional_bps: Mapping[int, float | None]
    directional_uplift_bps: Mapping[int, float | None]
    event_median_mfe_bps: float
    control_median_mfe_bps: float
    event_median_mae_bps: float
    control_median_mae_bps: float


def _time_bucket(ts: datetime, bucket_minutes: int = 30) -> int:
    minute_of_day = ts.hour * 60 + ts.minute
    return minute_of_day // bucket_minutes


def _vol_bucket(atr_pct: float) -> int:
    cuts = (0.0005, 0.001, 0.002)
    for idx, cut in enumerate(cuts):
        if atr_pct < cut:
            return idx
    return len(cuts)


def _directional_bps(expected_rotation: str, start: float, end: float) -> float:
    raw = (end - start) / start * 10_000.0
    return -raw if expected_rotation == "DOWN_TO_VWAP" else raw


def _session_index(bars: Sequence[Bar], ts: datetime) -> int:
    for idx, bar in enumerate(bars):
        if bar.ts == ts:
            return idx
    raise ValueError(f"TIMESTAMP_NOT_FOUND:{ts.isoformat()}")


def _forward_close(
    bars: Sequence[Bar], start_idx: int, horizon_minutes: int
) -> float | None:
    target = bars[start_idx].ts + timedelta(minutes=horizon_minutes)
    for bar in bars[start_idx + 1 :]:
        if bar.ts == target:
            return bar.close
        if bar.ts > target:
            return None
    return None


def _path_outcome(
    bars: Sequence[Bar],
    *,
    start_idx: int,
    expected_rotation: str,
    event_close: float,
    frozen_vwap: float,
    frozen_extreme: float,
    atr_pct: float,
    label: str,
) -> Outcome:
    deadline = bars[start_idx].ts + timedelta(minutes=PRIMARY_HORIZON_MINUTES)
    future = [bar for bar in bars[start_idx + 1 :] if bar.ts <= deadline]

    primary_success = False
    invalidated = False
    time_to_vwap: float | None = None
    favorable: list[float] = [0.0]
    adverse: list[float] = [0.0]

    for bar in future:
        if expected_rotation == "DOWN_TO_VWAP":
            invalidate_hit = bar.high >= frozen_extreme
            target_hit = bar.low <= frozen_vwap
            favorable.append(max(0.0, (event_close - bar.low) / event_close * 10_000.0))
            adverse.append(max(0.0, (bar.high - event_close) / event_close * 10_000.0))
        else:
            invalidate_hit = bar.low <= frozen_extreme
            target_hit = bar.high >= frozen_vwap
            favorable.append(max(0.0, (bar.high - event_close) / event_close * 10_000.0))
            adverse.append(max(0.0, (event_close - bar.low) / event_close * 10_000.0))

        # Frozen adverse convention: if target and invalidation are both possible
        # within the same one-minute bar, count invalidation first.
        if invalidate_hit:
            invalidated = True
            break
        if target_hit:
            primary_success = True
            time_to_vwap = (bar.ts - bars[start_idx].ts).total_seconds() / 60.0
            break

    returns = {
        horizon: (
            _directional_bps(expected_rotation, event_close, end)
            if (end := _forward_close(bars, start_idx, horizon)) is not None
            else None
        )
        for horizon in HORIZONS
    }
    return Outcome(
        ts=bars[start_idx].ts,
        label=label,
        expected_rotation=expected_rotation,
        primary_success=primary_success,
        invalidated=invalidated,
        time_to_vwap_minutes=time_to_vwap,
        directional_returns_bps=returns,
        mfe_bps=max(favorable),
        mae_bps=max(adverse),
        atr_pct=atr_pct,
        time_bucket=_time_bucket(bars[start_idx].ts),
        volatility_bucket=_vol_bucket(atr_pct),
    )


def evaluate_event(bars: Sequence[Bar], event: FailedDiscoveryEvent) -> Outcome:
    idx = _session_index(bars, event.ts)
    return _path_outcome(
        bars,
        start_idx=idx,
        expected_rotation=event.expected_rotation,
        event_close=event.event_close,
        frozen_vwap=event.frozen_vwap,
        frozen_extreme=event.frozen_discovery_extreme,
        atr_pct=event.atr_pct,
        label="EVENT",
    )


def _control_extreme(
    bars: Sequence[Bar], idx: int, expected_rotation: str, lookback: int
) -> float:
    start = max(0, idx - lookback + 1)
    window = bars[start : idx + 1]
    if expected_rotation == "DOWN_TO_VWAP":
        return max(bar.high for bar in window)
    return min(bar.low for bar in window)


def control_candidates(
    bars: Sequence[Bar], cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[ControlCandidate, ...]:
    """Create same-location non-event controls.

    Controls are in the same-side re-entry z-zone as events but have no accepted
    discovery during the frozen failure lookback. This compares failed-discovery
    history against ordinary observations at a similar current VWAP location.
    """
    features = compute_features(bars, cfg)
    accepted = accepted_discoveries(bars, cfg)
    event_ts = {event.ts for event in detect_failed_discoveries(bars, cfg)}
    out: list[ControlCandidate] = []

    for idx in range(cfg.minimum_history_bars, len(bars)):
        feature: Feature = features[idx]
        if feature.ts in event_ts or feature.sigma <= 1e-12:
            continue
        if not (0.0 < abs(feature.z) <= cfg.failure_reentry_z_abs_max):
            continue
        recent_start = max(0, idx - cfg.failure_lookback_bars)
        if any(side is not None for side in accepted[recent_start:idx]):
            continue

        expected = "DOWN_TO_VWAP" if feature.z > 0 else "UP_TO_VWAP"
        out.append(
            ControlCandidate(
                ts=feature.ts,
                expected_rotation=expected,
                close=feature.close,
                frozen_vwap=feature.vwap,
                frozen_extreme=_control_extreme(
                    bars, idx, expected, cfg.failure_lookback_bars
                ),
                atr_pct=feature.atr_pct,
                z=feature.z,
                time_bucket=_time_bucket(feature.ts),
                volatility_bucket=_vol_bucket(feature.atr_pct),
            )
        )
    return tuple(out)


def evaluate_control(bars: Sequence[Bar], control: ControlCandidate) -> Outcome:
    idx = _session_index(bars, control.ts)
    return _path_outcome(
        bars,
        start_idx=idx,
        expected_rotation=control.expected_rotation,
        event_close=control.close,
        frozen_vwap=control.frozen_vwap,
        frozen_extreme=control.frozen_extreme,
        atr_pct=control.atr_pct,
        label="CONTROL",
    )


def match_controls(
    event_sessions: Mapping[datetime, Sequence[Bar]],
    control_sessions: Mapping[datetime, Sequence[Bar]],
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> tuple[MatchedPair, ...]:
    """Deterministically match events to non-event controls without reuse.

    Mapping keys are session identifiers represented by a session datetime/date
    anchor. Controls from the same calendar date as an event are excluded.
    """
    events: list[tuple[FailedDiscoveryEvent, Sequence[Bar]]] = []
    controls: list[tuple[ControlCandidate, Sequence[Bar]]] = []
    for bars in event_sessions.values():
        for event in detect_failed_discoveries(bars, cfg):
            events.append((event, bars))
    for bars in control_sessions.values():
        for control in control_candidates(bars, cfg):
            controls.append((control, bars))

    events.sort(key=lambda item: item[0].ts)
    controls.sort(key=lambda item: item[0].ts)
    used: set[datetime] = set()
    pairs: list[MatchedPair] = []

    for event, event_bars in events:
        event_bucket = _time_bucket(event.ts)
        event_vol = _vol_bucket(event.atr_pct)
        eligible = [
            (control, bars)
            for control, bars in controls
            if control.ts not in used
            and control.ts.date() != event.ts.date()
            and control.expected_rotation == event.expected_rotation
            and control.time_bucket == event_bucket
            and control.volatility_bucket == event_vol
        ]
        if not eligible:
            continue
        eligible.sort(
            key=lambda item: (
                abs(item[0].atr_pct - event.atr_pct),
                abs(abs(item[0].z) - abs(event.failure_z)),
                item[0].ts,
            )
        )
        control, control_bars = eligible[0]
        used.add(control.ts)
        pairs.append(
            MatchedPair(
                event=evaluate_event(event_bars, event),
                control=evaluate_control(control_bars, control),
            )
        )
    return tuple(pairs)


def _median(values: Sequence[float]) -> float | None:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    return statistics.median(clean) if clean else None


def summarize_pairs(pairs: Sequence[MatchedPair]) -> ComparisonSummary:
    event = [p.event for p in pairs]
    control = [p.control for p in pairs]
    event_rate = sum(o.primary_success for o in event) / len(event) if event else 0.0
    control_rate = sum(o.primary_success for o in control) / len(control) if control else 0.0

    event_medians: dict[int, float | None] = {}
    control_medians: dict[int, float | None] = {}
    uplifts: dict[int, float | None] = {}
    for horizon in HORIZONS:
        ev = _median(
            [o.directional_returns_bps[horizon] for o in event if o.directional_returns_bps[horizon] is not None]
        )
        co = _median(
            [o.directional_returns_bps[horizon] for o in control if o.directional_returns_bps[horizon] is not None]
        )
        event_medians[horizon] = ev
        control_medians[horizon] = co
        uplifts[horizon] = ev - co if ev is not None and co is not None else None

    return ComparisonSummary(
        event_count=len(event),
        control_count=len(control),
        event_primary_rate=event_rate,
        control_primary_rate=control_rate,
        primary_risk_difference=event_rate - control_rate,
        event_median_directional_bps=event_medians,
        control_median_directional_bps=control_medians,
        directional_uplift_bps=uplifts,
        event_median_mfe_bps=_median([o.mfe_bps for o in event]) or 0.0,
        control_median_mfe_bps=_median([o.mfe_bps for o in control]) or 0.0,
        event_median_mae_bps=_median([o.mae_bps for o in event]) or 0.0,
        control_median_mae_bps=_median([o.mae_bps for o in control]) or 0.0,
    )


def support_gate(summary: ComparisonSummary, *, oos: bool = False) -> bool:
    min_count = 30 if oos else 100
    if summary.event_count < min_count or summary.control_count < min_count:
        return False
    if summary.primary_risk_difference < 0.05:
        return False
    required_horizons = (5, 10, 15)
    return all(
        summary.directional_uplift_bps[h] is not None
        and summary.directional_uplift_bps[h] > 0
        for h in required_horizons
    )


def classify_support(
    dev: ComparisonSummary,
    oos: ComparisonSummary | None = None,
    *,
    negative_controls_pass: bool = False,
    robustness_pass: bool = False,
    independent_oracle_pass: bool = False,
    holdout: ComparisonSummary | None = None,
) -> str:
    """Fail-closed hypothesis verdict; never emits a strategy/live verdict."""
    if not support_gate(dev, oos=False):
        return "REJECTED" if dev.event_count >= 100 else "INCONCLUSIVE"
    if not negative_controls_pass or not robustness_pass:
        return "SUPPORTED"
    if oos is None or not support_gate(oos, oos=True):
        return "SUPPORTED"
    if not independent_oracle_pass or holdout is None or not support_gate(holdout, oos=True):
        return "SUPPORTED"
    return "ROBUSTLY_SUPPORTED"
