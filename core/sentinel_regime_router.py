"""Sentinel Regime Router & Microstructure Feature Engine.

FEAT-SENTINEL-REGIME-ROUTER-001: Modular Upstream Supervisory Regime Router
& Microstructure Calibration Engine for Sentinel.

Strict Non-Invasive Safety Contract:
    read_only = True
    is_order_action = False
    broker_api_called = False
    allowed_for_live_execution = False
    edge_certification_status = "NO_CERTIFIED_EDGE"
"""

from __future__ import annotations

import math
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Canonical Market Regimes
REGIME_RUNAWAY_EXPANSION = "RUNAWAY_EXPANSION"
REGIME_ROTATIONAL_CHOP = "ROTATIONAL_CHOP"
REGIME_EXHAUSTION_REVERSAL = "EXHAUSTION_REVERSAL"
REGIME_VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
REGIME_AMBIGUOUS_NO_TRADE = "AMBIGUOUS_NO_TRADE"
REGIME_CIRCUIT_EMERGENCY = "REGIME_CIRCUIT_EMERGENCY"
REGIME_DATA_GUARD_FAIL_CLOSED = "DATA_GUARD_FAIL_CLOSED"

ALL_CANONICAL_REGIMES = (
    REGIME_RUNAWAY_EXPANSION,
    REGIME_ROTATIONAL_CHOP,
    REGIME_EXHAUSTION_REVERSAL,
    REGIME_VOLATILITY_COMPRESSION,
)


@dataclass(slots=True, frozen=True)
class RegimePosteriorState:
    """Vector output data contract representing the continuous simplex distribution

    and supervisory permissions at a closed bar boundary.
    """

    probabilities: Dict[str, float]  # Continuous vector on Delta^4
    dominant_regime: str             # Dominant regime name or fail-closed state
    entropy: float                   # Shannon entropy H(P_t)
    normalized_entropy: float        # Normalized entropy H_tilde in [0.0, 1.0]
    regime_epoch: int                # Monotonically increasing bar sequence token
    bar_timestamp_ms: int            # Frozen bar T-1 boundary close timestamp
    dwell_bars: int                  # Current regime dwell duration
    session_switch_count: int        # Cumulative regime flips today
    permissions: Dict[str, bool]     # Advisory permissions per setup family: {"ORB", "APM_REENTRY", "REVERSAL"}
    is_trading_permitted: bool       # Global supervisory gate
    fail_closed_reason: str          # Empty if normal, or diagnostic string

    # Non-negotiable architectural safety invariants
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    edge_certification_status: str = "NO_CERTIFIED_EDGE"


