"""Comprehensive Unit Tests for ActivePositionManager.

Proves:
- Gate 1: Intrabar Pessimism Proof (SL hit first if both TP and SL are touched in the same bar)
- Gate 2: Ratchet Monotonicity Proof (SL never regresses on high/low price fluctuations)
- Gate 3: State Recovery Proof (Mid-flight process crash / restart triggers fail-closed EXIT_PENDING)
- Gate 4: Session Phase Variance Decay (SPVD) Energy Gate Proof (Session depletion rejection)
- 15-Minute Time Exit Invariant Proof
"""

import pytest
import os
import json
from datetime import time as dtime
from pathlib import Path

from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_ARMED,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_EXIT_PENDING,
    STATE_LIQUIDATED
)


@pytest.fixture
def tmp_wal(tmp_path):
    return str(tmp_path / "sentinel_apm_wal.json")


def test_gate1_intrabar_pessimism_sl_collision(tmp_wal):
    """Gate 1: Prove that when a single bar spans both TP and SL, SL hits chronologically first."""
    apm = ActivePositionManager(wal_path=tmp_wal)
    
    # Enter CE trade at 22,700 with SL 22,688 (-12) and TP 22,718 (+18)
    ok = apm.arm_and_enter(
        position_id="TEST_001",
        direction="CE",
        contract="NIFTY 22700 CE",
        entry_price=22700.0,
        entry_time_str="2026-10-07T10:00:00",
        sl_pts=12.0,
        tp_pts=18.0
    )
    assert ok is True
    assert apm.state == STATE_IN_FLIGHT

    # Simulate an extreme 35-point bar: Low = 22680 (below SL), High = 22720 (above TP)
    st, summary = apm.evaluate_bar(
        bar_open=22700.0,
        bar_high=22720.0,
        bar_low=22680.0,
        bar_close=22710.0,
        bar_time_str="2026-10-07T10:01:00"
    )

    # Pessimistic Intrabar Resolution MUST force SL hit
    assert st == STATE_LIQUIDATED
    assert summary["exit_reason"] == "PESSIMISTIC_INTRABAR_SL_COLLISION"
    assert summary["exit_price"] == 22688.0
    assert summary["pnl_pts"] == -12.0


def test_gate2_ratchet_monotonicity_proof(tmp_wal):
    """Gate 2: Trailing stop ratchet must lock at +4 pts after +8 pts gain and never regress."""
    apm = ActivePositionManager(wal_path=tmp_wal)
    apm.arm_and_enter(
        position_id="TEST_002",
        direction="CE",
        contract="NIFTY 22700 CE",
        entry_price=22700.0,
        entry_time_str="2026-10-07T10:00:00",
        sl_pts=12.0,
        tp_pts=18.0
    )

    # Bar 1: Price reaches +8.5 pts (High = 22708.5). Ratchet locks to 22704 (+4 pts)
    st, payload = apm.evaluate_bar(
        bar_open=22700.0,
        bar_high=22708.5,
        bar_low=22699.0,
        bar_close=22707.0,
        bar_time_str="2026-10-07T10:01:00"
    )
    assert st == STATE_TRAIL_LOCK
    assert payload["trail_locked"] is True
    assert payload["current_sl"] == 22704.0

    # Bar 2: Price pulls back to 22705 (above 22704). Current SL MUST NOT regress downwards
    st2, payload2 = apm.evaluate_bar(
        bar_open=22707.0,
        bar_high=22707.5,
        bar_low=22704.5,
        bar_close=22705.0,
        bar_time_str="2026-10-07T10:02:00"
    )
    assert st2 == STATE_TRAIL_LOCK
    assert payload2["current_sl"] == 22704.0

    # Bar 3: Price drops below trailed SL (Low = 22703.0) -> Triggers Trailing Stop Exit with locked profit
    st3, summary = apm.evaluate_bar(
        bar_open=22705.0,
        bar_high=22706.0,
        bar_low=22703.0,
        bar_close=22703.5,
        bar_time_str="2026-10-07T10:03:00"
    )
    assert st3 == STATE_LIQUIDATED
    assert summary["exit_reason"] == "TRAILING_STOP_HIT"
    assert summary["exit_price"] == 22704.0
    assert summary["pnl_pts"] == +4.0


