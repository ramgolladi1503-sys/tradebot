"""Unit and regression tests for Asymmetric Structural Runner Trailing Engine."""

import pytest
from core.active_position_manager import (
    ActivePositionManager,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_COOL_OFF,
    STATE_LIQUIDATED,
)


def test_structural_runner_trailing_allows_breathing_room(tmp_path):
    """Verify that a 50% runner anchored to 15m structural swing is not stopped out by minor spot wicks."""
    wal = tmp_path / "test_structural_runner_wal.json"
    apm = ActivePositionManager(wal_path=str(wal))

    # Long CE entry at 24500 with Target 1 at 24535 (+35 pts)
    # Structural Swing Low established at 24490 (entry bar swing low)
    apm.arm_and_enter(
        position_id="RUNNER_STRUCTURAL_TEST",
        direction="CE",
        contract="NIFTY 24500 CE",
        entry_price=24500.0,
        entry_time_str="2026-10-30T09:45:00",
        sl_pts=15.0,
        tp_pts=35.0,
        opt_quote={"symbol": "NIFTY 24500 CE", "ltp": 100.0, "bid": 99.5, "ask": 100.5},
        is_runner_mode=True,
        structural_runner_enabled=True,
        structural_swing_anchor_sl=24490.0,
    )

    # 1. Price hits Target 1 at 24535 (+35 pts spot excursion) -> Books 50% Tranche 1!
    state, p = apm.evaluate_tick(current_spot=24535.0, current_opt_ltp=130.0)
    assert p["target_1_hit"] is True
    assert p["half_booked"] is True
    assert p["tranche_1_pnl_pts"] == 30.0  # +30 pts locked on Tranche 1

    # 2. Trend consolidation: Spot takes a breath and pulls back to 24510 (pullback of 25 pts from high)
    # With normal tight trailing, this would stop out!
    # But Structural Swing is at 24490 -> Runner STAYS ALIVE!
    state, p = apm.evaluate_tick(current_spot=24510.0, current_opt_ltp=112.0)
    assert state == STATE_TRAIL_LOCK
    assert p["exit_reason"] is None

    # 3. Bar completes 15m consolidation and forms a new Higher Low at 24515.
    # Update structural swing anchor upward!
    updated = apm.update_structural_swing_anchor(24515.0)
    assert updated is True
    assert apm.payload.structural_swing_anchor_sl == 24515.0

    # 4. Secondary wave expands: Spot rallies to 24590 (+90 pts spot excursion!)
    state, p = apm.evaluate_tick(current_spot=24590.0, current_opt_ltp=175.0)
    assert state == STATE_TRAIL_LOCK
    assert p["opt_peak_hwm"] == 175.0

    # 5. Trend exhaustion: Spot reverses and breaks below new 15m Higher Low at 24515
    state, p = apm.evaluate_tick(current_spot=24512.0, current_opt_ltp=125.0)
    assert state in {STATE_COOL_OFF, STATE_LIQUIDATED}
    completed = apm.last_completed_trade
    assert completed["exit_reason"] == "STRUCTURAL_15M_SWING_EXIT"
    assert completed["runner_pnl_pts"] == 25.0  # Runner exited with +25 pts
    # Blended profit: 50% at +30 pts + 50% at +25 pts = +27.5 pts
    assert completed["blended_opt_pnl_pts"] == 27.5