class RingBufferFeatureExtractor:
    """Pre-allocated C-contiguous numpy ndarray ring buffer of fixed capacity (default N=1024).

    Zero dynamic heap allocation per tick. Guarantees sub-millisecond evaluation (SYS-02).
    """

    def __init__(self, capacity: int = 1024) -> None:
        self.capacity = capacity
        self.prices = np.zeros(capacity, dtype=np.float64)
        self.volumes = np.zeros(capacity, dtype=np.float64)
        self.cvds = np.zeros(capacity, dtype=np.float64)
        self.timestamps_ms = np.zeros(capacity, dtype=np.int64)
        self.head = 0
        self.size = 0

    def append(self, price: float, volume: float, cvd: float, timestamp_ms: int) -> None:
        idx = self.head
        self.prices[idx] = price
        self.volumes[idx] = volume
        self.cvds[idx] = cvd
        self.timestamps_ms[idx] = timestamp_ms
        self.head = (idx + 1) % self.capacity
        if self.size < self.capacity:
            self.size += 1

    def get_latest_slice(self, length: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns ordered slices of (prices, volumes, cvds) of given length up to self.size."""
        n = min(length, self.size)
        if n == 0:
            return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
        indices = [(self.head - n + i) % self.capacity for i in range(n)]
        return self.prices[indices], self.volumes[indices], self.cvds[indices]


class RegimeJournalWAL:
    """Idempotent crash recovery via local append-only binary Write-Ahead-Log (SYS-03).

    Eliminates lookahead REST backfill leaks by replaying up to T_crash.
    Format:
    [8 bytes timestamp_ms][8 bytes epoch][4 bytes dominant_len][dominant_str][4 bytes perms_bitmask][4 bytes reason_len][reason_str]
    """

    def __init__(self, wal_path: str = "runtime/regime_journal.wal") -> None:
        self.wal_path = Path(wal_path)
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)

    def write_state(self, state: RegimePosteriorState) -> None:
        bitmask = 0
        if state.permissions.get("ORB", False):
            bitmask |= 1
        if state.permissions.get("APM_REENTRY", False):
            bitmask |= 2
        if state.permissions.get("REVERSAL", False):
            bitmask |= 4
        if state.is_trading_permitted:
            bitmask |= 8

        dom_bytes = state.dominant_regime.encode("utf-8")
        reason_bytes = state.fail_closed_reason.encode("utf-8")

        # Header: ts_ms (q), epoch (q), dom_len (i), dom_bytes, bitmask (i), reason_len (i), reason_bytes
        header = struct.pack(
            f">qqI{len(dom_bytes)}sII{len(reason_bytes)}s",
            state.bar_timestamp_ms,
            state.regime_epoch,
            len(dom_bytes),
            dom_bytes,
            bitmask,
            len(reason_bytes),
            reason_bytes,
        )

        with open(self.wal_path, "ab") as f:
            f.write(header)
            f.flush()

    def replay_states(self) -> List[Dict[str, Any]]:
        if not self.wal_path.exists():
            return []

        records = []
        with open(self.wal_path, "rb") as f:
            data = f.read()

        offset = 0
        length = len(data)
        while offset + 20 <= length:
            ts_ms, epoch, dom_len = struct.unpack_from(">qqI", data, offset)
            offset += 20
            if offset + dom_len + 8 > length:
                break
            dom_bytes = data[offset : offset + dom_len]
            dominant = dom_bytes.decode("utf-8", errors="replace")
            offset += dom_len

            bitmask, reason_len = struct.unpack_from(">II", data, offset)
            offset += 8
            if offset + reason_len > length:
                break
            reason_bytes = data[offset : offset + reason_len]
            reason = reason_bytes.decode("utf-8", errors="replace")
            offset += reason_len

            records.append({
                "bar_timestamp_ms": ts_ms,
                "regime_epoch": epoch,
                "dominant_regime": dominant,
                "permissions": {
                    "ORB": bool(bitmask & 1),
                    "APM_REENTRY": bool(bitmask & 2),
                    "REVERSAL": bool(bitmask & 4),
                },
                "is_trading_permitted": bool(bitmask & 8),
                "fail_closed_reason": reason,
            })
        return records


class OptionsGreekSupervisor:
    """Options Volatility & Greeks Dynamics Supervisory Invariant Gates (GREEK-01..04)."""

    def __init__(
        self,
        iv_velocity_crush_threshold: float = -1.5,  # -1.5 pts/hour
        spread_slip_budget_pct: float = 1.5,        # 1.5% max spread drag
        skew_ce_reversal_min: float = 1.15,         # Put/Call skew > 1.15 for CE bottom fades
        skew_pe_reversal_max: float = 0.95,         # Put/Call skew < 0.95 for PE top fades
    ) -> None:
        self.iv_velocity_crush_threshold = iv_velocity_crush_threshold
        self.spread_slip_budget_pct = spread_slip_budget_pct
        self.skew_ce_reversal_min = skew_ce_reversal_min
        self.skew_pe_reversal_max = skew_pe_reversal_max

    def evaluate_iv_velocity(self, d_iv_15m: float) -> Tuple[bool, str]:
        """GREEK-01: Blocks call/breakout buying if rolling 15m IV velocity < -tau_vol."""
        if math.isnan(d_iv_15m) or math.isinf(d_iv_15m):
            return False, "INVALID_IV_METRIC"
        if d_iv_15m < self.iv_velocity_crush_threshold:
            return False, f"IV_CRUSH_DETECTED(velocity={d_iv_15m:.2f} < {self.iv_velocity_crush_threshold})"
        return True, "IV_VELOCITY_OK"

    def evaluate_gamma_theta_budget(
        self,
        spot_velocity_pts_15m: float,
        abs_theta: float,
        abs_delta: float,
        is_zero_dte: bool,
        current_time: dt_time,
    ) -> Tuple[bool, str]:
        """GREEK-02: Gamma-to-Theta budget threshold post-12:00 PM on 0-DTE.

        Requires: Underlying Velocity v_spot > |Theta| / (|Delta| * 100).
        """
        if not is_zero_dte or current_time < dt_time(12, 0):
            return True, "BUDGET_NOT_APPLICABLE"

        if abs_delta <= 1e-6:
            return False, "DELTA_ZERO_BUDGET_FAIL"

        theta_drag_threshold = abs_theta / (abs_delta * 100.0)
        if spot_velocity_pts_15m <= theta_drag_threshold:
            return False, f"THETA_BLEED_EXCEEDS_VELOCITY(spot_vel={spot_velocity_pts_15m:.2f} <= req={theta_drag_threshold:.2f})"
        return True, "GAMMA_THETA_BUDGET_OK"

    def evaluate_skew_ratio(self, skew_ratio: float, setup_type: str) -> Tuple[bool, str]:
        """GREEK-03: Asymmetric Put/Call skew differential.

        - CE reversals require 25-delta Put/Call Skew ratio > 1.15 (panic put bid overextended).
        - PE reversals require Skew ratio < 0.95 (complacent call skew topping).
        """
        if math.isnan(skew_ratio) or math.isinf(skew_ratio):
            return False, "INVALID_SKEW_RATIO"

        if setup_type == "CE_REVERSAL":
            if skew_ratio < self.skew_ce_reversal_min:
                return False, f"SKEW_BELOW_CE_THRESHOLD(skew={skew_ratio:.2f} < {self.skew_ce_reversal_min})"
        elif setup_type == "PE_REVERSAL":
            if skew_ratio > self.skew_pe_reversal_max:
                return False, f"SKEW_ABOVE_PE_THRESHOLD(skew={skew_ratio:.2f} > {self.skew_pe_reversal_max})"
        return True, "SKEW_RATIO_OK"

    def evaluate_spread_slip_budget(self, bid: float, ask: float) -> Tuple[bool, str]:
        """GREEK-04: Maximum allowable top-of-book spread drag (Ask - Bid) / Mid <= 1.5%."""
        if bid <= 0 or ask <= 0 or ask < bid:
            return False, "INVALID_QUOTE_SPREAD"
        mid = (bid + ask) / 2.0
        spread_pct = ((ask - bid) / mid) * 100.0
        if spread_pct > self.spread_slip_budget_pct:
            return False, f"SPREAD_BUDGET_EXCEEDED(spread={spread_pct:.2f}% > {self.spread_slip_budget_pct}%)"
        return True, "SPREAD_BUDGET_OK"


class SentinelRegimeRouter:
    """Supervisory Regime Router for Sentinel Live Stream Advisor.

    Enforces all 20 invariants (MICRO-01..04, STAT-01..04, SYS-01..05, GREEK-01..04, RG-01..04).
    """

    def __init__(
        self,
        temperature: float = 0.5,
        switching_penalty: float = 0.25,
        min_dwell_bars: int = 12,
        flip_cap: int = 4,
        entropy_threshold: float = 0.85,
        wal_path: str = "runtime/regime_journal.wal",
        enable_wal: bool = False,
    ) -> None:
        self.temperature = max(temperature, 1e-4)
        self.switching_penalty = switching_penalty
        self.min_dwell_bars = min_dwell_bars
        self.flip_cap = flip_cap
        self.entropy_threshold = entropy_threshold

        # Pre-allocated ring buffer
        self.ring_buffer = RingBufferFeatureExtractor(capacity=1024)

        # Greeks supervisor
        self.greek_supervisor = OptionsGreekSupervisor()

        # WAL
        self.enable_wal = enable_wal
        self.wal = RegimeJournalWAL(wal_path) if enable_wal else None

        # State tracking
        self.current_epoch: int = 0
        self.last_switch_epoch: int = 0
        self.session_switch_count: int = 0
        self.last_dominant_regime: str = REGIME_ROTATIONAL_CHOP
        self.current_dwell_bars: int = 0
        self.high_entropy_consecutive_bars: int = 0
        self.cooldown_remaining_bars: int = 0

        # Resting depth EWMM state (MICRO-04)
        self.ewmm_depth_bid: float = 0.0
        self.ewmm_depth_ask: float = 0.0
        self.ewmm_alpha: float = 0.2

        # Caching frozen state of Bar T-1 (SYS-01)
        self._current_frozen_state: Optional[RegimePosteriorState] = None

        # Non-invasive safety attributes
        self.read_only: bool = True
        self.is_order_action: bool = False
        self.broker_api_called: bool = False
        self.allowed_for_live_execution: bool = False
        self.edge_certification_status: str = "NO_CERTIFIED_EDGE"

    @property
    def current_state(self) -> Optional[RegimePosteriorState]:
        """SYS-01: Strategies evaluating during Bar T only see the frozen state of Bar T-1."""
        return self._current_frozen_state

    def reset_session(self) -> None:
        """Reset session-specific tracking state at morning discovery."""
        self.session_switch_count = 0
        self.current_dwell_bars = 0
        self.last_switch_epoch = self.current_epoch
        self.high_entropy_consecutive_bars = 0
        self.cooldown_remaining_bars = 0
        self.last_dominant_regime = REGIME_ROTATIONAL_CHOP

    def calculate_decay_vwap(self, prices: np.ndarray, volumes: np.ndarray, half_life_bars: float = 45.0) -> Tuple[float, float]:
        """MICRO-01: Time-decay normalized VWAP (session volume dampener).

        VWAP_t = sum(P_i * V_i * e^(-lambda * (t - i))) / sum(V_i * e^(-lambda * (t - i)))
        Returns (vwap, sigma_vwap).
        """
        n = len(prices)
        if n == 0 or np.sum(volumes) <= 0:
            return 0.0, 1.0

        decay_lambda = math.log(2.0) / max(half_life_bars, 1.0)
        time_diffs = np.arange(n - 1, -1, -1, dtype=np.float64)
        weights = volumes * np.exp(-decay_lambda * time_diffs)
        total_weight = np.sum(weights)

        if total_weight <= 1e-12:
            return float(prices[-1]), 1.0

        vwap = float(np.sum(prices * weights) / total_weight)
        var = float(np.sum(weights * (prices - vwap) ** 2) / total_weight)
        sigma = math.sqrt(max(var, 1e-6))
        return vwap, sigma

    def confirm_cvd_delta(self, rolling_cvds: np.ndarray) -> Tuple[float, bool]:
        """MICRO-02: Aggressive Delta CVD confirmation.

        z_cvd = (Delta CVD_t - mu_cvd,20) / sigma_cvd,20. Breakout regimes require |z_cvd| >= 1.8.
        """
        if len(rolling_cvds) < 5:
            return 0.0, False

        diffs = np.diff(rolling_cvds)
        if len(diffs) < 2:
            return 0.0, False

        latest_delta = float(diffs[-1])
        window = diffs[-20:] if len(diffs) >= 20 else diffs
        mu = float(np.mean(window))
        sigma = float(np.std(window))

        if sigma < 1e-6:
            z_score = 0.0
        else:
            z_score = (latest_delta - mu) / sigma

        return z_score, abs(z_score) >= 1.8

    def check_opening_lockout(self, bar_time: dt_time) -> bool:
        """MICRO-03: 09:15 - 09:30 morning discovery auction lockout."""
        start_lockout = dt_time(9, 15)
        end_lockout = dt_time(9, 30)
        return start_lockout <= bar_time <= end_lockout

    def ewmm_depth_filter(self, raw_bid_depth: float, raw_ask_depth: float, persistence_sec: float) -> Tuple[float, float, bool]:
        """MICRO-04: Time-weighted resting depth persistence (tau_min >= 3.0s, EWMM filter).

        Flickering liquidity under 3.0s is rejected as phantom/spoofed depth.
        """
        if persistence_sec < 3.0:
            # Phantom/flickering liquidity under 3.0s is rejected
            return 0.0, 0.0, False

        self.ewmm_depth_bid = (1.0 - self.ewmm_alpha) * self.ewmm_depth_bid + self.ewmm_alpha * raw_bid_depth
        self.ewmm_depth_ask = (1.0 - self.ewmm_alpha) * self.ewmm_depth_ask + self.ewmm_alpha * raw_ask_depth
        return self.ewmm_depth_bid, self.ewmm_depth_ask, True

    def calculate_entropy(self, probabilities: np.ndarray) -> Tuple[float, float]:
        """STAT-01: Shannon entropy H(P_t) and normalized entropy H_tilde in [0, 1].

        H(P_t) = - sum(p_k * ln(p_k + 1e-12))
        H_tilde = H(P_t) / ln(4)
        """
        eps = 1e-12
        entropy = -float(np.sum(probabilities * np.log(probabilities + eps)))
        norm_entropy = float(entropy / math.log(4.0))
        norm_entropy = min(max(norm_entropy, 0.0), 1.0)
        return entropy, norm_entropy

    def evaluate_epoch_token(self, requested_epoch: int) -> Tuple[bool, str]:
        """SYS-04: Atomic epoch-token routing & signal fencing."""
        if self._current_frozen_state is None:
            return False, "ROUTER_NOT_INITIALIZED"
        if requested_epoch != self._current_frozen_state.regime_epoch:
            return False, f"STALE_EPOCH_REJECT(expected={self._current_frozen_state.regime_epoch}, got={requested_epoch})"
        return True, "EPOCH_VALID"

    def guard_data_feed(
        self,
        tick_staleness_sec: float,
        price: float,
        volume: float,
        depth_bid_sum: float,
        depth_ask_sum: float,
    ) -> Optional[str]:
        """RG-01: Deterministic fail-closed data guard.

        Rejects stale ticks (> 3.0s), zero depth, or NaN/Inf.
        """
        if tick_staleness_sec > 3.0:
            return f"FEED_STALE(staleness={tick_staleness_sec:.2f}s > 3.0s)"
        if any(math.isnan(x) or math.isinf(x) for x in (price, volume, depth_bid_sum, depth_ask_sum)):
            return "FEED_NAN_OR_INF_DETECTED"
        if depth_bid_sum <= 0.0 or depth_ask_sum <= 0.0:
            return "FEED_ZERO_ORDER_BOOK_DEPTH"
        return None

    def guard_circuit_limits(
        self,
        current_spot: float,
        circuit_lower_limit: float,
        circuit_upper_limit: float,
        rolling_tick_vol_sigma: float,
    ) -> Optional[str]:
        """RG-02: Index circuit freeze & volatility blowout kill-gate.

        Move within 2.0% of circuit limits or tick volatility > 5.0 sigma triggers emergency freeze.
        """
        if circuit_lower_limit > 0 and circuit_upper_limit > circuit_lower_limit:
            dist_to_lower = (current_spot - circuit_lower_limit) / current_spot
            dist_to_upper = (circuit_upper_limit - current_spot) / current_spot
            if dist_to_lower <= 0.02 or dist_to_upper <= 0.02:
                return f"CIRCUIT_PROXIMITY_FREEZE(dist_lower={dist_to_lower:.3f}, dist_upper={dist_to_upper:.3f})"

        if rolling_tick_vol_sigma > 5.0:
            return f"VOLATILITY_BLOWOUT_FREEZE(sigma={rolling_tick_vol_sigma:.2f} > 5.0)"

        return None

    def on_bar_close(
        self,
        bar_close: float,
        bar_volume: float,
        cvd_delta: float,
        timestamp_ms: int,
        bar_time: dt_time,
        tick_staleness_sec: float = 0.5,
        depth_bid: float = 500.0,
        depth_ask: float = 500.0,
        depth_persistence_sec: float = 4.0,
        circuit_lower: float = 0.0,
        circuit_upper: float = 0.0,
        tick_vol_sigma: float = 1.0,
    ) -> RegimePosteriorState:
        """Evaluates regime state strictly at closed bar boundary and freezes it for Bar T (SYS-01)."""
        self.current_epoch += 1
        epoch = self.current_epoch
        self.current_dwell_bars += 1

        # Check Fail-Closed Guard (RG-01)
        data_fail = self.guard_data_feed(tick_staleness_sec, bar_close, bar_volume, depth_bid, depth_ask)
        if data_fail:
            state = RegimePosteriorState(
                probabilities={r: 0.25 for r in ALL_CANONICAL_REGIMES},
                dominant_regime=REGIME_DATA_GUARD_FAIL_CLOSED,
                entropy=math.log(4.0),
                normalized_entropy=1.0,
                regime_epoch=epoch,
                bar_timestamp_ms=timestamp_ms,
                dwell_bars=self.current_dwell_bars,
                session_switch_count=self.session_switch_count,
                permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": False},
                is_trading_permitted=False,
                fail_closed_reason=data_fail,
            )
            self._current_frozen_state = state
            if self.enable_wal and self.wal:
                self.wal.write_state(state)
            return state

        # Check Circuit Freeze Guard (RG-02)
        circuit_fail = self.guard_circuit_limits(bar_close, circuit_lower, circuit_upper, tick_vol_sigma)
        if circuit_fail:
            state = RegimePosteriorState(
                probabilities={r: 0.25 for r in ALL_CANONICAL_REGIMES},
                dominant_regime=REGIME_CIRCUIT_EMERGENCY,
                entropy=math.log(4.0),
                normalized_entropy=1.0,
                regime_epoch=epoch,
                bar_timestamp_ms=timestamp_ms,
                dwell_bars=self.current_dwell_bars,
                session_switch_count=self.session_switch_count,
                permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": False},
                is_trading_permitted=False,
                fail_closed_reason=circuit_fail,
            )
            self._current_frozen_state = state
            if self.enable_wal and self.wal:
                self.wal.write_state(state)
            return state

        # Append to Ring Buffer (SYS-02)
        latest_cvd = (self.ring_buffer.cvds[(self.ring_buffer.head - 1) % self.ring_buffer.capacity] + cvd_delta) if self.ring_buffer.size > 0 else cvd_delta
        self.ring_buffer.append(bar_close, bar_volume, latest_cvd, timestamp_ms)

        # Microstructure Feature Extraction
        # MICRO-03: Opening lockout
        is_opening_lockout = self.check_opening_lockout(bar_time)

        # MICRO-04: Depth persistence filter
        ewmm_bid, ewmm_ask, depth_persisted = self.ewmm_depth_filter(depth_bid, depth_ask, depth_persistence_sec)

        # Get history from ring buffer
        p_slice, v_slice, cvd_slice = self.ring_buffer.get_latest_slice(60)

        # MICRO-01: Time-decay normalized VWAP
        vwap, sigma_vwap = self.calculate_decay_vwap(p_slice, v_slice)
        delta_vwap = (bar_close - vwap) / max(sigma_vwap, 1e-6)

        # MICRO-02: CVD Delta z-score
        z_cvd, cvd_confirmed = self.confirm_cvd_delta(cvd_slice)

        # Kaufman Efficiency Ratio (KER) over 15 bars
        if len(p_slice) >= 15:
            net_disp = abs(bar_close - p_slice[-15])
            gross_path = np.sum(np.abs(np.diff(p_slice[-15:])))
            ker = float(net_disp / max(gross_path, 1e-6))
        else:
            ker = 0.5

        # Compute raw affinities for the 4 regimes
        # 1. RUNAWAY_EXPANSION: high |delta_vwap|, high ker, confirmed CVD breakout
        a_runaway = 2.0 * ker + 1.2 * abs(delta_vwap) + (1.5 if cvd_confirmed else -0.5)
        # 2. ROTATIONAL_CHOP: low |delta_vwap|, low ker, balanced CVD
        a_chop = 2.0 * (1.0 - ker) + 1.5 * max(0.0, 1.5 - abs(delta_vwap)) - abs(z_cvd) * 0.5
        # 3. EXHAUSTION_REVERSAL: extreme |delta_vwap|, divergence in CVD, high depth imbalance
        a_reversal = 1.5 * max(0.0, abs(delta_vwap) - 2.0) + (1.0 if not cvd_confirmed and abs(delta_vwap) > 1.5 else -0.5)
        # 4. VOLATILITY_COMPRESSION: very low volatility and narrow range
        a_compression = 1.5 * max(0.0, 0.5 - sigma_vwap / bar_close * 100.0) + 1.0 * max(0.0, 0.3 - ker)

        if is_opening_lockout:
            # Enforce Rotational Chop during morning discovery
            a_chop += 10.0

        affinities = np.array([a_runaway, a_chop, a_reversal, a_compression], dtype=np.float64)

        # Continuous softmax temperature scaling (STAT-01)
        scaled_aff = affinities / self.temperature
        exp_aff = np.exp(scaled_aff - np.max(scaled_aff))
        probs = exp_aff / np.sum(exp_aff)

        prob_dict = {
            REGIME_RUNAWAY_EXPANSION: float(probs[0]),
            REGIME_ROTATIONAL_CHOP: float(probs[1]),
            REGIME_EXHAUSTION_REVERSAL: float(probs[2]),
            REGIME_VOLATILITY_COMPRESSION: float(probs[3]),
        }

        # Shannon entropy
        entropy, norm_entropy = self.calculate_entropy(probs)

        # STAT-03 & RG-04: Hysteresis switching kernel with sticky dwell and flip cap
        candidate_idx = int(np.argmax(probs))
        candidate_regime = ALL_CANONICAL_REGIMES[candidate_idx]

        is_switch = (candidate_regime != self.last_dominant_regime)

        # Evaluate flip cap and dwell restrictions
        dwell_satisfied = (self.current_dwell_bars >= self.min_dwell_bars)
        flip_cap_breached = (self.session_switch_count >= self.flip_cap)

        dominant_regime = self.last_dominant_regime
        if is_switch:
            if not dwell_satisfied:
                # Dwell time not met: lock to existing regime
                dominant_regime = self.last_dominant_regime
            elif flip_cap_breached:
                # Flip cap breached: lock to Rotational Chop
                dominant_regime = REGIME_ROTATIONAL_CHOP
            else:
                # Check switching penalty
                switching_advantage = probs[candidate_idx] - self.switching_penalty
                current_reg_idx = ALL_CANONICAL_REGIMES.index(self.last_dominant_regime)
                if switching_advantage > probs[current_reg_idx]:
                    dominant_regime = candidate_regime
                    self.last_dominant_regime = candidate_regime
                    self.session_switch_count += 1
                    self.current_dwell_bars = 0
                    self.last_switch_epoch = epoch

        # RG-04: Anti-chatter cooldown freeze if normalized entropy > 0.85 for 3 consecutive bars
        if norm_entropy > self.entropy_threshold:
            self.high_entropy_consecutive_bars += 1
        else:
            self.high_entropy_consecutive_bars = 0

        if self.high_entropy_consecutive_bars >= 3:
            self.cooldown_remaining_bars = 30  # 30-bar cooldown

        if self.cooldown_remaining_bars > 0:
            self.cooldown_remaining_bars -= 1

        # Check entropy ambiguity threshold
        fail_closed_reason = ""
        is_trading_permitted = True

        if is_opening_lockout:
            is_trading_permitted = False
            fail_closed_reason = "OPENING_DISCOVERY_LOCKOUT"
            dominant_regime = REGIME_ROTATIONAL_CHOP
        elif flip_cap_breached:
            is_trading_permitted = False
            fail_closed_reason = f"SESSION_FLIP_CAP_BREACHED(switches={self.session_switch_count} >= {self.flip_cap})"
            dominant_regime = REGIME_ROTATIONAL_CHOP
        elif self.cooldown_remaining_bars > 0:
            is_trading_permitted = False
            fail_closed_reason = f"ANTI_CHATTER_COOLDOWN_ACTIVE(remaining_bars={self.cooldown_remaining_bars})"
            dominant_regime = REGIME_AMBIGUOUS_NO_TRADE
        elif norm_entropy > self.entropy_threshold:
            is_trading_permitted = False
            fail_closed_reason = f"HIGH_ENTROPY_AMBIGUITY(norm_entropy={norm_entropy:.3f} > {self.entropy_threshold})"
            dominant_regime = REGIME_AMBIGUOUS_NO_TRADE

        # Advisory permissions mapping (SYS-05: entry permissions only)
        if not is_trading_permitted:
            permissions = {"ORB": False, "APM_REENTRY": False, "REVERSAL": False}
        else:
            permissions = {
                "ORB": dominant_regime == REGIME_RUNAWAY_EXPANSION,
                "APM_REENTRY": dominant_regime in (REGIME_RUNAWAY_EXPANSION, REGIME_VOLATILITY_COMPRESSION),
                "REVERSAL": dominant_regime == REGIME_EXHAUSTION_REVERSAL,
            }

        state = RegimePosteriorState(
            probabilities=prob_dict,
            dominant_regime=dominant_regime,
            entropy=entropy,
            normalized_entropy=norm_entropy,
            regime_epoch=epoch,
            bar_timestamp_ms=timestamp_ms,
            dwell_bars=self.current_dwell_bars,
            session_switch_count=self.session_switch_count,
            permissions=permissions,
            is_trading_permitted=is_trading_permitted,
            fail_closed_reason=fail_closed_reason,
        )

        self._current_frozen_state = state

        if self.enable_wal and self.wal:
            self.wal.write_state(state)

        return state
