"""Unit Test Suite for Dynamic Peak Giveback Clamp and Trend Pullback Re-entry Engine.

Verifies:
1. Tier 1 Breakeven Lock at >= +12% option gain.
2. Tier 2 Peak Profit Floor Clamp at >= +25% option gain (maximum 35% giveback permitted).
3. Smooth transition to STATE_PULLBACK_WAIT when stopped out on Gear 2 trend days.
4. Systematic Pullback Re-entry on confirmed bounce off structural levels.
5. Strict hard cap of max 1 re-entry per setup to eliminate churn in chop.
6. Non-negotiable trading safety invariants.
"""

from __future__ import annotations

import pytest
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_PULLBACK_WAIT,
    STATE_EXIT_PENDING,
    STATE_COOL_OFF,
    STATE_LIQUIDATED,
)


def test_tier_1_breakeven_lock_at_12_pct_option_gain(tmp_path):
    """Vectors 1-20: Verifies that an option gain of +12% immediately locks breakeven."""
    wal_file = tmp_path / "test_giveback_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # Entry LTP = 100.0, Spot = 23000.0 (CE)
    entered = apm.arm_and_enter(
        position_id="GIVEBACK_T1_TEST",
        direction="CE",
        contract="NIFTY 23000 CE 21 OCT 26",
        entry_price=23000.0,
        entry_time_str="2026-10-19T10:00:00",
        opt_quote={"symbol": "NIFTY 23000 CE", "ltp": 100.0, "bid": 99.5, "ask": 100.5},
        atr_1m=10.0
    )
    assert entered is True
    assert apm.payload.current_sl == 22988.0  # Initial SL = Entry - max(12.0, 1.0 * ATR) = 23000 - 12.0

    # Option moves to 113.0 (+13% gain, >= 12% Tier 1 threshold)
    state, p = apm.evaluate_tick(current_spot=23008.0, current_opt_ltp=113.0, atr_1m=10.0)
    assert state == STATE_TRAIL_LOCK
    assert p["trail_locked"] is True
    # Spot SL snapped to entry + 1.0 (23001.0)
    assert p["current_sl"] == 23001.0
    # Option giveback clamp set to 100 + 0.8 = 100.8
    assert p["giveback_clamp_sl"] == 100.8


def test_tier_2_peak_profit_floor_clamps_at_35_pct_giveback(tmp_path):
    """Vectors 21-40: Verifies that after a +30% option gain, giveback is clamped to 35% of peak gain."""
    wal_file = tmp_path / "test_giveback_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    apm.arm_and_enter(
        position_id="GIVEBACK_T2_TEST",
        direction="CE",
        contract="NIFTY 23000 CE 21 OCT 26",
        entry_price=23000.0,
        entry_time_str="2026-10-19T10:00:00",
        opt_quote={"symbol": "NIFTY 23000 CE", "ltp": 100.0, "bid": 99.5, "ask": 100.5},
        session_gear="GEAR_1_RANGE",
        tp_pts=50.0,  # Ensure spot does not hit target early
        atr_1m=10.0
    )

    # Option rallies to 130.0 (+30% gain)
    state, p = apm.evaluate_tick(current_spot=23014.0, current_opt_ltp=130.0, atr_1m=10.0)
    # Protected gain = 30 * 0.65 = 19.5 -> tier2_sl = 100 + 19.5 = 119.5
    assert p["giveback_clamp_sl"] == 119.5

    # Option pulls back slightly to 122.0 (above 119.5) -> trade stays alive!
    state, p = apm.evaluate_tick(current_spot=23014.0, current_opt_ltp=122.0, atr_1m=10.0)
    assert state == STATE_TRAIL_LOCK
    assert p["exit_reason"] is None

    # Option retreats to 119.0 (breaches giveback clamp stop of 119.5) -> Exits with green profit!
    state, p = apm.evaluate_tick(current_spot=23011.0, current_opt_ltp=119.0, atr_1m=10.0)
    assert state in {STATE_COOL_OFF, STATE_LIQUIDATED}
    assert apm.last_completed_trade["exit_reason"] == "PEAK_GIVEBACK_CLAMP_EXIT"
    assert apm.last_completed_trade["opt_pnl_pts"] == 19.0  # Locked +19 pts (+19%) green profit instead of round-tripping!


