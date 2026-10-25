"""
Unit tests for Sentinel Diurnal Session Classifier.
Proves all 6 Grill Me attack vectors and Hermes acceptance gates:
1. Timezone anchoring (UTC, IST, naive) to exact boundary timestamps.
2. Bar close semantics (evaluating completed bar close).
3. Anti-stampede discard invariant (SignalFate.DISCARD, zero queuing).
4. All-day trend day volatility override (KER >= 0.70 & RVOL >= 1.50).
5. Expiry & Event day adaptations.
6. Immutability (frozen dataclass) and read_only=True invariants.
"""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import pytest
from dataclasses import FrozenInstanceError

from core.market_structure.sentinel_diurnal_regime import (
    ActionGate,
    CalendarContext,
    DiurnalDecision,
    DiurnalPhase,
    MicrostructureMetrics,
    SentinelDiurnalClassifier,
    SignalFate,
    IST_TZ,
)


def test_timezone_anchoring_utc_and_naive():
    classifier = SentinelDiurnalClassifier()

    # 1. UTC timestamp: 04:30:00 UTC = 10:00:00 IST (MORNING_DRIVE)
    ts_utc = datetime(2026, 10, 26, 4, 30, 0, tzinfo=timezone.utc)
    decision = classifier.classify(bar_timestamp=ts_utc)
    assert decision.phase == DiurnalPhase.MORNING_DRIVE
    assert decision.action_gate == ActionGate.ALLOW
    assert decision.signal_fate == SignalFate.EXECUTE_ELIGIBLE
    assert decision.timestamp_ist.tzinfo == IST_TZ
    assert decision.timestamp_ist.hour == 10
    assert decision.timestamp_ist.minute == 0

    # 2. Naive timestamp: 10:00:00 (assumed IST) -> MORNING_DRIVE
    ts_naive = datetime(2026, 10, 26, 10, 0, 0)
    decision_naive = classifier.classify(bar_timestamp=ts_naive)
    assert decision_naive.phase == DiurnalPhase.MORNING_DRIVE
    assert decision_naive.action_gate == ActionGate.ALLOW
    assert decision_naive.timestamp_ist.tzinfo == IST_TZ

    # 3. Pre-open timestamp (09:05:00 IST) -> PRE_OPEN, RESTRICT
    ts_pre = datetime(2026, 10, 26, 9, 5, 0, tzinfo=IST_TZ)
    decision_pre = classifier.classify(bar_timestamp=ts_pre)
    assert decision_pre.phase == DiurnalPhase.PRE_OPEN
    assert decision_pre.action_gate == ActionGate.RESTRICT
    assert decision_pre.signal_fate == SignalFate.DISCARD

    # 4. Out of session (08:30:00 IST and 16:00:00 IST) -> CLOSED, RESTRICT
    ts_early = datetime(2026, 10, 26, 8, 30, 0, tzinfo=IST_TZ)
    decision_early = classifier.classify(bar_timestamp=ts_early)
    assert decision_early.phase == DiurnalPhase.CLOSED
    assert decision_early.action_gate == ActionGate.RESTRICT

    ts_closed = datetime(2026, 10, 26, 15, 30, 0, tzinfo=IST_TZ)
    decision_closed = classifier.classify(bar_timestamp=ts_closed)
    assert decision_closed.phase == DiurnalPhase.CLOSED
    assert decision_closed.action_gate == ActionGate.RESTRICT


def test_bar_close_evaluation():
    classifier = SentinelDiurnalClassifier()

    # Bar start at 10:55:00 IST with 300s (5m) duration closes at 11:00:00 IST -> MIDDAY_CHOP
    ts_bar_start = datetime(2026, 10, 26, 10, 55, 0, tzinfo=IST_TZ)
    decision = classifier.classify(bar_timestamp=ts_bar_start, bar_duration_seconds=300)
    assert decision.timestamp_ist.hour == 11
    assert decision.timestamp_ist.minute == 0
    assert decision.phase == DiurnalPhase.MIDDAY_CHOP
    assert decision.action_gate == ActionGate.RESTRICT

    # Bar start at 09:25:00 IST with 300s duration closes at 09:30:00 IST -> MORNING_DRIVE
    ts_open_bar = datetime(2026, 10, 26, 9, 25, 0, tzinfo=IST_TZ)
    decision_open = classifier.classify(bar_timestamp=ts_open_bar, bar_duration_seconds=300)
    assert decision_open.timestamp_ist.hour == 9
    assert decision_open.timestamp_ist.minute == 30
    assert decision_open.phase == DiurnalPhase.MORNING_DRIVE
    assert decision_open.action_gate == ActionGate.ALLOW


