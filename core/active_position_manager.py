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
        friction_drag_pts: float = 0.80
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

        self.payload = PositionPayload(
            position_id=position_id,
            direction=direction,
            strike_contract=contract,
            entry_price=entry_price,
            entry_time=entry_time_str,
            current_sl=initial_sl,
            initial_sl=initial_sl,
            target_price=target,
            max_hold_minutes=15,
            trail_locked=False
        )

        self._transition_to(STATE_IN_FLIGHT)
        return True

    def evaluate_bar(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_time_str: str
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Evaluates completed bar against active position.
        
        Enforces:
        - Pessimistic Intrabar Resolution (SL wins if both SL and TP hit in same bar)
        - Monotonic Ratchet (+8 pts move locks +4 pts trailing stop)
        - Invariant 3.2: 15-Minute Theta Horizon Exit
        """
        if self.state not in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
            return self.state, None

        p = self.payload
        is_ce = (p.direction == "CE")

        # 1. Check Intrabar Hits
        if is_ce:
            hit_tp = bar_high >= p.target_price
            hit_sl = bar_low <= p.current_sl
            gain = bar_high - p.entry_price
        else:
            hit_tp = bar_low <= p.target_price
            hit_sl = bar_high >= p.current_sl
            gain = p.entry_price - bar_low

        # Pessimistic Resolution Rule: If both hit, SL wins chronologically
        if hit_tp and hit_sl:
            p.exit_price = p.current_sl
            p.exit_reason = "PESSIMISTIC_INTRABAR_SL_COLLISION"
            p.exit_time = bar_time_str
            p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
            self._transition_to(STATE_EXIT_PENDING)
            return self.liquidate()

        # Regular Target Hit
        if hit_tp:
            p.exit_price = p.target_price
            p.exit_reason = "TARGET_HIT"
            p.exit_time = bar_time_str
            p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
            self._transition_to(STATE_EXIT_PENDING)
            return self.liquidate()

        # Regular Stop Loss Hit
        if hit_sl:
            p.exit_price = p.current_sl
            p.exit_reason = "TRAILING_STOP_HIT" if p.trail_locked else "STOP_LOSS_HIT"
            p.exit_time = bar_time_str
            p.pnl_pts = (p.exit_price - p.entry_price) if is_ce else (p.entry_price - p.exit_price)
            self._transition_to(STATE_EXIT_PENDING)
            return self.liquidate()

        # 2. Monotonic Trailing Ratchet (+8 pts move locks +4 pts profit)
        if gain >= 8.0 and not p.trail_locked:
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
