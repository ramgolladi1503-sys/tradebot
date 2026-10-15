import pytest

def test_pe_stop_loss_inequality_counterexample():
    """
    Reviewer D Reproduction Test:
    Demonstrates DEF-01 in scripts/run_walk_forward_optimizer.py line 119.
    
    A BUY_PE trade enters at 22700 with a 12pt stop loss at 22712.
    If the market moves in our favor (drops to 22690, bar high is 22695):
    - Intended behavior: Stop Loss is NOT hit (22695 < 22712).
    - Buggy behavior (high <= sl_spot): 22695 <= 22712 evaluates to TRUE!
      The winning trade is prematurely stopped out at a loss!
    """
    entry_spot = 22700.0
    sl_pts = 12.0
    sl_spot = entry_spot + sl_pts  # 22712.0 (above entry for PE)
    
    # Next bar drops favorably: open=22698, high=22705, low=22680, close=22685
    curr_bar_high = 22705.0
    
    # Buggy condition from scripts/run_walk_forward_optimizer.py:119
    buggy_hit_sl = (curr_bar_high <= sl_spot)
    
    # Corrected condition
    correct_hit_sl = (curr_bar_high >= sl_spot)
    
    # Assert the bug produces false liquidation
    assert buggy_hit_sl is True, "Buggy code triggers false stop on favorable bar"
    assert correct_hit_sl is False, "Correct code keeps trade alive on favorable bar"

def test_active_position_manager_is_unaffected_by_def01():
    """
    Reviewer D Non-Regression Oracle:
    Proves that core/active_position_manager.py line 160 uses the CORRECT comparison:
    `bar_high >= current_sl` for PE trades.
    """
    from core.active_position_manager import ActivePositionManager
    from core.asset_profile_registry import get_asset_profile
    
    profile = get_asset_profile("NIFTY")
    apm = ActivePositionManager(wal_path="runtime/test_wal_pe.json", profile=profile)
    
    # Arm PE trade
    apm.arm_and_enter(
        position_id="TEST_PE",
        direction="PE",
        contract="NIFTY 22700 PE",
        entry_price=22700.0,
        entry_time_str="2026-10-15T10:00:00",
        sl_pts=12.0,
        tp_pts=15.0
    )
    assert apm.payload.current_sl == 22712.0
    
    # Favorable bar drops slightly: high=22705, low=22692 (Target at 22685 not touched)
    state, summary = apm.evaluate_bar(
        bar_open=22698.0,
        bar_high=22705.0,
        bar_low=22692.0,
        bar_close=22695.0,
        bar_time_str="2026-10-15T10:01:00",
        atr_1m=10.0
    )
    
    # Must NOT be liquidated (trade stays in flight, proving PE stop is not falsely hit)
    assert state != "LIQUIDATED", f"APM falsely liquidated trade: {summary}"
    assert apm.payload.position_id == "TEST_PE"
    
    # Cleanup
    import os
    if os.path.exists("runtime/test_wal_pe.json"):
        os.remove("runtime/test_wal_pe.json")
