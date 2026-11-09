"""
Sentinel Diurnal Session Classifier.
Part of Sentinel Market Structure Engine.

Provides deterministic, causal market regime phase classification across the
Indian equities / index derivatives intraday trading session (NSE: 09:15 - 15:30 IST).
Evaluates exchange bar close timestamps against strictly defined diurnal phases,
honoring all-day trend overrides, event-window chop restrictions, and expiry adaptations.
Zero delayed queuing; anti-stampede discard invariant enforced.

Read-only, immutable, zero broker wiring.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum, unique
from zoneinfo import ZoneInfo

IST_TZ = ZoneInfo("Asia/Kolkata")


@unique
class DiurnalPhase(str, Enum):
    PRE_OPEN = "PRE_OPEN"                                 # 09:00 - 09:15 IST
    DISCOVERY_OPEN = "DISCOVERY_OPEN"                     # 09:15 - 09:30 IST (Initial auction / high variance)
    MORNING_DRIVE = "MORNING_DRIVE"                       # 09:30 - 11:00 IST (Primary institutional trend)
    MIDDAY_CHOP = "MIDDAY_CHOP"                           # 11:00 - 13:15 IST (Low volume mean-reversion / decay)
    EUROPEAN_OPEN_TRANSITION = "EUROPEAN_OPEN_TRANSITION" # 13:15 - 14:00 IST (Macro liquidity shift)
    CLOSING_CROSS = "CLOSING_CROSS"                       # 14:00 - 15:15 IST (Closing momentum / expiry unwind)
    POST_CLOSE_CURFEW = "POST_CLOSE_CURFEW"               # 15:15 - 15:30 IST (Intraday squaring only, no new entries)
    CLOSED = "CLOSED"                                     # < 09:15 or >= 15:30 IST
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"         # Trend-day override state


@unique
class ActionGate(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"


@unique
class SignalFate(str, Enum):
    EXECUTE_ELIGIBLE = "EXECUTE_ELIGIBLE"
    DISCARD = "DISCARD"


@dataclass(frozen=True)
class CalendarContext:
    is_expiry_day: bool = False
    is_event_day: bool = False
    event_window_start: time | None = None
    event_window_end: time | None = None


@dataclass(frozen=True)
class MicrostructureMetrics:
    realized_ker: float        # Kaufman Efficiency Ratio [0.0, 1.0]
    relative_volume: float     # RVOL relative to historical session benchmark
    atr_ratio: float = 1.0     # Current ATR vs baseline session ATR


@dataclass(frozen=True)
class DiurnalDecision:
    timestamp_ist: datetime
    phase: DiurnalPhase
    action_gate: ActionGate
    signal_fate: SignalFate
    trend_override: bool
    allowed_strategies: tuple[str, ...]
    suppression_reason: str | None
    read_only: bool = True


class SentinelDiurnalClassifier:
    """
    Deterministic Diurnal Session Classifier for Indian Equities / Derivatives.
    Stateless, immutable, read-only.
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def _normalize_timestamp(bar_timestamp: datetime, bar_duration_seconds: int = 0) -> datetime:
        """
        Anchors timestamp to Asia/Kolkata and computes completed bar close timestamp.
        """
        if bar_timestamp.tzinfo is None:
            # Naive timestamp assumes Asia/Kolkata exchange feed
            ts_ist = bar_timestamp.replace(tzinfo=IST_TZ)
        else:
            ts_ist = bar_timestamp.astimezone(IST_TZ)

        if bar_duration_seconds > 0:
            ts_ist = ts_ist + timedelta(seconds=bar_duration_seconds)

        return ts_ist

    def classify(
        self,
        bar_timestamp: datetime,
        bar_duration_seconds: int = 0,
        metrics: MicrostructureMetrics | None = None,
        calendar: CalendarContext | None = None,
    ) -> DiurnalDecision:
        """
        Classifies bar close into a diurnal regime decision.
        """
        if calendar is None:
            calendar = CalendarContext()

        eval_ts = self._normalize_timestamp(bar_timestamp, bar_duration_seconds)
        t = eval_ts.time()

        # Session boundaries
        t_0900 = time(9, 0)
        t_0915 = time(9, 15)
        t_0930 = time(9, 30)
        t_1100 = time(11, 0)
        t_1315 = time(13, 15)
        t_1400 = time(14, 0)
        t_1515 = time(15, 15)
        t_1530 = time(15, 30)

        # 1. Closed checks
        if t < t_0915:
            phase = DiurnalPhase.PRE_OPEN if t >= t_0900 else DiurnalPhase.CLOSED
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=phase,
                action_gate=ActionGate.RESTRICT,
                signal_fate=SignalFate.DISCARD,
                trend_override=False,
                allowed_strategies=(),
                suppression_reason="Market session closed or pre-open auction phase",
                read_only=True,
            )

        if t >= t_1530:
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.CLOSED,
                action_gate=ActionGate.RESTRICT,
                signal_fate=SignalFate.DISCARD,
                trend_override=False,
                allowed_strategies=(),
                suppression_reason="Market session post-close",
                read_only=True,
            )

        # 2. Event window check (forces RESTRICT)
        if (
            calendar.is_event_day
            and calendar.event_window_start is not None
            and calendar.event_window_end is not None
            and calendar.event_window_start <= t < calendar.event_window_end
        ):
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.MIDDAY_CHOP if t_1100 <= t < t_1315 else DiurnalPhase.DISCOVERY_OPEN,
                action_gate=ActionGate.RESTRICT,
                signal_fate=SignalFate.DISCARD,
                trend_override=False,
                allowed_strategies=(),
                suppression_reason=f"Event window blackout active ({calendar.event_window_start}-{calendar.event_window_end})",
                read_only=True,
            )

        # 3. Determine Phase by Bar Close Time
        if t_0915 <= t < t_0930:
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.DISCOVERY_OPEN,
                action_gate=ActionGate.RESTRICT,
                signal_fate=SignalFate.DISCARD,
                trend_override=False,
                allowed_strategies=(),
                suppression_reason="Opening price discovery window; initial auction volatility",
                read_only=True,
            )

        if t_0930 <= t < t_1100:
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.MORNING_DRIVE,
                action_gate=ActionGate.ALLOW,
                signal_fate=SignalFate.EXECUTE_ELIGIBLE,
                trend_override=False,
                allowed_strategies=("TREND_CONTINUATION", "MOMENTUM_BREAKOUT"),
                suppression_reason=None,
                read_only=True,
            )

        if t_1100 <= t < t_1315:
            # Check Trend-Day / Volatility Expansion Override
            if metrics is not None and metrics.realized_ker >= 0.70 and metrics.relative_volume >= 1.50:
                return DiurnalDecision(
                    timestamp_ist=eval_ts,
                    phase=DiurnalPhase.VOLATILITY_EXPANSION,
                    action_gate=ActionGate.ALLOW,
                    signal_fate=SignalFate.EXECUTE_ELIGIBLE,
                    trend_override=True,
                    allowed_strategies=("TREND_CONTINUATION", "MOMENTUM_BREAKOUT"),
                    suppression_reason=None,
                    read_only=True,
                )
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.MIDDAY_CHOP,
                action_gate=ActionGate.RESTRICT,
                signal_fate=SignalFate.DISCARD,
                trend_override=False,
                allowed_strategies=(),
                suppression_reason="Midday chop regime; low directional volume and high decay risk",
                read_only=True,
            )

        if t_1315 <= t < t_1400:
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.EUROPEAN_OPEN_TRANSITION,
                action_gate=ActionGate.ALLOW,
                signal_fate=SignalFate.EXECUTE_ELIGIBLE,
                trend_override=False,
                allowed_strategies=("CROSS_MARKET_TREND", "MOMENTUM_BREAKOUT"),
                suppression_reason=None,
                read_only=True,
            )

        if t_1400 <= t < t_1515:
            # Check Expiry Day Adaptation
            if calendar.is_expiry_day:
                allowed = ("MOMENTUM_BREAKOUT", "DELTA_HEDGE_UNWIND")
            else:
                allowed = ("MOMENTUM_BREAKOUT",)
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.CLOSING_CROSS,
                action_gate=ActionGate.ALLOW,
                signal_fate=SignalFate.EXECUTE_ELIGIBLE,
                trend_override=False,
                allowed_strategies=allowed,
                suppression_reason=None,
                read_only=True,
            )

        if t_1515 <= t < t_1530:
            return DiurnalDecision(
                timestamp_ist=eval_ts,
                phase=DiurnalPhase.POST_CLOSE_CURFEW,
                action_gate=ActionGate.RESTRICT,
                signal_fate=SignalFate.DISCARD,
                trend_override=False,
                allowed_strategies=("SQUARE_OFF_ONLY",),
                suppression_reason="Post-close curfew; intraday square-off only, no new positions",
                read_only=True,
            )

        # Fallback closed
        return DiurnalDecision(
            timestamp_ist=eval_ts,
            phase=DiurnalPhase.CLOSED,
            action_gate=ActionGate.RESTRICT,
            signal_fate=SignalFate.DISCARD,
            trend_override=False,
            allowed_strategies=(),
            suppression_reason="Out of trading hours",
            read_only=True,
        )