def test_gate3_crash_recovery_fail_closed_proof(tmp_wal):
    """Gate 3: Process hard kill / restart during in-flight trade forces fail-closed recovery."""
    apm = ActivePositionManager(wal_path=tmp_wal)
    apm.arm_and_enter(
        position_id="TEST_003",
        direction="PE",
        contract="NIFTY 22700 PE",
        entry_price=22700.0,
        entry_time_str="2026-10-07T10:00:00",
        sl_pts=12.0,
        tp_pts=18.0
    )
    assert apm.state == STATE_IN_FLIGHT

    # Simulate abrupt crash: Re-instantiate a fresh APM loading the persisted WAL
    rebooted_apm = ActivePositionManager(wal_path=tmp_wal)
    
    # Must immediately detect orphaned state and force fail-closed EXIT_PENDING
    assert rebooted_apm.state == STATE_EXIT_PENDING
    assert rebooted_apm.payload.exit_reason == "CRASH_RECOVERY_FAIL_CLOSED"

    # Completes fail-closed liquidation
    final_st, summary = rebooted_apm.liquidate()
    assert final_st == STATE_LIQUIDATED
    assert rebooted_apm.payload is None


def test_gate4_energy_gate_spvd_proof(tmp_wal):
    """Gate 4: Session Phase Variance Decay correctly gates trades when remaining energy is depleted."""
    apm = ActivePositionManager(wal_path=tmp_wal)

    # 1. Early morning 10:00 AM (Lots of energy remaining) -> Allowed
    can_enter_morning, e_atr_morn, req_morn = apm.check_session_energy_gate(
        current_time=dtime(10, 0),
        daily_norm_atr=120.0,
        target_pts=18.0,
        buffer_multiplier=1.5
    )
    assert can_enter_morning is True
    assert e_atr_morn > req_morn

    # 2. Final 15 minutes of session (15:15 PM) -> Exhausted & Rejected
    can_enter_close, e_atr_close, req_close = apm.check_session_energy_gate(
        current_time=dtime(15, 15),
        daily_norm_atr=120.0,
        target_pts=18.0,
        buffer_multiplier=1.5
    )
    assert can_enter_close is False
    assert e_atr_close < req_close

    # 3. Afternoon 14:00 PM on a severe RANGE day (e.g., today Oct 7 with KER = 0.0463)
    # The low directional efficiency collapses expected variance -> Rejected
    can_enter_range, e_atr_range, req_range = apm.check_session_energy_gate(
        current_time=dtime(14, 0),
        daily_norm_atr=120.0,
        target_pts=18.0,
        buffer_multiplier=1.5,
        session_ker=0.0463
    )
    assert can_enter_range is False
    assert e_atr_range < req_range


def test_15_minute_time_exit_proof(tmp_wal):
    """Verify that a trade held for >= 15 minutes is exited at market close of the 15th bar."""
    apm = ActivePositionManager(wal_path=tmp_wal)
    apm.arm_and_enter(
        position_id="TEST_005",
        direction="CE",
        contract="NIFTY 22700 CE",
        entry_price=22700.0,
        entry_time_str="2026-10-07T10:00:00",
        sl_pts=12.0,
        tp_pts=18.0
    )

    # Bar at 10:14:00 (14 minutes) -> Still in flight
    st, _ = apm.evaluate_bar(
        bar_open=22701.0,
        bar_high=22704.0,
        bar_low=22698.0,
        bar_close=22702.0,
        bar_time_str="2026-10-07T10:14:00"
    )
    assert st == STATE_IN_FLIGHT

    # Bar at 10:15:00 (15 minutes exactly) -> Hits 15m time exit ceiling
    st2, summary = apm.evaluate_bar(
        bar_open=22702.0,
        bar_high=22705.0,
        bar_low=22701.0,
        bar_close=22703.5,
        bar_time_str="2026-10-07T10:15:00"
    )
    assert st2 == STATE_LIQUIDATED
    assert summary["exit_reason"] == "TIME_EXIT_15M"
    assert summary["exit_price"] == 22703.5
    assert summary["pnl_pts"] == +3.5


