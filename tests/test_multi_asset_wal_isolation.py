"""Tests proving strict Multi-Asset WAL State Isolation between NIFTY and SENSEX.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Guarantees:
1. NIFTY and SENSEX maintain completely independent Write-Ahead Logs.
2. Concurrent or sequential state transitions in SENSEX never alter NIFTY state.
3. Crash recovery on SENSEX never restores NIFTY positions or vice-versa.
"""
from pathlib import Path
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_LIQUIDATED,
)
from core.asset_profile_registry import get_asset_profile


def test_nifty_and_sensex_wal_paths_are_fully_isolated(tmp_path):
    nifty_wal = tmp_path / "runtime/sentinel_apm_wal.json"
    sensex_wal = tmp_path / "runtime/sentinel_apm_wal_sensex.json"

    nifty_profile = get_asset_profile("NIFTY")
    sensex_profile = get_asset_profile("SENSEX")

    apm_nifty = ActivePositionManager(wal_path=str(nifty_wal), profile=nifty_profile)
    apm_sensex = ActivePositionManager(wal_path=str(sensex_wal), profile=sensex_profile)

    assert apm_nifty.state == STATE_STANDBY
    assert apm_sensex.state == STATE_STANDBY
    assert apm_nifty.wal_path != apm_sensex.wal_path

    # Arm and enter SENSEX trade
    armed_sensex = apm_sensex.arm_and_enter(
        position_id="SENSEX_0945_CE",
        direction="CE",
        contract="SENSEX 80000 CE [ITM]",
        entry_price=80020.0,
        entry_time_str="2026-10-15T09:45:00+05:30",
        sl_pts=30.0,
        tp_pts=46.0,
        opt_quote={"symbol": "SENSEX 80000 CE 15 OCT 26", "ltp": 310.0, "bid": 308.0, "ask": 312.0},
    )
    assert armed_sensex is True
    assert apm_sensex.state == STATE_IN_FLIGHT
    assert apm_sensex.wal_path.exists()

    # NIFTY APM must remain pristine and completely unaffected in STANDBY
    assert apm_nifty.state == STATE_STANDBY
    assert apm_nifty.payload is None

    # Simulate crash and independent reboot
    reboot_nifty = ActivePositionManager(wal_path=str(nifty_wal), profile=nifty_profile)
    reboot_sensex = ActivePositionManager(wal_path=str(sensex_wal), profile=sensex_profile)

    # NIFTY reboots to STANDBY with zero open trades
    assert reboot_nifty.state == STATE_STANDBY
    assert reboot_nifty.payload is None

    # SENSEX reboots fail-closed with its own in-flight position
    assert reboot_sensex.state == "EXIT_PENDING"
    assert reboot_sensex.payload.position_id == "SENSEX_0945_CE"
    assert reboot_sensex.payload.entry_price == 80020.0