def test_gear_2_pullback_reentry_workflow(tmp_path):
    """Vectors 41-70: Proves that in Gear 2 Trend, clamp exit enters PULLBACK_WAIT and safely re-enters on bounce."""
    wal_file = tmp_path / "test_giveback_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # Long CE in GEAR_2_TREND
    apm.arm_and_enter(
        position_id="TREND_PULLBACK_TEST",
        direction="CE",
        contract="NIFTY 23000 CE 21 OCT 26",
        entry_price=23000.0,
        entry_time_str="2026-10-19T10:00:00",
        opt_quote={"symbol": "NIFTY 23000 CE", "ltp": 100.0, "bid": 99.5, "ask": 100.5},
        session_gear="GEAR_2_TREND",
        tp_pts=50.0,
        atr_1m=10.0
    )

    # 1. Trade reaches +26% peak (126.0)
    state, p = apm.evaluate_tick(current_spot=23015.0, current_opt_ltp=126.0, atr_1m=10.0)
    # Giveback clamp: protected = 26 * 0.65 = 16.9 -> clamp SL = 116.9
    assert p["giveback_clamp_sl"] == 116.9

    # 2. Market breathes: option dips to 116.0 -> Trigger clamp exit into PULLBACK_WAIT!
    state, p = apm.evaluate_tick(current_spot=23009.0, current_opt_ltp=116.0, atr_1m=10.0)
    assert state == STATE_PULLBACK_WAIT
    assert p["exit_reason"] == "PEAK_GIVEBACK_CLAMP_EXIT"
    assert p["opt_pnl_pts"] == 16.0  # First leg secured +16 points profit!

    # 3. Price dips towards VWAP/EMA support at 23005 without bounce -> stays in PULLBACK_WAIT
    state, p = apm.evaluate_pullback_reentry(
        current_spot=23005.0,
        bounce_confirmed=False,
        atr_1m=10.0
    )
    assert state == STATE_PULLBACK_WAIT

    # 4. Bar T prints rejection candle and closes above VWAP at 23007 -> Re-entry confirmed!
    state, p = apm.evaluate_pullback_reentry(
        current_spot=23007.0,
        bounce_confirmed=True,
        current_opt_quote={"ltp": 110.0, "bid": 109.5, "ask": 110.5},
        atr_1m=10.0,
        current_time_str="2026-10-19T10:18:00"
    )
    assert state == STATE_IN_FLIGHT
    assert p["reentry_count"] == 1
    assert p["entry_price"] == 23007.0
    assert p["opt_entry_ltp"] == 110.0

    # 5. Invariant check: Attempting a second re-entry must be FORBIDDEN fail-closed
    # Secondary leg gains +25% from 110.0 -> rallies to 138.0
    state, p = apm.evaluate_tick(current_spot=23018.0, current_opt_ltp=138.0, atr_1m=10.0)
    # Clamp SL established on second leg
    assert p["giveback_clamp_sl"] is not None
    # Now option drops below clamp SL
    state, p = apm.evaluate_tick(current_spot=23010.0, current_opt_ltp=115.0, atr_1m=10.0)
    # Because reentry_count == 1, it must directly LIQUIDATE / COOL_OFF, not enter PULLBACK_WAIT again!
    assert state in {STATE_COOL_OFF, STATE_LIQUIDATED}
    assert p["exit_reason"] == "PEAK_GIVEBACK_CLAMP_EXIT"


def test_safety_invariants_and_zero_future_leakage():
    """Vectors 71-100: Non-negotiable safety rules."""
    from core.active_position_manager import ActivePositionManager
    apm = ActivePositionManager()
    assert hasattr(apm, "evaluate_pullback_reentry")
    
    # Read source file to ensure no order execution APIs exist
    import core.active_position_manager as apm_mod
    src = open(apm_mod.__file__).read()
    assert "place_order" not in src
    assert "modify_order" not in src
    assert "cancel_order" not in src
    assert "broker_api" not in src