def test_runner_mode_hwm_trailing_proof(tmp_wal):
    """Verify that when is_runner_mode=True, the position:
    1. Books 50% upon reaching target_price, transitions to STATE_TRAIL_LOCK, locks Spot SL at +4 pts, and initializes Option HWM SL.
    2. Continues trailing the second half with peak option High-Watermark (HWM).
    3. Liquidates when option price breaches the ratcheted HWM trailing stop.
    """
    apm = ActivePositionManager(wal_path=tmp_wal)
    # Enter PE trade at Spot 22,400 with target +15.0 pts (at 22,385) and option LTP 120.0
    apm.arm_and_enter(
        position_id="TEST_RUNNER_001",
        direction="PE",
        contract="NIFTY 22450 PE [ITM]",
        entry_price=22400.0,
        entry_time_str="2026-10-08T10:00:00",
        sl_pts=14.0,
        tp_pts=15.0,
        is_runner_mode=True,
        opt_quote={"symbol": "NIFTY24OCT22450PE", "token": "12345", "ltp": 120.0, "bid": 119.5, "ask": 120.5}
    )
    assert apm.state == STATE_IN_FLIGHT
    assert apm.payload.is_runner_mode is True
    assert apm.payload.half_booked is False
    assert apm.payload.max_hold_minutes == 25

    # Bar 1: Spot drops to 22380 (below target 22385). Option surges to 135.0.
    # ATR_1m = 10.0. Option cushion = max(12.0, 1.2 * 10.0) = 12.0.
    # Should book 50%, lock trail, and set runner_trailing_sl = 135.0 - 12.0 = 123.0
    st1, p1 = apm.evaluate_bar(
        bar_open=22400.0,
        bar_high=22401.0,
        bar_low=22380.0,
        bar_close=22382.0,
        bar_time_str="2026-10-08T10:01:00",
        current_opt_ltp=135.0,
        atr_1m=10.0
    )
    assert st1 == STATE_TRAIL_LOCK
    assert apm.payload.half_booked is True
    assert apm.payload.trail_locked is True
    assert apm.payload.current_sl == 22396.0  # entry_price (22400) - 4.0 for PE
    assert apm.payload.opt_peak_hwm == 135.0
    assert apm.payload.runner_trailing_sl == 123.0

    # Bar 2: Spot extends downwards to 22350. Option surges to peak 160.0.
    # Trailing SL should ratchet up to 160.0 - 12.0 = 148.0.
    st2, p2 = apm.evaluate_bar(
        bar_open=22382.0,
        bar_high=22383.0,
        bar_low=22350.0,
        bar_close=22355.0,
        bar_time_str="2026-10-08T10:02:00",
        current_opt_ltp=160.0,
        atr_1m=10.0
    )
    assert st2 == STATE_TRAIL_LOCK
    assert apm.payload.opt_peak_hwm == 160.0
    assert apm.payload.runner_trailing_sl == 148.0

    # Bar 3: Option pulls back to 147.0 (breaches trailing SL 148.0).
    # Position should liquidate with RUNNER_HWM_TRAILING_EXIT.
    st3, summary = apm.evaluate_bar(
        bar_open=22355.0,
        bar_high=22365.0,
        bar_low=22350.0,
        bar_close=22362.0,
        bar_time_str="2026-10-08T10:03:00",
        current_opt_ltp=147.0,
        atr_1m=10.0
    )
    assert st3 == STATE_LIQUIDATED
    assert summary["exit_reason"] == "RUNNER_HWM_TRAILING_EXIT"
    assert summary["opt_exit_ltp"] == 147.0
    assert summary["opt_pnl_pts"] == 27.0  # 147.0 - 120.0


