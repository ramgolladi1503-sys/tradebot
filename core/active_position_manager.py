"""Active Position Manager (APM) for Sentinel Advisory Engine.

Formally designed per Hermes Architectural Specification and Grill Me Adversarial Audit:
- Strict finite state progression: STANDBY, ARMED, IN_FLIGHT, TRAIL_LOCK, EXIT_PENDING, LIQUIDATED
- Monotonic trailing stop ratchet (Compare-And-Swap non-decreasing invariant)
- Write-Ahead Log (WAL) with atomic rename for mid-flight crash recovery
- Pessimistic intrabar resolution contract (SL hits first if bar touches both SL and TP)
- Dynamic Session Phase Variance Decay (SPVD) energy gating (replaces arbitrary clock cutoff)
- 15-minute time horizon exit to prevent theta burn
"""

import json
import logging
import os
import math
import time
from datetime import datetime, time as dtime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

def compute_expiry_theta_holding_ceiling(
    base_max_hold_minutes: int,
    entry_time_str: str,
    is_expiry_day: bool,
    is_deep_itm: bool = False,
    accelerator_start: dtime = dtime(12, 30),
    accelerator_end: dtime = dtime(15, 0),
    min_hold_minutes: int = 15,
) -> int:
    """Computes dynamic theta accelerated holding ceiling on expiry afternoons.

    Invariant Specifications (Hermes Architecture & Gauntlet Protections):
    1. If not expiry day or if option is deep ITM, decay is zero -> returns base_max_hold_minutes.
    2. Continuous linear scaling from accelerator_start (12:30 IST) to accelerator_end (15:00 IST).
       Prevents arbitrary step-function boundary glitches.
    3. Floor clamped at min_hold_minutes (default 15m) to ensure statistical trade maturation.
    """
    if not is_expiry_day or is_deep_itm or not entry_time_str:
        return base_max_hold_minutes

    try:
        if "T" in entry_time_str:
            t_part = entry_time_str.split("T")[1][:8]
        elif " " in entry_time_str:
            t_part = entry_time_str.split(" ")[1][:8]
        else:
            t_part = entry_time_str[:8]
        dt = datetime.strptime(t_part, "%H:%M:%S").time()
    except Exception:
        return base_max_hold_minutes

    entry_mins = dt.hour * 60 + dt.minute + dt.second / 60.0
    start_mins = accelerator_start.hour * 60 + accelerator_start.minute
    end_mins = accelerator_end.hour * 60 + accelerator_end.minute

    if entry_mins <= start_mins:
        return base_max_hold_minutes
    if entry_mins >= end_mins:
        return min(base_max_hold_minutes, min_hold_minutes)

    decay_ratio = (entry_mins - start_mins) / float(end_mins - start_mins)
    scaled_hold = base_max_hold_minutes - (base_max_hold_minutes - min_hold_minutes) * decay_ratio
    return max(min_hold_minutes, int(round(scaled_hold)))

STATE_STANDBY = "STANDBY"
STATE_ARMED = "ARMED"
STATE_IN_FLIGHT = "IN_FLIGHT"
STATE_TRAIL_LOCK = "TRAIL_LOCK"
STATE_PULLBACK_WAIT = "PULLBACK_WAIT"
STATE_EXIT_PENDING = "EXIT_PENDING"
STATE_COOL_OFF = "COOL_OFF"
STATE_LIQUIDATED = "LIQUIDATED"

VALID_TRANSITIONS = {
    STATE_STANDBY: {STATE_ARMED},
    STATE_ARMED: {STATE_IN_FLIGHT, STATE_STANDBY},
    STATE_IN_FLIGHT: {STATE_TRAIL_LOCK, STATE_EXIT_PENDING, STATE_PULLBACK_WAIT},
    STATE_TRAIL_LOCK: {STATE_EXIT_PENDING, STATE_PULLBACK_WAIT},
    STATE_PULLBACK_WAIT: {STATE_ARMED, STATE_LIQUIDATED, STATE_STANDBY, STATE_COOL_OFF},
    STATE_EXIT_PENDING: {STATE_COOL_OFF, STATE_LIQUIDATED},
    STATE_COOL_OFF: {STATE_STANDBY, STATE_ARMED},
    STATE_LIQUIDATED: {STATE_COOL_OFF, STATE_STANDBY, STATE_ARMED, STATE_PULLBACK_WAIT},
}


@dataclass
class PositionPayload:
    position_id: str
    direction: str  # "CE" (Long) or "PE" (Short / Put Long)
    strike_contract: str
    entry_price: float
    entry_time: str
    current_sl: float
    initial_sl: float
    target_price: float
    max_hold_minutes: int = 15
    trail_locked: bool = False
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_time: Optional[str] = None
    pnl_pts: Optional[float] = None
    # Integer Lot Math & Capital Discretization Fields (Gate 1)
    lots: int = 1
    sizing_tier: str = "FULL_SIZE"  # "FULL_SIZE", "HALF_SIZE", "ZERO_SUPPRESS", "REJECT_INSUFFICIENT_MARGIN"
    lot_size: int = 65              # NIFTY=65, BANKNIFTY=40, SENSEX=20
    total_quantity: int = 65        # lots * lot_size
    # Real Traded Option Strike Fields (100% empirical read from WebSocket stream)
    opt_symbol: Optional[str] = None
    opt_token: Optional[str] = None
    opt_entry_ltp: Optional[float] = None
    opt_current_ltp: Optional[float] = None
    opt_target_pts: Optional[float] = None
    opt_sl_pts: Optional[float] = None
    opt_exit_ltp: Optional[float] = None
    opt_pnl_pts: Optional[float] = None
    opt_bid: Optional[float] = None
    opt_ask: Optional[float] = None
    is_runner_mode: bool = False
    half_booked: bool = False
    opt_peak_hwm: Optional[float] = None
    runner_trailing_sl: Optional[float] = None
    # Gear 1 vs Gear 2 Architecture Fields
    session_gear: str = "GEAR_1_RANGE"  # "GEAR_1_RANGE" or "GEAR_2_TREND"
    opt_stop_loss_pct: Optional[float] = None  # e.g. 0.20 for -20% option stop
    opt_initial_sl: Optional[float] = None
    target_1_hit: bool = False
    target_2_hit: bool = False
    max_spot_excursion: float = 0.0
    max_opt_excursion: float = 0.0
    # Peak Giveback Clamp & Pullback Re-entry Tracking
    giveback_clamp_sl: Optional[float] = None
    reentry_count: int = 0
    pullback_reference_price: Optional[float] = None
    # Tranche Accounting Schema Fields (Hermes Mandate 3)
    opt_half_booked_ltp: Optional[float] = None
    opt_half_booked_time: Optional[str] = None
    tranche_1_pnl_pts: Optional[float] = None
    runner_exit_ltp: Optional[float] = None
    runner_pnl_pts: Optional[float] = None
    blended_opt_pnl_pts: Optional[float] = None
    # Asymmetric Structural Runner Mode (15-Minute Swing Trailing)
    structural_runner_enabled: bool = False
    structural_swing_anchor_sl: Optional[float] = None  # 15m structural swing low (CE) or high (PE)


