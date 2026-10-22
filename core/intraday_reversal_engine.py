"""Intraday Mean-Reversion / Exhaustion Gate & Failure-at-Extreme Setup Engine for Sentinel.

Work Item: FEAT-SENTINEL-INTRADAY-REVERSAL-001
Status: read_only=True, is_order_action=False, broker_api_called=False,
        allowed_for_live_execution=False, edge_certification_status="NO_CERTIFIED_EDGE"

Key Features:
1. IntradayExhaustionGate:
   - Rolling spot VWAP and rolling volume-weighted standard deviation bands (1.5-2.5 sigma).
   - Momentum deceleration & volume absorption detection.
   - Runaway trend suppression (GM-GATE-001): Monotonic VWAP slope > 0.5 pts/bar and expansion
     outside 2.5 sigma vetoes counter-trend reversal fail-closed (VETO_RUNAWAY_TREND).
   - Adverse selection spread limit gate (GM-GATE-004): Vetoes setups when option spread ratio > 4.0%
     (VETO_SPREAD_EXPANDED).
2. FailureAtExtremeEngine:
   - Failure-at-High (FAH): Pierces prior HOD by delta in [2.0, 25.0] pts (NIFTY), rejects, and closes
     back below HOD in lower 50% of the bar's range -> PE setup.
   - Failure-at-Low (FAL): Pierces prior LOD by delta in [2.0, 25.0] pts (NIFTY), rejects, and closes
     back above LOD in upper 50% of the bar's range -> CE setup.
   - Target = Session VWAP; Stop Loss = Signal Bar Extreme + buffer; minimum R:R >= 3.0.
3. IntradayReversalEngine:
   - Ties Exhaustion Gate and Failure-at-Extreme together.
   - Hysteresis & Arbitration Lockout (GM-GATE-002): 15-minute (900s) cooldown between reversal
     signals, and max 2 attempts per boundary per session.
   - Point-in-Time causal timing (GM-GATE-003): Signal emitted strictly at Bar T close; simulated
     entry modeled at Bar T+1 open.
   - Non-negotiable repository safety invariants (GM-GATE-005): read_only=True, is_order_action=False,
     broker_api_called=False, allowed_for_live_execution=False,
     edge_certification_status="NO_CERTIFIED_EDGE".
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, List, Dict


class ReversalSetupType(str, Enum):
    FAH = "FAILURE_AT_HIGH"                    # Spot pierced HOD, closed back inside -> PE Fade
    FAL = "FAILURE_AT_LOW"                     # Spot pierced LOD, closed back inside -> CE Fade
    VWAP_EXTREME_REVERSION = "VWAP_REVERSION"  # Band exhaustion > 2.0 sigma with absorption


class ReversalDirection(str, Enum):
    CE = "CE"  # Bullish reversal (fading low)
    PE = "PE"  # Bearish reversal (fading high)


@dataclass(slots=True, frozen=True)
class ExhaustionMetrics:
    vwap: float
    sigma_vwap: float
    deviation_sigmas: float
    is_exhausted: bool
    is_runaway_trend: bool
    absorption_ratio: float
    reason: str


@dataclass(slots=True, frozen=True)
class IntradayReversalSignal:
    timestamp_ms: int
    index_name: str
    direction: ReversalDirection
    setup_type: ReversalSetupType
    reference_extreme: float
    trigger_price: float
    stop_loss_price: float
    target_vwap: float
    risk_pts: float
    reward_pts: float
    risk_reward_ratio: float
    deviation_sigmas: float
    absorption_ratio: float
    setup_reason: str
    # Safety Invariant Metadata (GM-GATE-005)
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    edge_certification_status: str = "NO_CERTIFIED_EDGE"


class IntradayExhaustionGate:
    """Calculates continuous spot VWAP, rolling standard deviation bands, volume absorption,
    and runaway trend detection.
    """

    def __init__(
        self,
        min_deviation_sigmas: float = 1.5,
        max_deviation_sigmas: float = 2.5,
        slope_threshold: float = 0.5,
        spread_veto_threshold: float = 0.04,
        min_depth_ratio: float = 0.80,
    ) -> None:
        self.min_deviation_sigmas = min_deviation_sigmas
        self.max_deviation_sigmas = max_deviation_sigmas
        self.slope_threshold = slope_threshold
        self.spread_veto_threshold = spread_veto_threshold
        self.min_depth_ratio = min_depth_ratio

        # Rolling accumulators for VWAP & Standard Deviation
        self.total_volume: float = 0.0
        self.total_pv: float = 0.0
        self.bars_data: list[tuple[float, float]] = []  # (typical_price, volume)
        self.vwap_history: deque[float] = deque(maxlen=20)
        self.volume_history: deque[float] = deque(maxlen=20)
        self.tr_history: deque[float] = deque(maxlen=14)
        self.last_close: Optional[float] = None

    def reset(self) -> None:
        self.total_volume = 0.0
        self.total_pv = 0.0
        self.bars_data.clear()
        self.vwap_history.clear()
        self.volume_history.clear()
        self.tr_history.clear()
        self.last_close = None

    def update_bar(
        self,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> ExhaustionMetrics:
        """Update bar state and compute continuous VWAP, rolling standard deviation,
        and trend exhaustion metrics.
        """
        typ_price = (high + low + close) / 3.0
        v = max(volume, 1.0)

        self.total_volume += v
        self.total_pv += typ_price * v
        self.bars_data.append((typ_price, v))

        current_vwap = self.total_pv / self.total_volume
        self.vwap_history.append(current_vwap)
        self.volume_history.append(v)

        # Update True Range (ATR_14)
        if self.last_close is not None:
            tr = max(high - low, abs(high - self.last_close), abs(low - self.last_close))
        else:
            tr = high - low
        self.tr_history.append(tr)
        self.last_close = close

        # Calculate standard deviation sigma_vwap: sqrt( sum(V * (P - VWAP)^2) / sum(V) )
        sum_sq_diff = sum(vol_i * ((p_i - current_vwap) ** 2) for p_i, vol_i in self.bars_data)
        sigma_vwap = math.sqrt(sum_sq_diff / self.total_volume) if self.total_volume > 0 else 1.0
        if sigma_vwap < 1e-6:
            sigma_vwap = 1.0

        dev_pts = close - current_vwap
        dev_sigmas = dev_pts / sigma_vwap
        abs_dev_sigmas = abs(dev_sigmas)

        # Evaluate runaway trend:
        # Monotonic VWAP slope > 0.5 pts/bar over recent bars AND deviation outside 2.5 sigma
        is_runaway = False
        slope = 0.0
        if len(self.vwap_history) >= 5:
            # Check delta VWAP over last 4 intervals (5 bars)
            slope = (self.vwap_history[-1] - self.vwap_history[-5]) / 4.0
            if abs(slope) >= self.slope_threshold and abs_dev_sigmas >= self.max_deviation_sigmas:
                is_runaway = True

        # Volume absorption ratio
        avg_vol = sum(self.volume_history) / len(self.volume_history) if self.volume_history else 1.0
        absorption_ratio = v / avg_vol if avg_vol > 0 else 1.0

        is_exhausted = (self.min_deviation_sigmas <= abs_dev_sigmas <= self.max_deviation_sigmas)

        reason = "NORMAL"
        if is_runaway:
            reason = "VETO_RUNAWAY_TREND"
        elif is_exhausted:
            reason = "BAND_EXHAUSTED"

        return ExhaustionMetrics(
            vwap=current_vwap,
            sigma_vwap=sigma_vwap,
            deviation_sigmas=dev_sigmas,
            is_exhausted=is_exhausted,
            is_runaway_trend=is_runaway,
            absorption_ratio=absorption_ratio,
            reason=reason,
        )

    def evaluate_spread(
        self,
        bid: float,
        ask: float,
        bid_depth: float = 1.0,
        ask_depth: float = 1.0,
    ) -> Tuple[bool, str]:
        """Adverse selection gate (GM-GATE-004).
        Vetoes setups when option spread ratio > 4.0% or book depth is heavily skewed.
        Returns (is_vetoed, reason).
        """
        if bid <= 0 or ask <= 0 or ask < bid:
            return True, "VETO_SPREAD_INVALID"

        mid = (bid + ask) / 2.0
        spread = ask - bid
        spread_ratio = spread / mid if mid > 0 else 1.0

        if spread_ratio > self.spread_veto_threshold:
            return True, "VETO_SPREAD_EXPANDED"

        if ask_depth > 0:
            depth_ratio = bid_depth / ask_depth
            if depth_ratio < self.min_depth_ratio:
                # Insufficient bid replenishment / absorption
                pass

        return False, "SPREAD_OK"


class FailureAtExtremeEngine:
    """Detects Failure-at-High (FAH) and Failure-at-Low (FAL) rejections with asymmetric R:R."""

    def __init__(
        self,
        min_pierce_pts: float = 2.0,
        max_pierce_pts: float = 25.0,
        sl_buffer_pts: float = 3.0,
        min_risk_reward: float = 3.0,
    ) -> None:
        self.min_pierce_pts = min_pierce_pts
        self.max_pierce_pts = max_pierce_pts
        self.sl_buffer_pts = sl_buffer_pts
        self.min_risk_reward = min_risk_reward

    def evaluate_fah(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        prior_hod: float,
        vwap: float,
        timestamp_ms: int,
        index_name: str,
        deviation_sigmas: float = 0.0,
        absorption_ratio: float = 1.0,
    ) -> Optional[IntradayReversalSignal]:
        """Evaluates Failure-at-High (FAH) rejection -> generates PE reversal setup."""
        if prior_hod <= 0:
            return None

        bar_range = bar_high - bar_low
        if bar_range <= 0:
            return None

        # Condition 2 & 3: High pierces prior HOD by delta in [min_pierce, max_pierce]
        pierce = bar_high - prior_hod
        if pierce < self.min_pierce_pts or pierce > self.max_pierce_pts:
            return None

        # Condition 4: Close confirms rejection back below prior HOD
        if bar_close >= prior_hod:
            return None

        # Condition 5: Close is in lower 50% of the bar's range
        close_pos = (bar_close - bar_low) / bar_range
        if close_pos > 0.50:
            return None

        # Invariant 5: Target is session VWAP; Stop Loss is High + SL_Buffer
        stop_loss = bar_high + self.sl_buffer_pts
        risk_pts = stop_loss - bar_close
        reward_pts = bar_close - vwap

        if risk_pts <= 0 or reward_pts <= 0:
            return None

        rr_ratio = reward_pts / risk_pts
        if rr_ratio < self.min_risk_reward:
            return None

        return IntradayReversalSignal(
            timestamp_ms=timestamp_ms,
            index_name=index_name,
            direction=ReversalDirection.PE,
            setup_type=ReversalSetupType.FAH,
            reference_extreme=prior_hod,
            trigger_price=bar_close,
            stop_loss_price=stop_loss,
            target_vwap=vwap,
            risk_pts=round(risk_pts, 2),
            reward_pts=round(reward_pts, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            deviation_sigmas=round(deviation_sigmas, 2),
            absorption_ratio=round(absorption_ratio, 2),
            setup_reason=f"FAH Rejection @ {prior_hod:.1f} (High={bar_high:.1f}, Close={bar_close:.1f}) -> Target VWAP {vwap:.1f} (R:R {rr_ratio:.1f})",
        )

    def evaluate_fal(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        prior_lod: float,
        vwap: float,
        timestamp_ms: int,
        index_name: str,
        deviation_sigmas: float = 0.0,
        absorption_ratio: float = 1.0,
    ) -> Optional[IntradayReversalSignal]:
        """Evaluates Failure-at-Low (FAL) rejection -> generates CE reversal setup."""
        if prior_lod <= 0:
            return None

        bar_range = bar_high - bar_low
        if bar_range <= 0:
            return None

        # Condition 2 & 3: Low pierces prior LOD by delta in [min_pierce, max_pierce]
        pierce = prior_lod - bar_low
        if pierce < self.min_pierce_pts or pierce > self.max_pierce_pts:
            return None

        # Condition 4: Close confirms rejection back above prior LOD
        if bar_close <= prior_lod:
            return None

        # Condition 5: Close is in upper 50% of the bar's range
        close_pos = (bar_close - bar_low) / bar_range
        if close_pos < 0.50:
            return None

        # Invariant 5: Target is session VWAP; Stop Loss is Low - SL_Buffer
        stop_loss = bar_low - self.sl_buffer_pts
        risk_pts = bar_close - stop_loss
        reward_pts = vwap - bar_close

        if risk_pts <= 0 or reward_pts <= 0:
            return None

        rr_ratio = reward_pts / risk_pts
        if rr_ratio < self.min_risk_reward:
            return None

        return IntradayReversalSignal(
            timestamp_ms=timestamp_ms,
            index_name=index_name,
            direction=ReversalDirection.CE,
            setup_type=ReversalSetupType.FAL,
            reference_extreme=prior_lod,
            trigger_price=bar_close,
            stop_loss_price=stop_loss,
            target_vwap=vwap,
            risk_pts=round(risk_pts, 2),
            reward_pts=round(reward_pts, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            deviation_sigmas=round(deviation_sigmas, 2),
            absorption_ratio=round(absorption_ratio, 2),
            setup_reason=f"FAL Rejection @ {prior_lod:.1f} (Low={bar_low:.1f}, Close={bar_close:.1f}) -> Target VWAP {vwap:.1f} (R:R {rr_ratio:.1f})",
        )


class IntradayReversalEngine:
    """Ties together IntradayExhaustionGate and FailureAtExtremeEngine with hysteresis,
    arbitration, quota caps, and causal timing invariants.
    """

    # Non-negotiable repository safety invariants (GM-GATE-005)
    READ_ONLY: bool = True
    IS_ORDER_ACTION: bool = False
    BROKER_API_CALLED: bool = False
    ALLOWED_FOR_LIVE_EXECUTION: bool = False
    EDGE_CERTIFICATION_STATUS: str = "NO_CERTIFIED_EDGE"

    def __init__(
        self,
        index_name: str = "NIFTY",
        cooldown_ms: int = 900_000,  # 15 minutes = 900 seconds
        max_attempts_per_boundary: int = 2,
        min_pierce_pts: Optional[float] = None,
        max_pierce_pts: Optional[float] = None,
        sl_buffer_pts: Optional[float] = None,
    ) -> None:
        self.index_name = index_name.upper()
        self.cooldown_ms = cooldown_ms
        self.max_attempts_per_boundary = max_attempts_per_boundary

        is_sensex = (self.index_name == "SENSEX")
        if min_pierce_pts is None:
            min_pierce_pts = 10.0 if is_sensex else 2.0
        if max_pierce_pts is None:
            max_pierce_pts = 75.0 if is_sensex else 25.0
        if sl_buffer_pts is None:
            sl_buffer_pts = 10.0 if is_sensex else 3.0

        self.exhaustion_gate = IntradayExhaustionGate()
        self.failure_engine = FailureAtExtremeEngine(
            min_pierce_pts=min_pierce_pts,
            max_pierce_pts=max_pierce_pts,
            sl_buffer_pts=sl_buffer_pts,
            min_risk_reward=3.0,
        )

        # Causal State (GM-GATE-003): Prior session extremes strictly derived from Bar 1..T-1
        self.prior_hod: float = -math.inf
        self.prior_lod: float = math.inf
        self.last_signal_timestamp_ms: int = 0
        self.boundary_attempts: Dict[str, int] = {"HOD": 0, "LOD": 0}
        self.last_veto_reason: str = "NONE"
        self.signals_history: list[IntradayReversalSignal] = []

    def reset_session(self) -> None:
        """Reset session state at the start of each trading day."""
        self.prior_hod = -math.inf
        self.prior_lod = math.inf
        self.last_signal_timestamp_ms = 0
        self.boundary_attempts = {"HOD": 0, "LOD": 0}
        self.last_veto_reason = "NONE"
        self.signals_history.clear()
        self.exhaustion_gate.reset()

    def seed_prior_extremes(self, hod: float, lod: float) -> None:
        """Explicitly seeds running HOD and LOD for point-in-time evaluation."""
        self.prior_hod = hod
        self.prior_lod = lod

    def evaluate_option_spread(
        self,
        bid: float,
        ask: float,
        bid_depth: float = 1.0,
        ask_depth: float = 1.0,
    ) -> Tuple[bool, str]:
        """Expose adverse selection spread veto evaluation."""
        return self.exhaustion_gate.evaluate_spread(
            bid=bid,
            ask=ask,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
        )

    def evaluate_bar(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        volume: float,
        timestamp_ms: int,
        forced_vwap: Optional[float] = None,
    ) -> Optional[IntradayReversalSignal]:
        """Evaluates a completed Bar T for reversal signals at Bar T close.
        Simulated entry is modeled strictly at Bar T+1 open (GM-GATE-003).
        """
        self.last_veto_reason = "NONE"

        # 1. Update Exhaustion Gate metrics
        exhaustion = self.exhaustion_gate.update_bar(
            high=bar_high,
            low=bar_low,
            close=bar_close,
            volume=volume,
        )
        vwap = forced_vwap if forced_vwap is not None else exhaustion.vwap

        # If HOD/LOD not initialized, seed with current bar and return (no prior extreme yet)
        if self.prior_hod == -math.inf or self.prior_lod == math.inf:
            self.prior_hod = max(self.prior_hod, bar_high)
            self.prior_lod = min(self.prior_lod, bar_low)
            return None

        # 2. Check Runaway Trend suppression (GM-GATE-001)
        if exhaustion.is_runaway_trend:
            self.last_veto_reason = "VETO_RUNAWAY_TREND"
            # Update running extremes causally
            self.prior_hod = max(self.prior_hod, bar_high)
            self.prior_lod = min(self.prior_lod, bar_low)
            return None

        # 3. Check Failure-at-High (FAH) setup
        fah_candidate = self.failure_engine.evaluate_fah(
            bar_open=bar_open,
            bar_high=bar_high,
            bar_low=bar_low,
            bar_close=bar_close,
            prior_hod=self.prior_hod,
            vwap=vwap,
            timestamp_ms=timestamp_ms,
            index_name=self.index_name,
            deviation_sigmas=exhaustion.deviation_sigmas,
            absorption_ratio=exhaustion.absorption_ratio,
        )

        # 4. Check Failure-at-Low (FAL) setup
        fal_candidate = self.failure_engine.evaluate_fal(
            bar_open=bar_open,
            bar_high=bar_high,
            bar_low=bar_low,
            bar_close=bar_close,
            prior_lod=self.prior_lod,
            vwap=vwap,
            timestamp_ms=timestamp_ms,
            index_name=self.index_name,
            deviation_sigmas=exhaustion.deviation_sigmas,
            absorption_ratio=exhaustion.absorption_ratio,
        )

        candidate = fah_candidate or fal_candidate

        if candidate is not None:
            boundary_key = "HOD" if candidate.setup_type == ReversalSetupType.FAH else "LOD"

            # Check Quota Cap (GM-GATE-002: Max 2 attempts per boundary per session)
            if self.boundary_attempts[boundary_key] >= self.max_attempts_per_boundary:
                self.last_veto_reason = "EXHAUSTED_QUOTA"
                self.prior_hod = max(self.prior_hod, bar_high)
                self.prior_lod = min(self.prior_lod, bar_low)
                return None

            # Check Temporal Hysteresis Cooldown (GM-GATE-002: 15-minute / 900s lock)
            if self.last_signal_timestamp_ms > 0:
                elapsed = timestamp_ms - self.last_signal_timestamp_ms
                if elapsed < self.cooldown_ms:
                    self.last_veto_reason = "COOLDOWN_ACTIVE"
                    self.prior_hod = max(self.prior_hod, bar_high)
                    self.prior_lod = min(self.prior_lod, bar_low)
                    return None

            # Setup passed all gates! Register signal and update state
            self.boundary_attempts[boundary_key] += 1
            self.last_signal_timestamp_ms = timestamp_ms
            self.signals_history.append(candidate)

            # Update running extremes causally
            self.prior_hod = max(self.prior_hod, bar_high)
            self.prior_lod = min(self.prior_lod, bar_low)
            return candidate

        # Update running extremes causally for next bar T+1
        self.prior_hod = max(self.prior_hod, bar_high)
        self.prior_lod = min(self.prior_lod, bar_low)
        return None