def test_gear2_option_native_stop_proof(tmp_wal):
    """Verify that in GEAR_2_TREND mode:
    1. Spot counter-wicks do NOT trigger premature stop-outs if the option premium holds.
    2. The position is stopped out if and only if the option premium drops below the -20% option SL.
    """
    apm = ActivePositionManager(wal_path=tmp_wal)
    apm.arm_and_enter(
        position_id="TEST_GEAR2_001",
        direction="PE",
        contract="NIFTY 22450 PE [ITM]",
        entry_price=22400.0,
        entry_time_str="2026-10-08T10:00:00",
        sl_pts=12.0,  # Spot SL would be 22412.0
        tp_pts=15.0,
        is_runner_mode=True,
        session_gear="GEAR_2_TREND",
        opt_stop_loss_pct=0.20,
        opt_quote={"symbol": "NIFTY24OCT22450PE", "token": "12345", "ltp": 100.0, "bid": 99.5, "ask": 100.5}
    )
    assert apm.state == STATE_IN_FLIGHT
    assert apm.payload.session_gear == "GEAR_2_TREND"
    assert apm.payload.opt_initial_sl == 80.0  # 100.0 * (1 - 0.20)
    assert apm.payload.max_hold_minutes == 360

    # Bar 1: Spot counter-bounces to 22415.0 (breaching the 12pt spot SL of 22412.0).
    # BUT option IV holds the premium at 88.0 (above 80.0).
    # In GEAR_2_TREND, the trade MUST NOT be stopped out by spot noise!
    st1, p1 = apm.evaluate_bar(
        bar_open=22400.0,
        bar_high=22415.0,
        bar_low=22398.0,
        bar_close=22410.0,
        bar_time_str="2026-10-08T10:01:00",
        current_opt_ltp=88.0,
        atr_1m=12.0
    )
    assert st1 == STATE_IN_FLIGHT  # Survived the spot noise collision!

    # Bar 2: Option premium actually drops below 80.0 (e.g. to 78.0).
    # Now it triggers OPTION_NATIVE_STOP_LOSS_HIT.
    st2, summary = apm.evaluate_bar(
        bar_open=22410.0,
        bar_high=22418.0,
        bar_low=22405.0,
        bar_close=22416.0,
        bar_time_str="2026-10-08T10:02:00",
        current_opt_ltp=78.0,
        atr_1m=12.0
    )
    assert st2 == STATE_LIQUIDATED
    assert summary["exit_reason"] == "OPTION_NATIVE_STOP_LOSS_HIT"
    assert summary["opt_exit_ltp"] == 78.0
    assert summary["opt_pnl_pts"] == -22.0


def test_breakeven_lock_proof(tmp_wal):
    """Verify that when spot price moves favorably by +12.0 points,
    Stop Loss automatically snaps to Breakeven (+1.0 point profit) to guard against trend stalls.
    """
    apm = ActivePositionManager(wal_path=tmp_wal)
    apm.arm_and_enter(
        position_id="TEST_BE_001",
        direction="CE",
        contract="NIFTY 22400 CE [ITM]",
        entry_price=22400.0,
        entry_time_str="2026-10-08T10:00:00",
        sl_pts=14.0,  # Initial SL = 22386.0
        tp_pts=25.0,
        session_gear="GEAR_1_RANGE"
    )
    assert apm.state == STATE_IN_FLIGHT
    assert apm.payload.current_sl == 22386.0

    # Bar 1: Price rallies to 22412.5 (+12.5 pts).
    # Breakeven lock triggers: new SL = 22401.0 (entry + 1.0).
    st1, p1 = apm.evaluate_bar(
        bar_open=22400.0,
        bar_high=22412.5,
        bar_low=22399.0,
        bar_close=22411.0,
        bar_time_str="2026-10-08T10:01:00",
        current_opt_ltp=110.0
    )
    assert st1 == STATE_TRAIL_LOCK
    assert apm.payload.trail_locked is True
    assert apm.payload.current_sl == 22401.0