def test_anti_stampede_discard_invariant():
    classifier = SentinelDiurnalClassifier()

    # Midday bar (11:15 IST) -> must return SignalFate.DISCARD
    ts_midday = datetime(2026, 10, 26, 11, 15, 0, tzinfo=IST_TZ)
    decision = classifier.classify(bar_timestamp=ts_midday)
    assert decision.action_gate == ActionGate.RESTRICT
    assert decision.signal_fate == SignalFate.DISCARD
    assert decision.allowed_strategies == ()
    assert decision.suppression_reason is not None

    # Prove classifier is stateless (zero internal queuing / buffering across calls)
    assert not hasattr(classifier, "queue")
    assert not hasattr(classifier, "_pending_signals")


def test_trend_day_override():
    classifier = SentinelDiurnalClassifier()

    ts_midday = datetime(2026, 10, 26, 11, 30, 0, tzinfo=IST_TZ)

    # 1. Normal chop metrics -> RESTRICT, MIDDAY_CHOP
    normal_metrics = MicrostructureMetrics(realized_ker=0.35, relative_volume=0.90)
    decision_normal = classifier.classify(bar_timestamp=ts_midday, metrics=normal_metrics)
    assert decision_normal.phase == DiurnalPhase.MIDDAY_CHOP
    assert decision_normal.action_gate == ActionGate.RESTRICT
    assert decision_normal.signal_fate == SignalFate.DISCARD
    assert decision_normal.trend_override is False

    # 2. Strong trend day metrics (KER >= 0.70 & RVOL >= 1.50) -> ALLOW, VOLATILITY_EXPANSION
    trend_metrics = MicrostructureMetrics(realized_ker=0.75, relative_volume=1.80)
    decision_trend = classifier.classify(bar_timestamp=ts_midday, metrics=trend_metrics)
    assert decision_trend.phase == DiurnalPhase.VOLATILITY_EXPANSION
    assert decision_trend.action_gate == ActionGate.ALLOW
    assert decision_trend.signal_fate == SignalFate.EXECUTE_ELIGIBLE
    assert decision_trend.trend_override is True
    assert "MOMENTUM_BREAKOUT" in decision_trend.allowed_strategies


def test_expiry_day_afternoon_adaptation():
    classifier = SentinelDiurnalClassifier()

    ts_afternoon = datetime(2026, 10, 26, 14, 15, 0, tzinfo=IST_TZ)

    # 1. Non-expiry day context
    normal_calendar = CalendarContext(is_expiry_day=False)
    decision_normal = classifier.classify(bar_timestamp=ts_afternoon, calendar=normal_calendar)
    assert decision_normal.phase == DiurnalPhase.CLOSING_CROSS
    assert decision_normal.action_gate == ActionGate.ALLOW
    assert decision_normal.allowed_strategies == ("MOMENTUM_BREAKOUT",)
    assert "DELTA_HEDGE_UNWIND" not in decision_normal.allowed_strategies

    # 2. Expiry day context -> adds DELTA_HEDGE_UNWIND
    expiry_calendar = CalendarContext(is_expiry_day=True)
    decision_expiry = classifier.classify(bar_timestamp=ts_afternoon, calendar=expiry_calendar)
    assert decision_expiry.phase == DiurnalPhase.CLOSING_CROSS
    assert decision_expiry.action_gate == ActionGate.ALLOW
    assert "DELTA_HEDGE_UNWIND" in decision_expiry.allowed_strategies
    assert "MOMENTUM_BREAKOUT" in decision_expiry.allowed_strategies


def test_event_day_blackout_adaptation():
    classifier = SentinelDiurnalClassifier()

    ts_event = datetime(2026, 10, 26, 10, 15, 0, tzinfo=IST_TZ)
    # Event window 10:00 - 11:30 IST (e.g. RBI rate decision)
    event_calendar = CalendarContext(
        is_event_day=True,
        event_window_start=time(10, 0),
        event_window_end=time(11, 30),
    )
    decision = classifier.classify(bar_timestamp=ts_event, calendar=event_calendar)
    assert decision.action_gate == ActionGate.RESTRICT
    assert decision.signal_fate == SignalFate.DISCARD
    assert "Event window blackout active" in (decision.suppression_reason or "")


def test_immutability_and_read_only():
    classifier = SentinelDiurnalClassifier()
    ts = datetime(2026, 10, 26, 10, 0, 0, tzinfo=IST_TZ)
    decision = classifier.classify(bar_timestamp=ts)

    # Invariant: read_only=True
    assert decision.read_only is True

    # Invariant: Frozen dataclass prevents mutation
    with pytest.raises(FrozenInstanceError):
        decision.action_gate = ActionGate.RESTRICT  # type: ignore

    with pytest.raises(FrozenInstanceError):
        decision.phase = DiurnalPhase.CLOSED  # type: ignore
