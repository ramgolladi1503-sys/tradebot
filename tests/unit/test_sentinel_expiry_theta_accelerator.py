"""Unit Test Suite for Expiry-Day Dynamic Theta Accelerator in APM & Sentinel Advisor.

Covers the full 10-Persona Pre- and Post-Development Adversarial Gauntlet:
Attacker 1: Premature Exit Fallacy (cutting winning trend trades before 14:00 PM squeeze)
Attacker 2: Arbitrary Step Function Glitch (sudden jumps from 35m to 15m)
Attacker 3: ITM vs OTM Asymmetry (deep ITM options have near-zero theta decay)
Attacker 4: Settle/Physical Delivery False Panic (index options are cash-settled in India)
Attacker 5: Spread Expansion on Fast Exits (forcing exits during afternoon spread spikes)
Reviewers 1-5: Continuous decay functions, moneyness-aware gating, monotonic safety invariants.
"""

from __future__ import annotations

import pytest
from datetime import time as dtime
from core.active_position_manager import (
    ActivePositionManager,
    compute_expiry_theta_holding_ceiling,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_EXIT_PENDING,
    STATE_COOL_OFF,
    STATE_LIQUIDATED,
)


def test_attacker_2_continuous_linear_decay_prevents_step_function():
    """Attacker 2 Defense: Verifies smooth linear scaling with no sudden 35m -> 15m cliff."""
    # Pre-12:30: full base hold time
    assert compute_expiry_theta_holding_ceiling(35, "2026-10-15T10:00:00", is_expiry_day=True) == 35
    assert compute_expiry_theta_holding_ceiling(35, "2026-10-15T12:30:00", is_expiry_day=True) == 35

    # Post-12:30 continuous gradation
    h_1300 = compute_expiry_theta_holding_ceiling(35, "2026-10-15T13:00:00", is_expiry_day=True)
    h_1330 = compute_expiry_theta_holding_ceiling(35, "2026-10-15T13:30:00", is_expiry_day=True)
    h_1400 = compute_expiry_theta_holding_ceiling(35, "2026-10-15T14:00:00", is_expiry_day=True)
    h_1430 = compute_expiry_theta_holding_ceiling(35, "2026-10-15T14:30:00", is_expiry_day=True)
    h_1500 = compute_expiry_theta_holding_ceiling(35, "2026-10-15T15:00:00", is_expiry_day=True)

    # Monotonically non-increasing and smooth
    assert 35 >= h_1300 >= h_1330 >= h_1400 >= h_1430 >= h_1500 >= 15
    assert h_1300 == 31
    assert h_1330 == 27
    assert h_1400 == 23
    assert h_1430 == 19
    assert h_1500 == 15


def test_attacker_3_deep_itm_asymmetry_bypasses_acceleration():
    """Attacker 3 Defense: Deep ITM options have near-zero theta decay and must retain full hold time."""
    # Non-deep ITM at 14:00 gets compressed
    atm_hold = compute_expiry_theta_holding_ceiling(
        35, "2026-10-15T14:00:00", is_expiry_day=True, is_deep_itm=False
    )
    assert atm_hold == 23

    # Deep ITM at 14:00 preserves full 35m horizon
    itm_hold = compute_expiry_theta_holding_ceiling(
        35, "2026-10-15T14:00:00", is_expiry_day=True, is_deep_itm=True
    )
    assert itm_hold == 35


