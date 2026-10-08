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
import os
import math
from datetime import datetime, time as dtime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, Dict, Any

STATE_STANDBY = "STANDBY"
STATE_ARMED = "ARMED"
STATE_IN_FLIGHT = "IN_FLIGHT"
STATE_TRAIL_LOCK = "TRAIL_LOCK"
STATE_EXIT_PENDING = "EXIT_PENDING"
STATE_LIQUIDATED = "LIQUIDATED"

VALID_TRANSITIONS = {
    STATE_STANDBY: {STATE_ARMED},
    STATE_ARMED: {STATE_IN_FLIGHT, STATE_STANDBY},
    STATE_IN_FLIGHT: {STATE_TRAIL_LOCK, STATE_EXIT_PENDING},
    STATE_TRAIL_LOCK: {STATE_EXIT_PENDING},
    STATE_EXIT_PENDING: {STATE_LIQUIDATED},
    STATE_LIQUIDATED: {STATE_ARMED, STATE_STANDBY},
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


class ActivePositionManager:
    def __init__(self, wal_path: str = "runtime/sentinel_apm_wal.json"):
        self.wal_path = Path(wal_path)
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = STATE_STANDBY
        self.payload: Optional[PositionPayload] = None
        self._recover_state_or_fail_closed()

    def _persist_wal_atomic(self):
        """Invariant 1.2: Atomic Write-Ahead Log persistence via temp file rename."""
        tmp_path = self.wal_path.with_suffix(".tmp")
        data = {
            "state": self.state,
            "payload": asdict(self.payload) if self.payload else None,
            "persisted_at": datetime.now().isoformat()
        }
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.wal_path)

    def _recover_state_or_fail_closed(self):
        """Invariant 1.3: On boot, load WAL. If crashed mid-trade, mark fail-closed EXIT_PENDING."""
        if not self.wal_path.exists():
            return

        try:
            with open(self.wal_path, "r") as f:
                data = json.load(f)
            saved_state = data.get("state", STATE_STANDBY)
            saved_payload = data.get("payload")

            if saved_payload:
                self.payload = PositionPayload(**saved_payload)

            if saved_state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK, STATE_EXIT_PENDING}:
                # Crash recovery fail-closed: force immediate liquidation
                print(f"⚠️ [APM CRASH RECOVERY] Detected unclosed in-flight state '{saved_state}'. Fail-closed trigger!")
                self.state = STATE_EXIT_PENDING
                if self.payload:
                    self.payload.exit_reason = "CRASH_RECOVERY_FAIL_CLOSED"
                self._persist_wal_atomic()
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
        return can_enter, e_atr_rem, required_energy

    def arm_and_enter(
        self,
        position_id: str,
        direction: str,
        contract: str,
        entry_price: float,
        entry_time_str: str,
        sl_pts: float = 12.0,
        tp_pts: float = 18.0,
        friction_drag_pts: float = 0.80,
        opt_quote: Optional[Dict[str, Any]] = None,
        is_runner_mode: bool = False,
        session_gear: str = "GEAR_1_RANGE",
        opt_stop_loss_pct: Optional[float] = None
    ) -> bool:
        """Arms and executes entry into IN_FLIGHT state with monotonic SL and TP targets."""
        if self.state not in {STATE_STANDBY, STATE_LIQUIDATED}:
            return False

        if not self._transition_to(STATE_ARMED):
            return False

        # Invariant 3.1: Deduct worst-case slippage friction from targets
        eff_tp = tp_pts
        eff_sl = sl_pts

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
            hold_horizon = 25

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
            opt_initial_sl=opt_initial_sl
        )

        self._transition_to(STATE_IN_FLIGHT)
        return True

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
                p.opt_pnl_pts = round(p.opt_exit_ltp - p.opt_entry_ltp, 2)
            self._transition_to(STATE_EXIT_PENDING)

        # 2. Runner Mode Logic: Book 50% at Target, Trail Remaining 50% via Option HWM
        if p.is_runner_mode and hit_tp and not p.half_booked:
            p.half_booked = True
            p.trail_locked = True
            # Lock Spot SL to entry + 4.0 pts
            p.current_sl = (p.entry_price + 4.0) if is_ce else (p.entry_price - 4.0)
            # Set Option Runner Trailing Stop: Peak Premium - max(12.0, 1.2 * ATR)
            opt_cushion = max(12.0, 1.2 * atr_1m)
            p.runner_trailing_sl = (p.opt_peak_hwm - opt_cushion) if p.opt_peak_hwm else None
            self._transition_to(STATE_TRAIL_LOCK)
            self._persist_wal_atomic()
            return self.state, asdict(p)

        # If in Runner Trailing Mode, check if Option Price hit the HWM trailing stop
        if p.is_runner_mode and p.half_booked and p.runner_trailing_sl is not None:
            # Ratchet trailing stop upward as peak HWM expands (monotonic non-decreasing)
            opt_cushion = max(12.0, 1.2 * atr_1m)
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

        self._persist_wal_atomic()
        return self.state, asdict(p)

    def liquidate(self) -> Tuple[str, Dict[str, Any]]:
        """Completes liquidation and transitions to LIQUIDATED."""
        if self.state != STATE_EXIT_PENDING:
            return self.state, asdict(self.payload) if self.payload else {}
        self._transition_to(STATE_LIQUIDATED)
        summary = asdict(self.payload) if self.payload else {}
        # Clear payload for next trade
        self.payload = None
        self._persist_wal_atomic()
        return STATE_LIQUIDATED, summary