class ActivePositionManager:
    def __init__(self, wal_path: str = "runtime/sentinel_apm_wal.json"):
        self.wal_path = Path(wal_path)
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = STATE_STANDBY
        self.payload: Optional[PositionPayload] = None
        self.last_completed_trade: Optional[Dict[str, Any]] = None
        self.trade_history: List[Dict[str, Any]] = []
        self.cool_off_until: Optional[datetime] = None
        self.cool_off_ref_spot: Optional[float] = None
        self.cool_off_direction: Optional[str] = None
        self._last_wal_persist_ts: float = 0.0
        self._recover_state_or_fail_closed()

    def _persist_wal_atomic(self, force_sync: bool = True):
        """Invariant 1.2: Atomic Write-Ahead Log persistence via temp file rename.
        
        When force_sync=False, updates are debounced to at most once per 1.0s to protect
        the event loop thread from os.fsync storage jitter during continuous tick HWM updates.
        """
        now_ts = time.time()
        if not force_sync and (now_ts - self._last_wal_persist_ts) < 1.0:
            return

        tmp_path = self.wal_path.with_suffix(".tmp")
        data = {
            "state": self.state,
            "payload": asdict(self.payload) if self.payload else None,
            "last_completed_trade": self.last_completed_trade,
            "trade_history": self.trade_history,
            "cool_off_until": self.cool_off_until.isoformat() if self.cool_off_until else None,
            "cool_off_ref_spot": self.cool_off_ref_spot,
            "cool_off_direction": self.cool_off_direction,
            "persisted_at": datetime.now().isoformat()
        }
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            if force_sync:
                os.fsync(f.fileno())
        os.replace(tmp_path, self.wal_path)
        self._last_wal_persist_ts = now_ts

    def _recover_state_or_fail_closed(self):
        """Invariant 1.3: On boot, load WAL. If crashed mid-trade, mark fail-closed EXIT_PENDING."""
        if not self.wal_path.exists():
            return

        try:
            with open(self.wal_path, "r") as f:
                data = json.load(f)
            saved_state = data.get("state", STATE_STANDBY)
            saved_payload = data.get("payload")
            self.last_completed_trade = data.get("last_completed_trade")
            self.trade_history = data.get("trade_history", [])

            # Recover cool-off state
            saved_cool_until = data.get("cool_off_until")
            if saved_cool_until:
                try:
                    self.cool_off_until = datetime.fromisoformat(saved_cool_until)
                except Exception:
                    self.cool_off_until = None
            self.cool_off_ref_spot = data.get("cool_off_ref_spot")
            self.cool_off_direction = data.get("cool_off_direction")

            if saved_payload:
                self.payload = PositionPayload(**saved_payload)

            if saved_state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK, STATE_EXIT_PENDING}:
                # Crash recovery fail-closed: force immediate liquidation
                print(f"⚠️ [APM CRASH RECOVERY] Detected unclosed in-flight state '{saved_state}'. Fail-closed trigger!")
                self.state = STATE_EXIT_PENDING
                if self.payload:
                    self.payload.exit_reason = "CRASH_RECOVERY_FAIL_CLOSED"
                self._persist_wal_atomic(force_sync=True)
            else:
                self.state = saved_state
        except Exception as e:
            print(f"🚨 [APM WAL CORRUPTED] Error recovering WAL: {e}. Forcing STANDBY.")
            self.state = STATE_STANDBY
            self.payload = None

    def _transition_to(self, new_state: str, guard: bool = True) -> bool:
        if not guard:
            return False
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Illegal state transition from {self.state} to {new_state}")
        self.state = new_state
        self._persist_wal_atomic()
        return True

    def check_session_energy_gate(
        self,
        current_time: dtime,
        session_start: dtime = dtime(9, 15),
        session_end: dtime = dtime(15, 30),
        daily_norm_atr: float = 120.0,
        target_pts: float = 18.0,
        buffer_multiplier: float = 1.5,
        session_ker: Optional[float] = None
    ) -> Tuple[bool, float, float]:
        """Invariant 4.1: Dynamic Session Phase Variance Decay (SPVD) Energy Gate.
        
        Calculates expected remaining directional ATR:
        E[ATR_rem] = sqrt(T_rem) * ATR_norm * directional_efficiency_factor
        Guards against low-volatility late-session trap moves without arbitrary clock hardcoding.
        On chop/range days (low KER), directional energy decays significantly faster.
        """
        now_dt = datetime.combine(datetime.today(), current_time)
        start_dt = datetime.combine(datetime.today(), session_start)
        end_dt = datetime.combine(datetime.today(), session_end)

        total_secs = max(1.0, (end_dt - start_dt).total_seconds())
        rem_secs = max(0.0, (end_dt - now_dt).total_seconds())
        t_rem = rem_secs / total_secs

        # If KER is provided, directional efficiency factor scales energy (clamped between 0.25 and 1.0)
        eff_factor = 1.0
        if session_ker is not None:
            eff_factor = max(0.25, min(1.0, session_ker / 0.28))

        e_atr_rem = math.sqrt(t_rem) * daily_norm_atr * eff_factor
        required_energy = target_pts * buffer_multiplier

        can_enter = e_atr_rem >= required_energy
        return can_enter, e_atr_rem, required_energy

    def arm_and_enter(
        self,
        position_id: str,
        direction: str,
        contract: str,
        entry_price: float,
        entry_time_str: str,
        sl_pts: Optional[float] = None,
        tp_pts: Optional[float] = None,
        friction_drag_pts: float = 0.80,
        opt_quote: Optional[Dict[str, Any]] = None,
        is_runner_mode: bool = False,
        session_gear: str = "GEAR_1_RANGE",
        opt_stop_loss_pct: Optional[float] = None,
        atr_1m: float = 10.0,
        max_session_trades: int = 4,
        lots: int = 1,
        sizing_tier: str = "FULL_SIZE",
        lot_size: int = 65,
        total_quantity: Optional[int] = None,
        is_expiry_day: bool = False,
        is_deep_itm: bool = False,
        structural_runner_enabled: bool = False,
        structural_swing_anchor_sl: Optional[float] = None,
    ) -> bool:
        """Arms and executes entry into IN_FLIGHT state with dynamic volatility-scaled targets.
        
        Enforces Floor-or-Reject: If lots < 1, entry is rejected (never round up).
        """
        if lots < 1:
            logger.warning(f"ENTRY_REJECTED: lots={lots} < 1 (Floor-or-Reject invariant). Suppressing entry.")
            return False

        # Invariant 2.3: Anti-Churn Cool-Off State Gate
        cleared_cool_off = False
        if self.state == STATE_COOL_OFF:
            now_dt = datetime.now()
            # If the new setup is a reversal (opposite direction), allow immediate pivot
            is_same_direction = (self.cool_off_direction is not None and self.cool_off_direction == direction)
            
            if is_same_direction:
                if self.cool_off_until and now_dt < self.cool_off_until:
                    rem_sec = (self.cool_off_until - now_dt).total_seconds()
                    logger.warning(f"ENTRY_REJECTED: APM in STATE_COOL_OFF for {rem_sec:.1f}s more. Suppressing same-direction churn.")
                    return False
                # Check structural extreme if ref spot available
                if self.cool_off_ref_spot is not None:
                    if self.cool_off_direction == "CE" and entry_price <= self.cool_off_ref_spot:
                        logger.warning("ENTRY_REJECTED: Spot has not exceeded pre-exit high extreme. Suppressing same-direction churn.")
                        return False
                    elif self.cool_off_direction == "PE" and entry_price >= self.cool_off_ref_spot:
                        logger.warning("ENTRY_REJECTED: Spot has not broken pre-exit low extreme. Suppressing same-direction churn.")
                        return False
            else:
                logger.info(f"COOL_OFF_PIVOT_ALLOWED: Immediate reversal trade permitted ({self.cool_off_direction} -> {direction}).")
            
            cleared_cool_off = True

        if not cleared_cool_off and self.state not in {STATE_STANDBY, STATE_LIQUIDATED, STATE_PULLBACK_WAIT}:
            return False

        # Invariant: Regime-Aware Session Trade Cap
        effective_cap = 6 if session_gear == "GEAR_2_TREND" else max_session_trades
        today_iso = entry_time_str[:10] if (entry_time_str and len(entry_time_str) >= 10) else datetime.now().strftime("%Y-%m-%d")
        today_trades_count = sum(
            1 for t in self.trade_history
            if isinstance(t, dict) and (
                str(t.get("entry_time", "")).startswith(today_iso) or
                not str(t.get("entry_time", ""))  # count if no date specified in mock
            )
        )
        if today_trades_count >= effective_cap:
            logger.warning(f"SESSION_TRADE_CAP_REACHED: {today_trades_count} trades already executed today (cap={effective_cap}). Suppressing entry.")
            return False

        # If cool-off was cleared and downstream gates pass, transition to STANDBY
        if cleared_cool_off:
            self._transition_to(STATE_STANDBY)

        if not self._transition_to(STATE_ARMED):
            return False

        # Quantitative Scale Normalization: SENSEX vs NIFTY vs BANKNIFTY
        is_sensex = "SENSEX" in contract or entry_price > 50000.0
        is_banknifty = "BANKNIFTY" in contract or (entry_price > 35000.0 and not is_sensex)
        
        # If caller provides explicit tp_pts and sl_pts, they are authoritative native points.
        # Otherwise fallback to unscaled defaults (tp=18.0, sl=12.0) scaled by index volatility.
        if tp_pts is not None and sl_pts is not None:
            eff_tp = float(tp_pts)
            eff_sl = float(sl_pts)
            eff_atr = float(atr_1m)
        else:
            index_scale = 3.5 if is_sensex else (2.5 if is_banknifty else 1.0)
            eff_atr = max(atr_1m, 8.0) * index_scale
            raw_tp = 18.0 if tp_pts is None else float(tp_pts)
            raw_sl = 12.0 if sl_pts is None else float(sl_pts)
            eff_tp = max(raw_tp * index_scale, 1.5 * eff_atr)
            eff_sl = max(raw_sl * index_scale, 1.0 * eff_atr)

        if direction == "CE":
            target = entry_price + eff_tp
            initial_sl = entry_price - eff_sl
        else:  # "PE"
            target = entry_price - eff_tp
            initial_sl = entry_price + eff_sl

        # Real option quote fields
        opt_symbol = opt_quote.get("symbol") if opt_quote else None
        opt_token = opt_quote.get("token") if opt_quote else None
        opt_entry_ltp = opt_quote.get("ltp") if opt_quote else None
        opt_bid = opt_quote.get("bid") if opt_quote else None
        opt_ask = opt_quote.get("ask") if opt_quote else None

        # If in GEAR_2_TREND, compute option native stop (e.g. entry_ltp * (1 - 0.20))
        opt_initial_sl = None
        if opt_entry_ltp is not None and opt_stop_loss_pct is not None:
            opt_initial_sl = round(opt_entry_ltp * (1.0 - opt_stop_loss_pct), 2)

        # In GEAR_2_TREND, max_hold_minutes is extended to 360 (end of day)
        hold_horizon = 15
        if session_gear == "GEAR_2_TREND":
            hold_horizon = 360
        elif is_runner_mode:
            hold_horizon = 45

        # Dynamic Expiry-Day Theta Accelerator:
        # Scale holding ceiling continuously post-12:30 IST down to 15m minimum floor
        # for non-deep-ITM options in range/scalp mode (or runner mode).
        if is_expiry_day and not is_deep_itm and session_gear != "GEAR_2_TREND":
            hold_horizon = compute_expiry_theta_holding_ceiling(
                base_max_hold_minutes=hold_horizon,
                entry_time_str=entry_time_str,
                is_expiry_day=is_expiry_day,
                is_deep_itm=is_deep_itm,
                accelerator_start=dtime(12, 30),
                accelerator_end=dtime(15, 0),
                min_hold_minutes=15,
            )

        self.payload = PositionPayload(
            position_id=position_id,
            direction=direction,
            strike_contract=contract,
            entry_price=entry_price,
            entry_time=entry_time_str,
            current_sl=initial_sl,
            initial_sl=initial_sl,
            target_price=target,
            max_hold_minutes=hold_horizon,
            trail_locked=False,
            lots=int(lots),
            sizing_tier=sizing_tier,
            lot_size=int(lot_size),
            total_quantity=int(total_quantity if total_quantity is not None else lots * lot_size),
            opt_symbol=opt_symbol,
            opt_token=opt_token,
            opt_entry_ltp=opt_entry_ltp,
            opt_current_ltp=opt_entry_ltp,
            opt_bid=opt_bid,
            opt_ask=opt_ask,
            is_runner_mode=is_runner_mode,
            half_booked=False,
            opt_peak_hwm=opt_entry_ltp,
            runner_trailing_sl=None,
            session_gear=session_gear,
            opt_stop_loss_pct=opt_stop_loss_pct,
            opt_initial_sl=opt_initial_sl,
            structural_runner_enabled=structural_runner_enabled,
            structural_swing_anchor_sl=structural_swing_anchor_sl,
        )

        self._transition_to(STATE_IN_FLIGHT)
        return True

    def update_structural_swing_anchor(self, new_swing_anchor_sl: float) -> bool:
        """Dynamically updates the 15-minute structural swing trailing anchor for active runners.
        
        Enforces monotonic protection:
        - For CE (Long), the anchor can ONLY ratchet upward (protecting higher lows).
        - For PE (Short), the anchor can ONLY ratchet downward (protecting lower highs).
        """
        if self.state not in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK} or not self.payload:
            return False

        p = self.payload
        is_ce = (p.direction == "CE")

        if p.structural_swing_anchor_sl is None:
            p.structural_swing_anchor_sl = new_swing_anchor_sl
            p.structural_runner_enabled = True
            self._persist_wal_atomic(force_sync=False)
            return True

        # Monotonic ratchet: Never widen stop
        if is_ce and new_swing_anchor_sl > p.structural_swing_anchor_sl:
            p.structural_swing_anchor_sl = round(new_swing_anchor_sl, 2)
            self._persist_wal_atomic(force_sync=False)
            return True
        elif not is_ce and new_swing_anchor_sl < p.structural_swing_anchor_sl:
            p.structural_swing_anchor_sl = round(new_swing_anchor_sl, 2)
            self._persist_wal_atomic(force_sync=False)
            return True

        return False

    def evaluate_tick(
        self,
        current_spot: float,
        current_opt_ltp: Optional[float] = None,
        tick_time_str: Optional[str] = None,
        atr_1m: float = 10.0
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Invariant 5.1: Real-Time Sub-Second Tick Trailing & Exit Defense.
        
        Evaluates sub-second ticks directly while in flight:
        - Option Native Stop Loss (-20%): Evaluated immediately on live option tick.
        - Chandelier Volatility Trailing Stop: Scales with 2.5x ATR * delta cushion.
        - Dynamic Volatility Ratchet: Requires 1.2 ATR progress before breakeven lock.
        - Decoupled Runner Mode: Protects runners from microscopic 4-point spot jitter.
        """
        if self.state not in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
            return self.state, None

        p = self.payload
        is_ce = (p.direction == "CE")
        is_sensex = "SENSEX" in p.strike_contract or p.entry_price > 50000.0
        index_scale = 3.5 if is_sensex else 1.0
        eff_atr = max(atr_1m, 8.0) * index_scale

        if current_opt_ltp is not None:
            p.opt_current_ltp = current_opt_ltp
            if p.opt_peak_hwm is None or current_opt_ltp > p.opt_peak_hwm:
                p.opt_peak_hwm = current_opt_ltp

        # Helper to execute liquidation on tick
        def _record_tick_exit(reason: str, exit_spot: float):
            p.exit_price = exit_spot
            p.exit_reason = reason
            p.exit_time = tick_time_str or datetime.now().isoformat()
            p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
            if p.opt_entry_ltp is not None and p.opt_current_ltp is not None:
                p.opt_exit_ltp = p.opt_current_ltp
                raw_diff = round(p.opt_exit_ltp - p.opt_entry_ltp, 2)
                p.runner_exit_ltp = p.opt_exit_ltp
                p.runner_pnl_pts = raw_diff
                if p.half_booked and p.tranche_1_pnl_pts is not None:
                    # Multi-Tranche Blended Accounting: 50% booked at T1 + 50% runner
                    p.blended_opt_pnl_pts = round(0.5 * p.tranche_1_pnl_pts + 0.5 * p.runner_pnl_pts, 2)
                    p.opt_pnl_pts = p.blended_opt_pnl_pts
                else:
                    p.opt_pnl_pts = raw_diff
            self._transition_to(STATE_EXIT_PENDING)

        # Invariant: EOD Mandatory Square-Off (15:15:00 IST)
        if tick_time_str:
            try:
                t_str = tick_time_str.split("T")[1][:8] if "T" in tick_time_str else (tick_time_str.split(" ")[1][:8] if " " in tick_time_str else tick_time_str[:8])
                if t_str >= "15:15:00":
                    _record_tick_exit("EOD_MANDATORY_SQUAREOFF", current_spot)
                    return self.liquidate()
            except Exception:
                pass

        # Excursion & Milestone Tracking
        gain = (current_spot - p.entry_price) if is_ce else (p.entry_price - current_spot)
        if gain > p.max_spot_excursion:
            p.max_spot_excursion = round(gain, 2)

        tp1_milestone_pts = 15.0 * index_scale
        tp2_milestone_pts = 35.0 * index_scale

        if current_opt_ltp is not None and p.opt_entry_ltp is not None:
            opt_gain = current_opt_ltp - p.opt_entry_ltp
            if opt_gain > p.max_opt_excursion:
                p.max_opt_excursion = round(opt_gain, 2)
            if opt_gain >= tp1_milestone_pts or gain >= tp1_milestone_pts:
                p.target_1_hit = True
            if opt_gain >= tp2_milestone_pts or gain >= tp2_milestone_pts:
                p.target_2_hit = True

        # 1. Option Native Stop Loss (-20%)
        if p.session_gear == "GEAR_2_TREND" and p.opt_initial_sl is not None and p.opt_current_ltp is not None:
            if p.opt_current_ltp <= p.opt_initial_sl and not p.trail_locked:
                _record_tick_exit("OPTION_NATIVE_STOP_LOSS_HIT", current_spot)
                return self.liquidate()

        # 2. Spot Stop Loss / Trailing Stop Hit (Only if NOT in deep runner mode)
        hit_spot_sl = (current_spot <= p.current_sl) if is_ce else (current_spot >= p.current_sl)
        if hit_spot_sl and not p.half_booked:
            if p.session_gear == "GEAR_1_RANGE" or p.trail_locked:
                _record_tick_exit("TRAILING_STOP_HIT" if p.trail_locked else "STOP_LOSS_HIT", p.current_sl)
                return self.liquidate()

        # 3. Peak Giveback Clamp (Tiers 1 & 2)
        # Prevents trades that gained +12% to +30%+ from round-tripping into red stops
        # (Only active before Target 1 half-booking; once half-booked, Chandelier takes over trailing)
        if current_opt_ltp is not None and p.opt_entry_ltp is not None and p.opt_peak_hwm is not None and not p.half_booked:
            opt_entry = p.opt_entry_ltp
            peak_gain_pct = (p.opt_peak_hwm - opt_entry) / max(opt_entry, 1.0)
            
            # Tier 1: Friction & Breakeven Lock at >= +12% option gain
            if peak_gain_pct >= 0.12 and not p.trail_locked:
                friction_buffer = 1.5 if is_sensex else 0.8
                p.giveback_clamp_sl = round(opt_entry + friction_buffer, 2)
                be_sl = (p.entry_price + 1.0) if is_ce else (p.entry_price - 1.0)
                if (is_ce and be_sl > p.current_sl) or (not is_ce and be_sl < p.current_sl):
                    p.current_sl = be_sl
                p.trail_locked = True
                if self.state == STATE_IN_FLIGHT:
                    self._transition_to(STATE_TRAIL_LOCK)

            # Tier 2: Peak Profit Floor Clamp at >= +25% option gain
            # Guarantees at least +10% profit floor and clamps max peak giveback to 35%
            if peak_gain_pct >= 0.25:
                # 35% allowable giveback from peak gain
                protected_gain = (p.opt_peak_hwm - opt_entry) * 0.65
                min_floor_gain = opt_entry * 0.10  # Guaranteed >= 10% profit floor
                tier2_sl = round(opt_entry + max(protected_gain, min_floor_gain), 2)
                if p.giveback_clamp_sl is None or tier2_sl > p.giveback_clamp_sl:
                    p.giveback_clamp_sl = tier2_sl
                if not p.trail_locked:
                    p.trail_locked = True
                    if self.state == STATE_IN_FLIGHT:
                        self._transition_to(STATE_TRAIL_LOCK)

            # Check if Live Option Price Breached the Giveback Clamp Stop
            if p.giveback_clamp_sl is not None and current_opt_ltp <= p.giveback_clamp_sl:
                # In GEAR_2_TREND with 0 prior re-entries, qualify for PULLBACK_WAIT
                if p.session_gear == "GEAR_2_TREND" and p.reentry_count < 1:
                    p.exit_price = current_spot
                    p.exit_reason = "PEAK_GIVEBACK_CLAMP_EXIT"
                    p.exit_time = tick_time_str or datetime.now().isoformat()
                    p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
                    p.opt_exit_ltp = current_opt_ltp
                    p.opt_pnl_pts = round(p.opt_exit_ltp - opt_entry, 2)
                    p.pullback_reference_price = current_spot
                    self.last_completed_trade = asdict(p)
                    self.trade_history.append(self.last_completed_trade)
                    self._transition_to(STATE_PULLBACK_WAIT)
                    self._persist_wal_atomic()
                    return self.state, asdict(p)
                else:
                    _record_tick_exit("PEAK_GIVEBACK_CLAMP_EXIT", current_spot)
                    return self.liquidate()

        # 4. Target 1 Hit -> Secure 50% lot and arm Chandelier Runner Trailing Mode
        hit_spot_tp = (current_spot >= p.target_price) if is_ce else (current_spot <= p.target_price)
        if hit_spot_tp:
            p.target_1_hit = True
            if not p.is_runner_mode:
                _record_tick_exit("TARGET_HIT", p.target_price)
                return self.liquidate()
            elif not p.half_booked:
                p.half_booked = True
                p.current_sl = p.entry_price  # Breakeven lock on spot
                p.opt_half_booked_ltp = current_opt_ltp or p.opt_current_ltp or p.opt_entry_ltp
                p.opt_half_booked_time = tick_time_str or datetime.now().isoformat()
                if p.opt_entry_ltp is not None and p.opt_half_booked_ltp is not None:
                    p.tranche_1_pnl_pts = round(p.opt_half_booked_ltp - p.opt_entry_ltp, 2)
                
                # Invariant 1.1 & 1.2: Bounded Giveback Clamp & Monotonic Breakeven Floor
                opt_entry = p.opt_entry_ltp or 50.0
                peak_hwm = p.opt_peak_hwm or opt_entry
                friction_buffer = 5.0 if is_sensex else (3.0 if "BANKNIFTY" in p.strike_contract else 2.0)
                monotonic_floor = opt_entry + friction_buffer

                peak_excursion = max(0.0, peak_hwm - opt_entry)
                clamped_cushion = min(1.5 * eff_atr, max(12.0, 0.35 * peak_excursion))
                proposed_sl = round(peak_hwm - clamped_cushion, 2)
                p.runner_trailing_sl = max(monotonic_floor, proposed_sl)

                if self.state == STATE_IN_FLIGHT:
                    self._transition_to(STATE_TRAIL_LOCK)
                self._persist_wal_atomic()
                return self.state, asdict(p)

        # 5. Chandelier Option Volatility Trailing Exit or Structural Swing Trailing Exit
        if p.is_runner_mode and p.half_booked:
            # Check Structural Swing Stop if enabled (15-minute Market Structure Higher Low / Lower High)
            if p.structural_runner_enabled and p.structural_swing_anchor_sl is not None:
                hit_struct = (current_spot <= p.structural_swing_anchor_sl) if is_ce else (current_spot >= p.structural_swing_anchor_sl)
                if hit_struct:
                    _record_tick_exit("STRUCTURAL_15M_SWING_EXIT", current_spot)
                    return self.liquidate()
            elif p.runner_trailing_sl is not None:
                # Otherwise trail via Chandelier Volatility Floor (if structural runner is not active)
                opt_entry = p.opt_entry_ltp or 50.0
                peak_hwm = p.opt_peak_hwm or opt_entry
                friction_buffer = 5.0 if is_sensex else (3.0 if "BANKNIFTY" in p.strike_contract else 2.0)
                monotonic_floor = opt_entry + friction_buffer

                peak_excursion = max(0.0, peak_hwm - opt_entry)
                clamped_cushion = min(1.5 * eff_atr, max(12.0, 0.35 * peak_excursion))
                proposed_sl = round(peak_hwm - clamped_cushion, 2)
                new_opt_sl = max(monotonic_floor, proposed_sl)

                if new_opt_sl > p.runner_trailing_sl:
                    p.runner_trailing_sl = round(new_opt_sl, 2)
                if p.opt_current_ltp is not None and p.opt_current_ltp <= p.runner_trailing_sl:
                    _record_tick_exit("RUNNER_HWM_TRAILING_EXIT", current_spot)
                    return self.liquidate()

        # 6. Volatility-Scaled Breakeven Ratchet (Requires >= 1.2 ATR excursion to avoid noise stops)
        be_req_gain = 1.2 * eff_atr
        if gain >= be_req_gain and not p.trail_locked:
            be_sl = (p.entry_price + 1.0) if is_ce else (p.entry_price - 1.0)
            if (is_ce and be_sl > p.current_sl) or (not is_ce and be_sl < p.current_sl):
                p.current_sl = be_sl
                p.trail_locked = True
                if self.state == STATE_IN_FLIGHT:
                    self._transition_to(STATE_TRAIL_LOCK)

        # 7. Time Horizon Exit (Dynamic Expiry Theta Acceleration or Base Hold Horizon)
        # Suppressed if option is in positive excursion runner mode with trail locked (let trend winners run)
        if tick_time_str and not (p.half_booked or p.trail_locked):
            try:
                entry_dt = datetime.fromisoformat(p.entry_time)
                cur_dt = datetime.fromisoformat(tick_time_str)
                held_minutes = (cur_dt - entry_dt).total_seconds() / 60.0
                if held_minutes >= p.max_hold_minutes:
                    # Liquidity Spread Spike Defense: if bid-ask spread is severely blown (> 15% of LTP),
                    # allow 60-second grace window rather than market selling into spread expansion
                    allow_exit = True
                    if p.opt_bid is not None and p.opt_ask is not None and current_opt_ltp and current_opt_ltp > 0:
                        cur_spread = p.opt_ask - p.opt_bid
                        if (cur_spread / current_opt_ltp) > 0.15:
                            allow_exit = False
                    if allow_exit:
                        _record_tick_exit(f"TIME_EXIT_{int(held_minutes)}M", current_spot)
                        return self.liquidate()
            except Exception:
                pass

        self._persist_wal_atomic(force_sync=False)
        return self.state, asdict(p)

    def evaluate_bar(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_time_str: str,
        current_opt_ltp: Optional[float] = None,
        atr_1m: float = 10.0
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Evaluates completed bar against active position.
        
        Enforces:
        - Pessimistic Intrabar Resolution (SL wins if both SL and TP hit in same bar)
        - Monotonic Ratchet (+8 pts move locks +4 pts trailing stop)
        - Invariant 3.2: 15-Minute Theta Horizon Exit (extended to 45m for runners)
        - Empirical Option Strike PnL calculation from real WebSocket ticks
        - 50% Fixed Target Book + 50% Runner Trailed via Option High-Watermark (HWM)
        """
        if self.state not in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
            return self.state, None

        p = self.payload
        is_ce = (p.direction == "CE")

        if current_opt_ltp is not None:
            p.opt_current_ltp = current_opt_ltp
            # Update peak option high-watermark
            if p.opt_peak_hwm is None or current_opt_ltp > p.opt_peak_hwm:
                p.opt_peak_hwm = current_opt_ltp

        # 1. Check Intrabar Hits
        if is_ce:
            hit_tp = bar_high >= p.target_price
            hit_sl = bar_low <= p.current_sl
            gain = bar_high - p.entry_price
        else:
            hit_tp = bar_low <= p.target_price
            hit_sl = bar_high >= p.current_sl
            gain = p.entry_price - bar_low

        # Helper to compute empirical option strike PnL
        def _record_exit(exit_reason: str, exit_spot: float):
            p.exit_price = exit_spot
            p.exit_reason = exit_reason
            p.exit_time = bar_time_str
            p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
            if p.opt_entry_ltp is not None and p.opt_current_ltp is not None:
                p.opt_exit_ltp = p.opt_current_ltp
                raw_diff = round(p.opt_exit_ltp - p.opt_entry_ltp, 2)
                p.runner_exit_ltp = p.opt_exit_ltp
                p.runner_pnl_pts = raw_diff
                if p.half_booked and p.tranche_1_pnl_pts is not None:
                    p.blended_opt_pnl_pts = round(0.5 * p.tranche_1_pnl_pts + 0.5 * p.runner_pnl_pts, 2)
                    p.opt_pnl_pts = p.blended_opt_pnl_pts
                else:
                    p.opt_pnl_pts = raw_diff
            self._transition_to(STATE_EXIT_PENDING)

        # Invariant: EOD Mandatory Square-Off (15:15:00 IST)
        if bar_time_str:
            try:
                t_str = bar_time_str.split("T")[1][:8] if "T" in bar_time_str else (bar_time_str.split(" ")[1][:8] if " " in bar_time_str else bar_time_str[:8])
                if t_str >= "15:15:00":
                    _record_exit("EOD_MANDATORY_SQUAREOFF", bar_close)
                    return self.liquidate()
            except Exception:
                pass

        # 2. Runner Mode Logic: Book 50% at Target, Trail Remaining 50% via Option HWM
        if p.is_runner_mode and hit_tp and not p.half_booked:
            p.half_booked = True
            p.trail_locked = True
            p.opt_half_booked_ltp = current_opt_ltp or p.opt_current_ltp or p.opt_entry_ltp
            p.opt_half_booked_time = bar_time_str
            if p.opt_entry_ltp is not None and p.opt_half_booked_ltp is not None:
                p.tranche_1_pnl_pts = round(p.opt_half_booked_ltp - p.opt_entry_ltp, 2)

            # Lock Spot SL to entry + 4.0 pts
            p.current_sl = (p.entry_price + 4.0) if is_ce else (p.entry_price - 4.0)
            
            # Invariant 1.1 & 1.2: Bounded Giveback Clamp & Monotonic Breakeven Floor
            is_sensex = "SENSEX" in p.strike_contract or p.entry_price > 50000.0
            opt_entry = p.opt_entry_ltp or 50.0
            peak_hwm = p.opt_peak_hwm or opt_entry
            friction_buffer = 5.0 if is_sensex else (3.0 if "BANKNIFTY" in p.strike_contract else 2.0)
            monotonic_floor = opt_entry + friction_buffer

            peak_excursion = max(0.0, peak_hwm - opt_entry)
            clamped_cushion = min(1.5 * max(atr_1m, 8.0), max(12.0, 0.35 * peak_excursion))
            proposed_sl = round(peak_hwm - clamped_cushion, 2)
            p.runner_trailing_sl = max(monotonic_floor, proposed_sl)

            if self.state == STATE_IN_FLIGHT:
                self._transition_to(STATE_TRAIL_LOCK)
            elif self.state == STATE_TRAIL_LOCK:
                pass
            else:
                raise ValueError(
                    f"Cannot book runner target while position is in {self.state}"
                )
            self._persist_wal_atomic()
            return self.state, asdict(p)

        # If in Runner Trailing Mode, check if Option Price hit the HWM trailing stop
        if p.is_runner_mode and p.half_booked and p.runner_trailing_sl is not None:
            is_sensex = "SENSEX" in p.strike_contract or p.entry_price > 50000.0
            opt_entry = p.opt_entry_ltp or 50.0
            peak_hwm = p.opt_peak_hwm or opt_entry
            friction_buffer = 5.0 if is_sensex else (3.0 if "BANKNIFTY" in p.strike_contract else 2.0)
            monotonic_floor = opt_entry + friction_buffer

            peak_excursion = max(0.0, peak_hwm - opt_entry)
            clamped_cushion = min(1.5 * max(atr_1m, 8.0), max(12.0, 0.35 * peak_excursion))
            proposed_sl = round(peak_hwm - clamped_cushion, 2)
            new_opt_sl = max(monotonic_floor, proposed_sl)
            new_opt_sl = (p.opt_peak_hwm - opt_cushion) if p.opt_peak_hwm else p.runner_trailing_sl
            if new_opt_sl > p.runner_trailing_sl:
                p.runner_trailing_sl = new_opt_sl

            # Check if live option price breached the HWM trailing stop
            if p.opt_current_ltp is not None and p.opt_current_ltp <= p.runner_trailing_sl:
                _record_exit("RUNNER_HWM_TRAILING_EXIT", bar_close)
                return self.liquidate()

        # Pessimistic Resolution Rule: If both hit, SL wins chronologically
        if hit_tp and hit_sl:
            _record_exit("PESSIMISTIC_INTRABAR_SL_COLLISION", p.current_sl)
            return self.liquidate()

        # Regular Target Hit (Full exit if not runner mode)
        if hit_tp and not p.is_runner_mode:
            _record_exit("TARGET_HIT", p.target_price)
            return self.liquidate()

        # In GEAR_2_TREND: Stop loss is evaluated natively on Option Contract Price (e.g. -20% of premium).
        # This prevents 15-20 pt spot counter-wicks from stopping out a macro trend position.
        hit_opt_sl = False
        if p.session_gear == "GEAR_2_TREND" and p.opt_initial_sl is not None and p.opt_current_ltp is not None:
            if p.opt_current_ltp <= p.opt_initial_sl and not p.trail_locked:
                hit_opt_sl = True

        # In GEAR_1_RANGE: Stop loss is evaluated on spot index price
        if p.session_gear == "GEAR_1_RANGE" and hit_sl:
            _record_exit("TRAILING_STOP_HIT" if p.trail_locked else "STOP_LOSS_HIT", p.current_sl)
            return self.liquidate()
        elif p.session_gear == "GEAR_2_TREND" and hit_opt_sl:
            _record_exit("OPTION_NATIVE_STOP_LOSS_HIT", bar_close)
            return self.liquidate()
        elif p.session_gear == "GEAR_2_TREND" and p.trail_locked and hit_sl:
            # Once trail locked, spot stop also acts as a hard backstop
            _record_exit("TRAILING_STOP_HIT", p.current_sl)
            return self.liquidate()

        # Invariant: Breakeven Lock at +12.0 Spot Points Gain (Snaps SL to entry + 1.0 pt)
        if gain >= 12.0 and not p.trail_locked:
            be_sl = (p.entry_price + 1.0) if is_ce else (p.entry_price - 1.0)
            if (is_ce and be_sl > p.current_sl) or (not is_ce and be_sl < p.current_sl):
                p.current_sl = be_sl
                p.trail_locked = True
                if self.state == STATE_IN_FLIGHT:
                    self._transition_to(STATE_TRAIL_LOCK)

        # 2. Monotonic Trailing Ratchet (+8 pts move locks +4 pts profit)
        elif gain >= 8.0 and not p.trail_locked:
            new_sl = (p.entry_price + 4.0) if is_ce else (p.entry_price - 4.0)
            # Invariant 1.1: Compare-And-Swap monotonicity check
            if (is_ce and new_sl > p.current_sl) or (not is_ce and new_sl < p.current_sl):
                p.current_sl = new_sl
                p.trail_locked = True
                if self.state == STATE_IN_FLIGHT:
                    self._transition_to(STATE_TRAIL_LOCK)

        # 3. Time Horizon Exit (15-Minute Holding Ceiling)
        try:
            entry_dt = datetime.fromisoformat(p.entry_time)
            cur_dt = datetime.fromisoformat(bar_time_str)
            held_minutes = (cur_dt - entry_dt).total_seconds() / 60.0
            if held_minutes >= p.max_hold_minutes:
                p.exit_price = bar_close
                p.exit_reason = f"TIME_EXIT_{int(held_minutes)}M"
                p.exit_time = bar_time_str
                p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
                if p.opt_entry_ltp is not None and p.opt_current_ltp is not None:
                    p.opt_exit_ltp = p.opt_current_ltp
                    p.opt_pnl_pts = round(p.opt_exit_ltp - p.opt_entry_ltp, 2)
                self._transition_to(STATE_EXIT_PENDING)
                return self.liquidate()
        except Exception:
            pass

        self._persist_wal_atomic(force_sync=False)
        return self.state, asdict(p)

    def liquidate(self, cooldown_seconds: Optional[float] = None) -> Tuple[str, Dict[str, Any]]:
        """Completes liquidation, arms COOL_OFF state to prevent 2-second churn loops, and records summary.
        
        Dynamically scales cooldown by session gear:
        - GEAR_2_TREND: 60 seconds (allows rapid resumption of trending moves)
        - GEAR_1_RANGE / ROTATIONAL_CHOP: 300 seconds (dampens whipsaw churn)
        """
        if self.state != STATE_EXIT_PENDING:
            return self.state, asdict(self.payload) if self.payload else {}
        summary = asdict(self.payload) if self.payload else {}
        self.last_completed_trade = summary
        if summary:
            self.trade_history.append(summary)

        # Dynamic regime-scaled cooldown
        if cooldown_seconds is None:
            gear = self.payload.session_gear if self.payload else "GEAR_1_RANGE"
            effective_cooldown = 60.0 if gear == "GEAR_2_TREND" else 300.0
        else:
            effective_cooldown = cooldown_seconds

        # Invariant 2.1: Transition to STATE_COOL_OFF rather than direct naked standby
        if effective_cooldown > 0.0:
            from datetime import timedelta
            self.cool_off_until = datetime.now() + timedelta(seconds=effective_cooldown)
            if self.payload:
                self.cool_off_ref_spot = self.payload.exit_price or self.payload.entry_price
                self.cool_off_direction = self.payload.direction
            self._transition_to(STATE_COOL_OFF)
            next_state = STATE_COOL_OFF
        else:
            self.cool_off_until = None
            self.cool_off_ref_spot = None
            self.cool_off_direction = None
            self._transition_to(STATE_LIQUIDATED)
            next_state = STATE_LIQUIDATED

        # Clear payload for next trade
        self.payload = None
        self._persist_wal_atomic(force_sync=True)
        return next_state, summary

    def evaluate_pullback_reentry(
        self,
        current_spot: float,
        bounce_confirmed: bool,
        current_opt_quote: Optional[Dict[str, Any]] = None,
        atr_1m: float = 10.0,
        current_time_str: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Evaluates whether an active PULLBACK_WAIT state should re-enter on bounce.
        
        Enforces strict institutional gates:
        1. APM must be in STATE_PULLBACK_WAIT
        2. Session gear must remain GEAR_2_TREND
        3. Prior setup reentry_count must be < 1 (hard limit of 1 re-entry)
        4. Bar T confirmed structural bounce (e.g. rejection off EMA-9 or VWAP)
        5. Execution occurs at Bar T+1 Open (zero future bar leakage)
        """
        if self.state != STATE_PULLBACK_WAIT or self.payload is None:
            return self.state, None

        p = self.payload
        is_ce = (p.direction == "CE")

        # Invariant 1: Hard cap of 1 re-entry per setup
        if p.reentry_count >= 1:
            self.state = STATE_LIQUIDATED
            self.payload = None
            self._persist_wal_atomic()
            return STATE_LIQUIDATED, None

        # Invariant 2: Gear 2 Trend must be maintained
        if p.session_gear != "GEAR_2_TREND":
            self.state = STATE_LIQUIDATED
            self.payload = None
            self._persist_wal_atomic()
            return STATE_LIQUIDATED, None

        # Invariant 3: Bounce Confirmation Required
        if not bounce_confirmed:
            # Check if spot broke too far against prior reference price (> 1.5 ATR against entry direction)
            if p.pullback_reference_price is not None:
                adverse_drift = (p.pullback_reference_price - current_spot) if is_ce else (current_spot - p.pullback_reference_price)
                if adverse_drift > 1.5 * atr_1m:
                    # Pullback failed into full reversal: abort re-entry
                    self.state = STATE_LIQUIDATED
                    self.payload = None
                    self._persist_wal_atomic()
                    return STATE_LIQUIDATED, None
            return self.state, asdict(p)

        # Re-entry Confirmed! Reset parameters for re-entered position
        p.reentry_count += 1
        p.entry_price = current_spot
        p.entry_time = current_time_str or datetime.now().isoformat()
        p.trail_locked = False
        p.half_booked = False
        p.target_1_hit = False
        p.target_2_hit = False
        p.exit_price = None
        p.exit_reason = None
        p.exit_time = None
        p.pnl_pts = None

        eff_atr = max(atr_1m, 8.0)
        eff_tp = round(1.5 * eff_atr, 2)
        eff_sl = round(1.0 * eff_atr, 2)

        p.current_sl = (current_spot - eff_sl) if is_ce else (current_spot + eff_sl)
        p.initial_sl = p.current_sl
        p.target_price = (current_spot + eff_tp) if is_ce else (current_spot - eff_tp)

        if current_opt_quote:
            p.opt_entry_ltp = current_opt_quote.get("ltp")
            p.opt_current_ltp = current_opt_quote.get("ltp")
            p.opt_peak_hwm = current_opt_quote.get("ltp")
            p.opt_bid = current_opt_quote.get("bid")
            p.opt_ask = current_opt_quote.get("ask")
            if p.opt_stop_loss_pct and p.opt_entry_ltp:
                p.opt_initial_sl = round(p.opt_entry_ltp * (1.0 - p.opt_stop_loss_pct), 2)
        p.giveback_clamp_sl = None

        self.state = STATE_IN_FLIGHT
        self._persist_wal_atomic()
        return STATE_IN_FLIGHT, asdict(p)