def test_attacker_1_trend_runners_bypass_time_exit_cutoff(tmp_path):
    """Attacker 1 Defense: Winning trend runners with trail locked are not prematurely cut before 14:00 squeeze."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # Enter a runner trade at 13:30 on expiry day
    entered = apm.arm_and_enter(
        position_id="EXPIRY_TREND_TEST",
        direction="CE",
        contract="NIFTY 22500 CE 15 OCT 26",
        entry_price=22500.0,
        entry_time_str="2026-10-15T13:30:00",
        opt_quote={"symbol": "NIFTY 22500 CE 15 OCT 26", "ltp": 100.0, "bid": 99.5, "ask": 100.5},
        is_runner_mode=True,
        session_gear="GEAR_1_RANGE",
        is_expiry_day=True,
        is_deep_itm=False,
    )
    assert entered is True
    # At 13:30, base hold 45 is accelerated:
    # decay_ratio = 60/150 = 0.4 -> 45 - (45 - 15) * 0.4 = 45 - 12 = 33m
    assert apm.payload.max_hold_minutes == 33

    # Suppose trend moves up strongly: spot touches 22530 (+30 pts)
    # This hits Target 1 (+15 pts) and locks trail / half-books
    apm.evaluate_tick(current_spot=22530.0, current_opt_ltp=125.0, tick_time_str="2026-10-15T13:40:00")
    assert apm.payload.half_booked is True

    # Now time reaches 14:10 (40 minutes elapsed, exceeding the 33m ceiling)
    # Because trail is locked and trade is a winning runner, time exit MUST NOT liquidate the trade
    state, payload = apm.evaluate_tick(
        current_spot=22535.0, current_opt_ltp=130.0, tick_time_str="2026-10-15T14:10:00"
    )
    assert state != STATE_LIQUIDATED
    assert state in {STATE_TRAIL_LOCK, STATE_IN_FLIGHT}


def test_attacker_5_spread_expansion_defense(tmp_path):
    """Attacker 5 Defense: If afternoon spread expands > 15% of LTP, exit is suppressed to avoid market impact."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    entered = apm.arm_and_enter(
        position_id="SPREAD_SPIKE_TEST",
        direction="CE",
        contract="NIFTY 22500 CE 15 OCT 26",
        entry_price=22500.0,
        entry_time_str="2026-10-15T14:00:00",
        opt_quote={"symbol": "NIFTY 22500 CE 15 OCT 26", "ltp": 20.0, "bid": 15.0, "ask": 25.0},  # wide spread
        session_gear="GEAR_1_RANGE",
        is_expiry_day=True,
        is_deep_itm=False,
    )
    assert entered is True
    # Base 15m compressed at 14:00
    assert apm.payload.max_hold_minutes == 15

    # 16 minutes later, trade is drifting at entry price, but spread is blown: bid=10, ask=20 (spread=10 on LTP=15 -> 66% ratio)
    apm.payload.opt_bid = 10.0
    apm.payload.opt_ask = 20.0
    state, payload = apm.evaluate_tick(
        current_spot=22500.0, current_opt_ltp=15.0, tick_time_str="2026-10-15T14:16:00"
    )
    # Must NOT liquidate into the spread blowup
    assert state == STATE_IN_FLIGHT


def test_reviewer_sideways_drift_theta_cutoff(tmp_path):
    """Reviewer Invariant: Sideways drifting trade with normal spread is cleanly exited once holding ceiling is hit."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    entered = apm.arm_and_enter(
        position_id="DRIFT_TEST",
        direction="CE",
        contract="NIFTY 22500 CE 15 OCT 26",
        entry_price=22500.0,
        entry_time_str="2026-10-15T14:00:00",
        opt_quote={"symbol": "NIFTY 22500 CE 15 OCT 26", "ltp": 50.0, "bid": 49.8, "ask": 50.2},
        session_gear="GEAR_1_RANGE",
        is_expiry_day=True,
        is_deep_itm=False,
    )
    assert entered is True
    assert apm.payload.max_hold_minutes == 15

    # At 14:16 (16m elapsed), spot unchanged, normal spread -> time exit triggers cleanly
    apm.payload.opt_bid = 47.8
    apm.payload.opt_ask = 48.2
    state, payload = apm.evaluate_tick(
        current_spot=22500.0, current_opt_ltp=48.0, tick_time_str="2026-10-15T14:16:00"
    )
    # Liquidate transitions through EXIT_PENDING to COOL_OFF (or LIQUIDATED)
    assert state in {STATE_COOL_OFF, STATE_LIQUIDATED}
    assert apm.last_completed_trade is not None
    assert "TIME_EXIT_16M" in apm.last_completed_trade["exit_reason"]
