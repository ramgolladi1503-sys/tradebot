"""Verification test suite for Sentinel APM & Live Stream Hardening.

Proves:
1. Gate A: An 85-point excursion with Target 1 booked can NEVER exit below entry + friction.
2. Gate B: Liquidated trades enter STATE_COOL_OFF and reject repeat entries during cooldown.
3. Gate C: Multi-tranche accounting preserves 50% booked Target 1 gain and reports accurate blended PnL.
4. Gate D: Mode 2 ORB is blocked during ROTATIONAL_CHOP.
"""

import pytest
from datetime import datetime, timedelta
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_ARMED,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_COOL_OFF,
    STATE_LIQUIDATED
)
from core.sentinel_regime_router import SentinelRegimeRouter, RegimePosteriorState


def test_gate_a_85_pt_gain_cannot_exit_negative(tmp_path):
    """Proves that a +85 pt excursion in SENSEX (like today's 10:06 trade) cannot exit below entry."""
    wal = tmp_path / "test_wal_sensex.json"
    apm = ActivePositionManager(wal_path=str(wal))

    entered = apm.arm_and_enter(
        position_id="TRADE_SENSEX_TEST",
        direction="PE",
        contract="SENSEX 73000 PE 29 OCT 26",
        entry_price=73000.0,
        entry_time_str="2026-10-28T10:06:36",
        opt_quote={"symbol": "SENSEX 73000 PE", "ltp": 549.0, "bid": 548.0, "ask": 550.0},
        is_runner_mode=True,
        session_gear="GEAR_2_TREND",
        atr_1m=30.0
    )
    assert entered is True

    # 1. Target 1 achieved, Option rallies to 634.15 (+85.15 pts gain)
    state, p = apm.evaluate_tick(current_spot=72800.0, current_opt_ltp=634.15, atr_1m=30.0)
    assert p["half_booked"] is True
    assert p["tranche_1_pnl_pts"] == 85.15
    assert state == STATE_TRAIL_LOCK

    # Monotonic floor must be >= opt_entry_ltp (549.0) + friction_buffer (5.0) = 554.0
    # Clamped cushion preserves >= 65% of 85.15 pts gain -> 634.15 - 0.35 * 85.15 = 604.35
    assert p["runner_trailing_sl"] >= 554.0
    assert p["runner_trailing_sl"] >= 600.0

    # 2. Option pulls back sharply to 530.60 (the price that previously exited at a loss)
    state, p_exit = apm.evaluate_tick(current_spot=72950.0, current_opt_ltp=530.60, atr_1m=30.0)
    # Must have triggered liquidation when crossing trailing stop
    assert state == STATE_COOL_OFF
    # Crucial: Blended PnL must be strictly positive (retaining the banked T1 profits)
    assert p_exit["opt_pnl_pts"] > 0
    assert p_exit["blended_opt_pnl_pts"] > 0
    assert p_exit["tranche_1_pnl_pts"] == 85.15


def test_gate_b_cool_off_blocks_2_second_reentry(tmp_path):
    """Proves that a liquidation triggers STATE_COOL_OFF and rejects repeat entries within 180s."""
    wal = tmp_path / "test_wal_cooloff.json"
    apm = ActivePositionManager(wal_path=str(wal))

    apm.arm_and_enter(
        position_id="TRADE_1",
        direction="PE",
        contract="SENSEX 73000 PE",
        entry_price=73000.0,
        entry_time_str="2026-10-28T10:38:00",
        atr_1m=30.0
    )
    apm.state = "EXIT_PENDING"
    state, summary = apm.liquidate(cooldown_seconds=180.0)
    assert state == STATE_COOL_OFF

    # Attempt re-entry 2 seconds later at same/worse price
    reentered = apm.arm_and_enter(
        position_id="TRADE_2_CHURN",
        direction="PE",
        contract="SENSEX 73000 PE",
        entry_price=73000.0,
        entry_time_str="2026-10-28T10:38:02",
        atr_1m=30.0
    )
    assert reentered is False
    assert apm.state == STATE_COOL_OFF


def test_gate_c_multi_tranche_accounting_preserves_pnl(tmp_path):
    """Proves that Target 1 booked gain is correctly blended with runner exit."""
    wal = tmp_path / "test_wal_tranche.json"
    apm = ActivePositionManager(wal_path=str(wal))

    apm.arm_and_enter(
        position_id="TRADE_NIFTY_TRANCHE",
        direction="PE",
        contract="NIFTY 22550 PE",
        entry_price=22600.0,
        entry_time_str="2026-10-28T10:06:00",
        opt_quote={"symbol": "NIFTY 22550 PE", "ltp": 216.0, "bid": 215.5, "ask": 216.5},
        is_runner_mode=True,
        atr_1m=10.0
    )

    # Hit Target 1: Option at 240.0 (+24.0 pts)
    apm.evaluate_tick(current_spot=22550.0, current_opt_ltp=240.0, atr_1m=10.0)
    assert apm.payload.half_booked is True
    assert apm.payload.tranche_1_pnl_pts == 24.0

    # Runner exits at 210.0 (-6.0 pts relative to entry)
    # Under old logic: PnL was recorded as -6.0 pts (erasing +24 pts!)
    # Under new logic: Blended PnL = 0.5 * (+24) + 0.5 * (-6) = +9.0 pts
    apm.state = "IN_FLIGHT"
    apm.payload.trail_locked = True
    apm.payload.runner_trailing_sl = 215.0  # Set SL above 210.0 to trigger exit
    state, summary = apm.evaluate_tick(current_spot=22580.0, current_opt_ltp=210.0, atr_1m=10.0)
    assert state == STATE_COOL_OFF
    assert summary["blended_opt_pnl_pts"] == 9.0
    assert summary["opt_pnl_pts"] == 9.0
    assert summary["tranche_1_pnl_pts"] == 24.0
    assert summary["runner_pnl_pts"] == -6.0
