from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from research.vwap_failed_discovery_hypothesis_v1.detector import (
    Bar,
    FailedDiscoveryEvent,
    compute_features,
    detect_failed_discoveries,
)
from research.vwap_failed_discovery_hypothesis_v1.evaluation import (
    ComparisonSummary,
    evaluate_event,
    classify_support,
)

IST = ZoneInfo("Asia/Kolkata")


def _bar(i: int, close: float, *, volume: float = 1000.0) -> Bar:
    ts = datetime(2026, 1, 5, 9, 15, tzinfo=IST) + timedelta(minutes=i)
    return Bar(ts=ts, open=close, high=close + 0.2, low=close - 0.2, close=close, volume=volume)


def _up_discovery_then_fail() -> tuple[Bar, ...]:
    bars = [_bar(i, 100.0 + 0.5 * i) for i in range(25)]
    bars.append(_bar(25, 107.0))
    return tuple(bars)


def test_positive_authoritative_volume_is_required() -> None:
    bars = (_bar(0, 100.0, volume=0.0),)
    with pytest.raises(ValueError, match="AUTHORITATIVE_POSITIVE_VOLUME_REQUIRED"):
        compute_features(bars)


def test_causal_vwap_uses_only_completed_history() -> None:
    bars = tuple(_bar(i, 100.0 + i) for i in range(5))
    base = compute_features(bars)
    extended = compute_features(bars + (_bar(5, 500.0),))
    assert [f.vwap for f in base] == [f.vwap for f in extended[:5]]


def test_detector_finds_upside_failed_discovery_without_strategy_rules() -> None:
    events = detect_failed_discoveries(_up_discovery_then_fail())
    assert events
    event = events[-1]
    assert event.side == "UP_FAILED"
    assert event.expected_rotation == "DOWN_TO_VWAP"
    assert 0.0 < event.failure_z <= 0.75
    assert event.frozen_discovery_extreme > event.event_close


def test_one_discovery_episode_cannot_emit_repeated_failures() -> None:
    bars = list(_up_discovery_then_fail())
    bars.extend((_bar(26, 107.0), _bar(27, 107.1), _bar(28, 106.9)))
    events = detect_failed_discoveries(tuple(bars))
    assert len(events) == 1


def test_primary_endpoint_counts_vwap_before_extreme_as_success() -> None:
    bars = [
        _bar(0, 100.0),
        _bar(1, 100.0),
        Bar(_bar(2, 100.0).ts, 100.0, 101.0, 98.5, 99.0, 1000.0),
    ]
    event = FailedDiscoveryEvent(
        ts=bars[1].ts,
        side="UP_FAILED",
        expected_rotation="DOWN_TO_VWAP",
        event_close=100.0,
        frozen_vwap=99.0,
        frozen_discovery_extreme=102.0,
        discovery_accepted_ts=bars[0].ts,
        discovery_z=1.2,
        failure_z=0.5,
        atr_pct=0.001,
        vwap_slope_atr_at_acceptance=0.2,
        efficiency_at_acceptance=0.8,
    )
    outcome = evaluate_event(tuple(bars), event)
    assert outcome.primary_success is True
    assert outcome.invalidated is False
    assert outcome.time_to_vwap_minutes == 1.0


def test_same_bar_target_and_invalidation_is_adverse_invalidation() -> None:
    bars = [
        _bar(0, 100.0),
        _bar(1, 100.0),
        Bar(_bar(2, 100.0).ts, 100.0, 102.2, 98.5, 99.0, 1000.0),
    ]
    event = FailedDiscoveryEvent(
        ts=bars[1].ts,
        side="UP_FAILED",
        expected_rotation="DOWN_TO_VWAP",
        event_close=100.0,
        frozen_vwap=99.0,
        frozen_discovery_extreme=102.0,
        discovery_accepted_ts=bars[0].ts,
        discovery_z=1.2,
        failure_z=0.5,
        atr_pct=0.001,
        vwap_slope_atr_at_acceptance=0.2,
        efficiency_at_acceptance=0.8,
    )
    outcome = evaluate_event(tuple(bars), event)
    assert outcome.primary_success is False
    assert outcome.invalidated is True


def _summary(count: int, risk_diff: float, uplift: float) -> ComparisonSummary:
    event_rate = 0.65
    control_rate = event_rate - risk_diff
    horizons = {h: 3.0 for h in (1, 3, 5, 10, 15, 30)}
    controls = {h: 3.0 - uplift for h in horizons}
    uplifts = {h: uplift for h in horizons}
    return ComparisonSummary(
        event_count=count,
        control_count=count,
        event_primary_rate=event_rate,
        control_primary_rate=control_rate,
        primary_risk_difference=risk_diff,
        event_median_directional_bps=horizons,
        control_median_directional_bps=controls,
        directional_uplift_bps=uplifts,
        event_median_mfe_bps=8.0,
        control_median_mfe_bps=5.0,
        event_median_mae_bps=4.0,
        control_median_mae_bps=4.0,
    )


def test_support_gate_is_fail_closed_on_insufficient_events() -> None:
    assert classify_support(_summary(99, 0.10, 2.0)) == "INCONCLUSIVE"


def test_supported_is_not_robust_without_oos_or_controls() -> None:
    assert classify_support(_summary(120, 0.08, 2.0)) == "SUPPORTED"


def test_robust_verdict_requires_every_later_gate() -> None:
    dev = _summary(150, 0.08, 2.0)
    oos = _summary(40, 0.06, 1.0)
    holdout = _summary(35, 0.06, 1.0)
    assert (
        classify_support(
            dev,
            oos,
            negative_controls_pass=True,
            robustness_pass=True,
            independent_oracle_pass=True,
            holdout=holdout,
        )
        == "ROBUSTLY_SUPPORTED"
    )
