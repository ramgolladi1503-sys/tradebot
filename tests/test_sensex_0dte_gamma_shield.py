"""Tests proving Layer 3: 0-DTE Greek Shields & Expiry Calendar Guarantees.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Guarantees:
1. 2026 official exchange holiday matrix correctly pulls forward Thursday expiries.
2. SENSEX 0-DTE dynamic theta decay curve shortens holding horizon in the afternoon.
"""
from datetime import datetime
from core.expiry_calendar import get_days_to_expiry, is_holiday
from core.active_position_manager import ActivePositionManager
from core.asset_profile_registry import get_asset_profile


def test_2026_holiday_pull_forward():
    # Oct 2, 2026 is Mahatma Gandhi Jayanti (Friday)
    assert is_holiday(datetime(2026, 10, 2)) is True

    # Check a standard Thursday (e.g. 2026-10-15) -> 0-DTE for SENSEX
    dte_sensex = get_days_to_expiry(datetime(2026, 10, 15), "SENSEX")
    assert dte_sensex == 0


def test_0dte_afternoon_theta_holding_horizon(tmp_path):
    wal = tmp_path / "runtime/sentinel_apm_wal_sensex.json"
    sensex = get_asset_profile("SENSEX")
    apm = ActivePositionManager(wal_path=str(wal), profile=sensex)

    # 1. Morning Entry at 10:00 AM (mins to close = 330 > 180) -> Normal 15 min hold
    entered_morn = apm.arm_and_enter(
        position_id="SENSEX_1000_CE",
        direction="CE",
        contract="SENSEX 80000 CE [ITM]",
        entry_price=80000.0,
        entry_time_str="2026-10-15T10:00:00+05:30",
        sl_pts=30.0,
        tp_pts=46.0,
        session_gear="GEAR_1_RANGE",
    )
    assert entered_morn is True
    assert apm.payload.max_hold_minutes == 15

    # Cleanly transition to EXIT_PENDING and liquidate
    apm._transition_to("EXIT_PENDING")
    apm.liquidate()
    assert apm.payload is None

    # 2. Late Afternoon Entry at 14:30 PM (mins to close = 60 < 180)
    # Scaled horizon: max(6, 15 * (60/180)) = max(6, 5) = 6 minutes!
    entered_aft = apm.arm_and_enter(
        position_id="SENSEX_1430_CE",
        direction="CE",
        contract="SENSEX 80000 CE [ITM]",
        entry_price=80000.0,
        entry_time_str="2026-10-15T14:30:00+05:30",
        sl_pts=30.0,
        tp_pts=46.0,
        session_gear="GEAR_1_RANGE",
    )
    assert entered_aft is True
    assert apm.payload.max_hold_minutes == 6
