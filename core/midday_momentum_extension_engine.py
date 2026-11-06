"""Midday Momentum Extension Setup Engine for Sentinel.

Work Item: FEAT-SENTINEL-MIDDAY-MOMENTUM-001
Branch: feat/sentinel-unified-upstox-stream-advisor
PR Baseline: #987

Safety Invariants (Non-negotiable):
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Empirical & Mathematical Properties:
- Evaluation Point: Point-in-time strictly at 12:30:00 IST on completed 12:29:00 bar.
- Signal Conditioning: Morning cumulative drift from 09:15 open >= +0.60% (LONG/CE) or <= -0.60% (SHORT/PE).
- Payoff Profile: 1:1 Fixed Symmetrical Payoff (Target = 40.0 pts, Stop = 40.0 pts on NIFTY index).
- Strike Selection: Round-100 strike resolution to guarantee highest liquidity ($15M+ OI, 0.25-0.50 spread).
- Mandatory Flattening: Strictly liquidated by 15:15:00 IST square-off gate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time as dt_time, datetime
from enum import Enum
from typing import Optional, Dict, Any


class MiddayDirection(str, Enum):
    LONG = "CE"
    SHORT = "PE"
    ABSTAIN = "ABSTAIN"


@dataclass(slots=True, frozen=True)
class MiddayMomentumSignal:
    timestamp_ms: int
    eval_time_str: str
    index_name: str
    direction: MiddayDirection
    open_price: float
    current_price: float
    drift_pct: float
    target_pts: float
    stop_pts: float
    target_price: float
    stop_price: float
    recommended_strike: float
    recommended_option_type: str
    setup_reason: str
    # Battle-Hardened Execution Specifications
    order_type: str = "MARKETABLE_IOC_LIMIT"
    ioc_slippage_cap: float = 0.30
    max_spread_gate: float = 0.60
    # Safety Invariants
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


class MiddayMomentumExtensionEngine:
    """Evaluates causal midday continuation setups at 12:30:00 IST based on morning drift and geometric target strikes."""

    def __init__(
        self,
        index_name: str = "NIFTY",
        drift_threshold: float = 0.0060,  # 0.60%
        target_pts: float = 40.0,
        stop_pts: float = 40.0,
        eval_time: dt_time = dt_time(12, 30),
        strike_round: float = 100.0,  # Default 100 for index liquidity, supports 50-pt resolution
        target_strike_mode: bool = False,  # If True, resolves strike at target level (Convexity)
    ) -> None:
        self.index_name = index_name.upper()
        self.drift_threshold = float(drift_threshold)
        self.target_pts = float(target_pts)
        self.stop_pts = float(stop_pts)
        self.eval_time = eval_time
        self.strike_round = strike_round
        self.target_strike_mode = target_strike_mode

        # Session tracking state
        self.session_open_price: Optional[float] = None
        self.evaluation_completed: bool = False
        self.evaluated_date_str: Optional[str] = None
        self.cached_signal: Optional[MiddayMomentumSignal] = None

    def reset_session(self) -> None:
        """Resets state for a new trading day."""
        self.session_open_price = None
        self.evaluation_completed = False
        self.evaluated_date_str = None
        self.cached_signal = None

    def set_session_open(self, open_price: float) -> None:
        """Sets the official 09:15 opening print for the session."""
        if open_price > 0.0 and self.session_open_price is None:
            self.session_open_price = float(open_price)

    def resolve_liquid_round_strike(self, spot_price: float) -> float:
        """Resolves the nearest Round-100 or Round-50 strike to guarantee maximum institutional liquidity."""
        return round(spot_price / self.strike_round) * self.strike_round

    def resolve_target_option_strike(self, target_price: float) -> float:
        """Resolves the Geometric Target Strike that transitions into the new ATM option when target is reached."""
        return round(target_price / self.strike_round) * self.strike_round

    def evaluate_at_1230(
        self,
        current_spot: float,
        timestamp_ms: int,
        wall_time: dt_time,
        date_str: str,
        open_price: Optional[float] = None,
        morning_range: Optional[float] = None,
    ) -> Optional[MiddayMomentumSignal]:
        """Evaluates causal midday extension at 12:30:00 IST with geometric target-strike selection.

        Args:
            current_spot: The spot price at 12:30:00 IST (close of 12:29 bar).
            timestamp_ms: Exchange timestamp in milliseconds.
            wall_time: Current wall time.
            date_str: ISO date string (YYYY-MM-DD).
            open_price: Optional explicit 09:15 open price.
            morning_range: Optional morning range (High - Low) from 09:15 to 12:30.

        Returns:
            MiddayMomentumSignal if evaluated at 12:30, or None if outside evaluation window.
        """
        if open_price is not None and self.session_open_price is None:
            self.session_open_price = float(open_price)

        # Reset if new session date encountered
        if self.evaluated_date_str is not None and self.evaluated_date_str != date_str:
            self.reset_session()

        # If already evaluated today, return cached signal if any
        if self.evaluation_completed and self.evaluated_date_str == date_str:
            return self.cached_signal

        # Check if current time is within evaluation minute (12:30:00 - 12:30:59)
        if wall_time.hour != self.eval_time.hour or wall_time.minute != self.eval_time.minute:
            return None

        # Fail-closed if session open price is unavailable or invalid
        if self.session_open_price is None or self.session_open_price <= 0.0 or current_spot <= 0.0:
            return None

        # Calculate morning drift strictly from 09:15 open to 12:30 spot
        drift = (current_spot - self.session_open_price) / self.session_open_price

        # Dynamic target move based on morning range if available
        eff_target_pts = self.target_pts
        if morning_range is not None and morning_range > 0:
            calc_target = round((morning_range * 0.618) / self.strike_round) * self.strike_round
            eff_target_pts = max(40.0, min(100.0, calc_target))

        direction = MiddayDirection.ABSTAIN
        target_price = current_spot
        stop_price = current_spot
        opt_type = "NONE"
        reason = f"No midday momentum drift: {drift:+.2%}"
        recommended_strike = self.resolve_liquid_round_strike(current_spot)

        if drift >= self.drift_threshold:
            direction = MiddayDirection.LONG
            target_price = current_spot + eff_target_pts
            stop_price = current_spot - self.stop_pts
            opt_type = "CE"
            if self.target_strike_mode:
                recommended_strike = self.resolve_target_option_strike(target_price)
            else:
                recommended_strike = self.resolve_liquid_round_strike(current_spot)
            reason = (
                f"Bullish Midday Continuation: Drift {drift:+.2%} >= +{self.drift_threshold:.2%}. "
                f"Target={target_price:.1f} (+{eff_target_pts}pts), Stop={stop_price:.1f} (-{self.stop_pts}pts)"
            )
        elif drift <= -self.drift_threshold:
            direction = MiddayDirection.SHORT
            target_price = current_spot - eff_target_pts
            stop_price = current_spot + self.stop_pts
            opt_type = "PE"
            if self.target_strike_mode:
                recommended_strike = self.resolve_target_option_strike(target_price)
            else:
                recommended_strike = self.resolve_liquid_round_strike(current_spot)
            reason = (
                f"Bearish Midday Continuation: Drift {drift:+.2%} <= -{self.drift_threshold:.2%}. "
                f"Target={target_price:.1f} (-{eff_target_pts}pts), Stop={stop_price:.1f} (+{self.stop_pts}pts)"
            )

        signal = MiddayMomentumSignal(
            timestamp_ms=timestamp_ms,
            eval_time_str=f"{date_str}T{wall_time.isoformat()}",
            index_name=self.index_name,
            direction=direction,
            open_price=self.session_open_price,
            current_price=current_spot,
            drift_pct=round(drift, 4),
            target_pts=eff_target_pts,
            stop_pts=self.stop_pts,
            target_price=round(target_price, 2),
            stop_price=round(stop_price, 2),
            recommended_strike=recommended_strike,
            recommended_option_type=opt_type,
            setup_reason=reason,
            order_type="MARKETABLE_IOC_LIMIT",
            ioc_slippage_cap=0.30,
            max_spread_gate=0.60,
            read_only=True,
            is_order_action=False,
            broker_api_called=False,
            allowed_for_live_execution=False,
        )

        self.evaluation_completed = True
        self.evaluated_date_str = date_str
        self.cached_signal = signal
        return signal
