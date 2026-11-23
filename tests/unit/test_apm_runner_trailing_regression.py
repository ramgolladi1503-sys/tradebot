"""Tests for Active Position Manager runner trailing mode and monotonic ratchet.

Verifies:
1. Fix for opt_cushion NameError in evaluate_bar.
2. CE (Call) runner trailing stop activation and monotonic HWM ratchet.
3. PE (Put) runner trailing stop activation and monotonic HWM ratchet.
4. Partial profit booking (tranche 1) and runner transition.
5. Runner exit when live LTP breaches trailing SL.
6. WAL recovery roundtrip for runner state.
"""

from pathlib import Path
import json

import pytest
from core.active_position_manager import (
    ActivePositionManager,
    PositionPayload,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_COOL_OFF,
    STATE_LIQUIDATED,
    STATE_STANDBY,
    STATE_RECOVERY_BLOCKED,
    STATE_PULLBACK_WAIT,
    STATE_EXIT_PENDING,
)


def test_apm_runner_ce_monotonic_trailing_ratchet(tmp_path: Path):
    """Verifies that a CE runner position properly updates runner_trailing_sl without NameError."""
    wal = tmp_path / "apm_runner_ce_wal.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = STATE_TRAIL_LOCK
    apm.payload = PositionPayload(
        position_id="CE_RUNNER_1",
        direction="CE",
        strike_contract="NIFTY24000CE",
        entry_price=24000.0,
        entry_time="2026-11-20T09:20:00",
        current_sl=24004.0,  # locked at entry + 4.0
        initial_sl=23950.0,
        target_price=24100.0,
        lots=2,
        is_runner_mode=True,
        half_booked=True,
        trail_locked=True,
        runner_trailing_sl=52.0,
        opt_entry_ltp=50.0,
        opt_peak_hwm=70.0,
        opt_current_ltp=68.0,
    )

    # Initial bar evaluation - atr_1m = 10.0 (bar does not hit target 24100 or spot SL 24004)
    # peak_excursion = 20.0, clamped_cushion = min(15.0, max(12.0, 7.0)) = 12.0
    # proposed_sl = 70.0 - 12.0 = 58.0 > 52.0 -> updates to 58.0
    state, payload = apm.evaluate_bar(
        bar_open=24050.0,
        bar_high=24065.0,
        bar_low=24045.0,
        bar_close=24060.0,
        bar_time_str="09:25:00",
        current_opt_ltp=68.0,
        atr_1m=10.0,
    )
    assert state == STATE_TRAIL_LOCK
    assert apm.payload.runner_trailing_sl == 58.0

    # Next bar: option price rises to 85.0 (HWM updates to 85.0)
    # peak_excursion = 35.0, clamped_cushion = min(15.0, max(12.0, 12.25)) = 12.25
    # proposed_sl = 85.0 - 12.25 = 72.75 > 58.0 -> updates to 72.75
    state2, payload2 = apm.evaluate_bar(
        bar_open=24060.0,
        bar_high=24090.0,
        bar_low=24055.0,
        bar_close=24085.0,
        bar_time_str="09:30:00",
        current_opt_ltp=85.0,
        atr_1m=10.0,
    )
    assert state2 == STATE_TRAIL_LOCK
    assert apm.payload.runner_trailing_sl == 72.75

    # Monotonicity test: market retraces (HWM stays 85.0, LTP drops to 75.0)
    # peak_excursion = 35.0, proposed_sl = 72.75 -> trailing stop does not decrease
    state3, payload3 = apm.evaluate_bar(
        bar_open=24085.0,
        bar_high=24086.0,
        bar_low=24070.0,
        bar_close=24072.0,
        bar_time_str="09:35:00",
        current_opt_ltp=75.0,
        atr_1m=10.0,
    )
    assert state3 == STATE_TRAIL_LOCK
    assert apm.payload.runner_trailing_sl == 72.75  # Did not decrease

    # Exit trigger: LTP drops to 70.0 <= runner_trailing_sl (72.75)
    state_exit, payload_exit = apm.evaluate_bar(
        bar_open=24072.0,
        bar_high=24075.0,
        bar_low=24060.0,
        bar_close=24065.0,
        bar_time_str="09:40:00",
        current_opt_ltp=70.0,
        atr_1m=10.0,
    )
    assert state_exit == STATE_COOL_OFF
    assert payload_exit["exit_reason"] == "RUNNER_HWM_TRAILING_EXIT"
    assert apm.state == STATE_COOL_OFF


def test_apm_runner_pe_monotonic_trailing_ratchet(tmp_path: Path):
    """Verifies that a PE (Put) runner position operates monotonically and exits correctly."""
    wal = tmp_path / "apm_runner_pe_wal.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = STATE_TRAIL_LOCK
    apm.payload = PositionPayload(
        position_id="PE_RUNNER_1",
        direction="PE",
        strike_contract="BANKNIFTY52000PE",
        entry_price=52000.0,
        entry_time="2026-11-20T10:00:00",
        current_sl=51996.0,  # entry 52000 - 4.0
        initial_sl=52150.0,
        target_price=51700.0,
        lots=2,
        is_runner_mode=True,
        half_booked=True,
        trail_locked=True,
        runner_trailing_sl=103.0,  # entry 100 + friction 3
        opt_entry_ltp=100.0,
        opt_peak_hwm=130.0,
        opt_current_ltp=125.0,
    )

    # atr_1m = 12.0
    # peak_excursion = 30.0, clamped_cushion = min(18.0, max(12.0, 10.5)) = 12.0
    # proposed_sl = 130.0 - 12.0 = 118.0
    state, payload = apm.evaluate_bar(
        bar_open=51900.0,
        bar_high=51910.0,
        bar_low=51800.0,
        bar_close=51820.0,
        bar_time_str="10:05:00",
        current_opt_ltp=125.0,
        atr_1m=12.0,
    )
    assert state == STATE_TRAIL_LOCK
    assert apm.payload.runner_trailing_sl == 118.0

    # Put premium surges to 155.0 (HWM updates to 155.0)
    # peak_excursion = 55.0, clamped_cushion = min(18.0, max(12.0, 19.25)) = 18.0
    # proposed_sl = 155.0 - 18.0 = 137.0
    state2, payload2 = apm.evaluate_bar(
        bar_open=51820.0,
        bar_high=51830.0,
        bar_low=51720.0,
        bar_close=51730.0,
        bar_time_str="10:10:00",
        current_opt_ltp=155.0,
        atr_1m=12.0,
    )
    assert state2 == STATE_TRAIL_LOCK
    assert apm.payload.runner_trailing_sl == 137.0

    # Put retraces, LTP drops to 135.0 <= 137.0
    state_exit, payload_exit = apm.evaluate_bar(
        bar_open=51730.0,
        bar_high=51760.0,
        bar_low=51725.0,
        bar_close=51750.0,
        bar_time_str="10:15:00",
        current_opt_ltp=135.0,
        atr_1m=12.0,
    )
    assert state_exit == STATE_COOL_OFF
    assert payload_exit["exit_reason"] == "RUNNER_HWM_TRAILING_EXIT"
    assert apm.state == STATE_COOL_OFF


def test_apm_target_hit_projects_runner_state_without_claiming_a_fill(tmp_path: Path):
    """Target touch arms runner protection but does not claim partial execution."""
    wal = tmp_path / "apm_target_to_runner.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = STATE_IN_FLIGHT
    apm.payload = PositionPayload(
        position_id="TARGET_RUNNER_1",
        direction="CE",
        strike_contract="NIFTY24000CE",
        entry_price=24000.0,
        entry_time="2026-11-20T09:20:00",
        current_sl=23950.0,
        initial_sl=23950.0,
        target_price=24100.0,
        lots=2,
        is_runner_mode=True,
        half_booked=False,
        trail_locked=False,
        opt_entry_ltp=50.0,
        opt_current_ltp=100.0,
        opt_peak_hwm=100.0,
    )

    # Bar touches target_price 24100.0 (high=24105.0)
    state, payload_dict = apm.evaluate_bar(
        bar_open=24070.0,
        bar_high=24105.0,
        bar_low=24065.0,
        bar_close=24095.0,
        bar_time_str="09:25:00",
        current_opt_ltp=100.0,
        atr_1m=10.0,
    )
    assert state == STATE_TRAIL_LOCK
    assert apm.payload.runner_target_reached is True
    assert apm.payload.half_booked is False
    assert apm.payload.trail_locked is True
    assert apm.payload.current_sl == 24004.0  # entry + 4
    assert apm.payload.tranche_1_pnl_pts is None
    assert apm.payload.remaining_lots is None
    assert apm.payload.remaining_quantity is None
    assert apm.payload.actual_quantity_status == "UNKNOWN_NO_FILL_SOURCE"
    assert apm.payload.runner_trailing_sl is not None


def test_apm_wal_recovery_roundtrip_runner_state(tmp_path: Path):
    """Verifies that runner position state is persisted and cleanly reloaded from WAL."""
    wal = tmp_path / "apm_wal_recovery.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = STATE_TRAIL_LOCK
    apm.payload = PositionPayload(
        position_id="WAL_TEST_1",
        direction="CE",
        strike_contract="NIFTY24000CE",
        entry_price=24000.0,
        entry_time="2026-11-20T09:20:00",
        current_sl=24004.0,
        initial_sl=23950.0,
        target_price=24100.0,
        lots=2,
        remaining_lots=1,
        remaining_quantity=65,
        is_runner_mode=True,
        half_booked=True,
        trail_locked=True,
        runner_trailing_sl=65.0,
        opt_entry_ltp=50.0,
        opt_peak_hwm=80.0,
        opt_current_ltp=75.0,
    )
    apm._persist_wal_atomic(force_sync=True)

    # Recover in fresh instance
    apm.close()
    apm_recovered = ActivePositionManager(wal_path=str(wal))
    assert apm_recovered.payload is not None
    assert apm_recovered.payload.position_id == "WAL_TEST_1"
    assert apm_recovered.payload.is_runner_mode is True
    assert apm_recovered.payload.runner_target_reached is True
    assert apm_recovered.payload.half_booked is False
    assert apm_recovered.state == "RECOVERY_BLOCKED"
    assert apm_recovered.payload.runner_trailing_sl == 65.0
    assert apm_recovered.payload.opt_peak_hwm == 80.0
    assert apm_recovered.payload.remaining_lots is None
    assert apm_recovered.payload.remaining_quantity is None


def test_apm_wal_crash_before_replacement_fault_injection(tmp_path: Path):
    """Fault injection: Crash/failure before os.replace leaves previous valid WAL intact."""
    import os
    from unittest.mock import patch
    wal = tmp_path / "apm_wal_crash_test.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = STATE_IN_FLIGHT
    apm.payload = PositionPayload(
        position_id="CRASH_BASE_1",
        direction="CE",
        strike_contract="NIFTY24000CE",
        entry_price=24000.0,
        entry_time="2026-11-20T09:20:00",
        current_sl=23950.0,
        initial_sl=23950.0,
        target_price=24100.0,
        lots=2,
    )
    apm._persist_wal_atomic(force_sync=True)
    assert wal.exists()

    # Now simulate a crash during os.replace on subsequent update
    apm.payload.current_sl = 23980.0
    with patch("os.replace", side_effect=OSError("Simulated crash before atomic replace")):
        try:
            apm._persist_wal_atomic(force_sync=True)
        except OSError:
            pass

    # Fresh instance must recover the original uncorrupted WAL state cleanly
    apm.close()
    apm_recovered = ActivePositionManager(wal_path=str(wal))
    assert apm_recovered.payload is not None
    assert apm_recovered.payload.position_id == "CRASH_BASE_1"
    assert apm_recovered.payload.current_sl == 23950.0


def test_apm_wal_lot_accounting_remains_unknown_after_target_touch(tmp_path: Path):
    """Target touch does not alter actual lot quantities without fill evidence."""
    wal = tmp_path / "apm_wal_lots_test.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = STATE_IN_FLIGHT
    apm.payload = PositionPayload(
        position_id="LOT_TEST_1",
        direction="CE",
        strike_contract="NIFTY24000CE",
        entry_price=24000.0,
        entry_time="2026-11-20T09:20:00",
        current_sl=23950.0,
        initial_sl=23950.0,
        target_price=24100.0,
        lots=4,
        lot_size=65,
        total_quantity=260,
        remaining_lots=4,
        remaining_quantity=260,
        is_runner_mode=True,
    )
    apm._persist_wal_atomic(force_sync=True)

    # Trigger the runner target milestone via evaluate_bar touching target_price
    state, payload = apm.evaluate_bar(
        bar_open=24050.0,
        bar_high=24105.0,
        bar_low=24040.0,
        bar_close=24095.0,
        bar_time_str="09:25:00",
        current_opt_ltp=100.0,
        atr_1m=10.0,
    )
    assert state == STATE_TRAIL_LOCK
    assert apm.payload.runner_target_reached is True
    assert apm.payload.half_booked is False
    assert apm.payload.remaining_lots == 4
    assert apm.payload.remaining_quantity == 260
    assert apm.payload.lots == 4
    assert apm.payload.total_quantity == 260

    # Recover from WAL and ensure accounting persisted accurately
    apm.close()
    apm_recovered = ActivePositionManager(wal_path=str(wal))
    assert apm_recovered.state == "RECOVERY_BLOCKED"
    assert apm_recovered.payload.runner_target_reached is True
    assert apm_recovered.payload.remaining_lots is None
    assert apm_recovered.payload.remaining_quantity is None


def _write_terminal_payload_wal(path: Path, state: str, *, cool_until: str | None = None) -> None:
    payload = {
        "position_id": "stale-position", "direction": "CE", "strike_contract": "NIFTY CE",
        "entry_price": 25000.0, "entry_time": "2026-11-20T09:20:00",
        "current_sl": 24980.0, "initial_sl": 24980.0, "target_price": 25040.0,
    }
    path.write_text(json.dumps({
        "state": state, "payload": payload,
        "trade_history": [], "daily_trade_count": 0,
        "cool_off_until": cool_until,
    }))


@pytest.mark.parametrize("terminal_state", [STATE_COOL_OFF, STATE_LIQUIDATED, STATE_STANDBY])
def test_recovery_with_terminal_state_and_position_payload_blocks_entry(tmp_path: Path, terminal_state: str):
    """A terminal state carrying a stale position is uncertain, never flat."""
    wal = tmp_path / f"terminal-{terminal_state}.json"
    future_cooloff = "2099-01-01T00:00:00"
    _write_terminal_payload_wal(
        wal, terminal_state,
        cool_until=future_cooloff if terminal_state == STATE_COOL_OFF else None,
    )

    recovered = ActivePositionManager(wal_path=str(wal))

    assert recovered.state == STATE_RECOVERY_BLOCKED
    assert recovered.payload is not None
    assert recovered.payload.position_id == "stale-position"
    assert recovered.arm_and_enter(
        "new", "CE", "NIFTY CE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is False


def test_successful_liquidation_persists_terminal_state_and_empty_payload_once(tmp_path: Path, monkeypatch):
    wal = tmp_path / "single-liquidation-snapshot.json"
    apm = ActivePositionManager(wal_path=str(wal))
    apm.state = "EXIT_PENDING"
    apm.payload = PositionPayload(
        position_id="complete", direction="CE", strike_contract="NIFTY CE",
        entry_price=25000.0, entry_time="2026-11-20T09:20:00",
        current_sl=24980.0, initial_sl=24980.0, target_price=25040.0,
    )
    captured = []
    original_persist = apm._persist_wal_atomic_impl

    def capture_snapshot(force_sync=True):
        captured.append((apm.state, apm.payload is None, len(apm.trade_history)))
        return original_persist(force_sync=force_sync)

    monkeypatch.setattr(apm, "_persist_wal_atomic_impl", capture_snapshot)
    state, summary = apm.liquidate(cooldown_seconds=0)

    assert state == STATE_LIQUIDATED
    assert summary["position_id"] == "complete"
    assert captured == [(STATE_LIQUIDATED, True, 1)]
    apm.close()
    recovered = ActivePositionManager(wal_path=str(wal))
    assert recovered.state == STATE_LIQUIDATED
    assert recovered.payload is None
    assert len(recovered.trade_history) == 1
    assert recovered.arm_and_enter(
        "after-liquidation", "PE", "NIFTY PE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is True


def _active_exit_pending_apm(tmp_path: Path, name: str) -> ActivePositionManager:
    apm = ActivePositionManager(wal_path=str(tmp_path / name))
    apm.state = "EXIT_PENDING"
    apm.payload = PositionPayload(
        position_id="uncertain", direction="CE", strike_contract="NIFTY CE",
        entry_price=25000.0, entry_time="2026-11-20T09:20:00",
        current_sl=24980.0, initial_sl=24980.0, target_price=25040.0,
    )
    apm._persist_wal_atomic(force_sync=True)
    return apm


def test_liquidation_replace_failure_keeps_old_active_wal_and_blocks_recovery(tmp_path: Path, monkeypatch):
    import os

    apm = _active_exit_pending_apm(tmp_path, "liquidation-replace-before.json")
    monkeypatch.setattr(os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("before replace")))

    with pytest.raises(OSError, match="before replace"):
        apm.liquidate(cooldown_seconds=0)

    assert apm.state == STATE_RECOVERY_BLOCKED
    assert apm.payload is not None and apm.payload.position_id == "uncertain"
    on_disk = json.loads(apm.wal_path.read_text())
    assert on_disk["state"] == "EXIT_PENDING"
    assert on_disk["payload"]["position_id"] == "uncertain"
    apm.close()
    recovered = ActivePositionManager(wal_path=str(apm.wal_path))
    assert recovered.state == STATE_RECOVERY_BLOCKED
    assert recovered.payload is not None
    assert recovered.arm_and_enter(
        "new", "PE", "NIFTY PE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is False


def test_liquidation_post_replace_directory_fsync_failure_blocks_current_manager(tmp_path: Path, monkeypatch):
    import os

    apm = _active_exit_pending_apm(tmp_path, "liquidation-dir-fsync.json")
    real_fsync = os.fsync
    fsync_calls = 0

    def fail_directory_fsync(fd):
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("directory sync uncertain")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="directory sync uncertain"):
        apm.liquidate(cooldown_seconds=0)

    assert fsync_calls == 2  # file sync and then post-replace directory sync
    assert apm.state == STATE_RECOVERY_BLOCKED
    assert apm.recovery_status == "DURABILITY_UNKNOWN"
    assert apm.payload is not None and apm.payload.position_id == "uncertain"
    assert apm.arm_and_enter(
        "new", "PE", "NIFTY PE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is False
    # The replacement image itself is coherent; restart sees either this whole
    # terminal snapshot or the prior EXIT_PENDING snapshot, never a split image.
    on_disk = json.loads(apm.wal_path.read_text())
    assert (
        on_disk["state"] == STATE_LIQUIDATED and on_disk["payload"] is None
    ) or (
        on_disk["state"] == "EXIT_PENDING" and on_disk["payload"] is not None
    )
    apm.close()
    recovered = ActivePositionManager(wal_path=str(apm.wal_path))
    if on_disk["state"] == "EXIT_PENDING":
        assert recovered.state == STATE_RECOVERY_BLOCKED
        assert recovered.payload is not None
        assert recovered.arm_and_enter(
            "new", "PE", "NIFTY PE", 25000.0, "2026-11-20T09:30:00", lots=1,
        ) is False
    else:
        assert recovered.state == STATE_LIQUIDATED
        assert recovered.recovery_status == "DURABLE"
        assert recovered.payload is None
        assert [row["position_id"] for row in recovered.trade_history].count("uncertain") == 1
        recovered.close()
        reloaded = ActivePositionManager(wal_path=str(apm.wal_path))
        assert reloaded.state == STATE_LIQUIDATED
        assert reloaded.recovery_status == "DURABLE"
        assert reloaded.payload is None
        assert [row["position_id"] for row in reloaded.trade_history].count("uncertain") == 1
        reloaded.close()


def _create_completed_terminal_wal(tmp_path: Path, name: str, *, cooldown_seconds: float = 0) -> Path:
    apm = _active_exit_pending_apm(tmp_path, name)
    apm.liquidate(cooldown_seconds=cooldown_seconds)
    wal_path = apm.wal_path
    apm.close()
    return wal_path


def test_terminal_recovery_fsync_failure_blocks_entry(tmp_path: Path, monkeypatch):
    import os

    wal = _create_completed_terminal_wal(tmp_path, "terminal-recovery-fsync.json")
    monkeypatch.setattr(os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("recovery fsync failed")))

    recovered = ActivePositionManager(wal_path=str(wal))

    assert recovered.state == STATE_RECOVERY_BLOCKED
    assert recovered.recovery_status == "DURABILITY_UNKNOWN"
    assert recovered.payload is None
    assert recovered.arm_and_enter(
        "new", "PE", "NIFTY PE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is False


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "mismatch"])
def test_terminal_recovery_requires_one_matching_trade_history_row(tmp_path: Path, corruption: str):
    import copy

    wal = _create_completed_terminal_wal(tmp_path, f"terminal-{corruption}.json")
    data = json.loads(wal.read_text())
    if corruption == "missing":
        data["last_completed_trade"] = None
    elif corruption == "duplicate":
        data["trade_history"].append(copy.deepcopy(data["trade_history"][0]))
    else:
        data["trade_history"][0]["position_id"] = "different-position"
    wal.write_text(json.dumps(data))

    recovered = ActivePositionManager(wal_path=str(wal))

    assert recovered.state == STATE_RECOVERY_BLOCKED
    assert recovered.recovery_status == "RECOVERY_BLOCKED"
    assert recovered.arm_and_enter(
        "new", "PE", "NIFTY PE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is False


def test_cooloff_resumes_only_after_terminal_snapshot_revalidation(tmp_path: Path):
    wal = _create_completed_terminal_wal(tmp_path, "terminal-cooloff.json", cooldown_seconds=600)

    recovered = ActivePositionManager(wal_path=str(wal))

    assert recovered.state == STATE_COOL_OFF
    assert recovered.recovery_status == "DURABLE"
    assert recovered.payload is None
    assert recovered.arm_and_enter(
        "blocked-by-cooloff", "CE", "NIFTY CE", 25000.0, "2026-11-20T09:30:00", lots=1,
    ) is False


def _enter_gear2_setup(apm: ActivePositionManager, position_id: str = "P") -> None:
    assert apm.arm_and_enter(
        position_id, "CE", "NIFTY CE", 25000.0, "2026-11-20T09:20:00",
        opt_quote={"ltp": 100.0}, session_gear="GEAR_2_TREND", lots=1,
    ) is True


def _key(row: dict) -> tuple[str, int]:
    return row["position_id"], row.get("reentry_count", 0)


def test_gear2_pullback_reentry_preserves_distinct_immutable_wal_legs(tmp_path: Path):
    """Same setup can complete a first leg and one re-entry without identity collision."""
    wal = tmp_path / "gear2-reentry-legs.json"
    apm = ActivePositionManager(wal_path=str(wal))
    _enter_gear2_setup(apm)

    # Real giveback path records leg 0 and moves the setup into pullback wait.
    apm.evaluate_tick(25010.0, current_opt_ltp=130.0, tick_time_str="2026-11-20T10:00:00")
    state, _ = apm.evaluate_tick(
        25011.0, current_opt_ltp=119.5, tick_time_str="2026-11-20T10:01:00",
    )
    assert state == STATE_PULLBACK_WAIT
    assert [_key(row) for row in apm.trade_history] == [("P", 0)]
    leg0 = json.loads(json.dumps(apm.trade_history[0]))

    # A genuine manager restart must preserve the in-flight setup and leg history.
    apm.close()
    recovered = ActivePositionManager(wal_path=str(wal))
    assert recovered.state == STATE_PULLBACK_WAIT
    assert recovered.payload is not None
    assert [_key(row) for row in recovered.trade_history] == [("P", 0)]

    state, reentered = recovered.evaluate_pullback_reentry(
        current_spot=25012.0,
        bounce_confirmed=True,
        current_opt_quote={"ltp": 120.0},
        current_time_str="2026-11-20T10:02:00",
    )
    assert state == STATE_IN_FLIGHT
    assert reentered is not None and reentered["reentry_count"] == 1
    assert recovered.trade_history[0] == leg0

    # Simulate the second leg's observed exit transition; no fill or PnL is asserted.
    recovered.payload.exit_price = 25015.0
    recovered.payload.exit_reason = "SECOND_LEG_EXIT"
    recovered.payload.exit_time = "2026-11-20T10:04:00"
    recovered._transition_to(STATE_EXIT_PENDING)
    state, _ = recovered.liquidate(cooldown_seconds=0)
    assert state == STATE_LIQUIDATED
    assert [_key(row) for row in recovered.trade_history] == [("P", 0), ("P", 1)]
    assert recovered.trade_history[0] == leg0
    assert recovered.last_completed_trade == recovered.trade_history[1]

    # Terminal recovery validates the summary against exactly leg 1 and is repeatable.
    recovered.close()
    for _ in range(2):
        restarted = ActivePositionManager(wal_path=str(wal))
        assert restarted.state == STATE_LIQUIDATED
        assert restarted.recovery_status == "DURABLE"
        assert restarted.payload is None
        assert [_key(row) for row in restarted.trade_history] == [("P", 0), ("P", 1)]
        assert restarted.trade_history[0] == leg0
        assert restarted.last_completed_trade == restarted.trade_history[1]
        restarted.close()


def test_liquidation_blocks_conflicting_history_row_for_same_leg_key(tmp_path: Path):
    apm = ActivePositionManager(wal_path=str(tmp_path / "conflicting-leg.json"))
    _enter_gear2_setup(apm)
    apm.payload.reentry_count = 1
    apm.payload.exit_reason = "NEW_CONTENT"
    apm.payload.exit_price = 25010.0
    apm.trade_history = [{
        **apm.payload.__dict__, "exit_reason": "CONFLICTING_CONTENT",
        "position_id": "P", "reentry_count": 1,
    }]
    apm.state = STATE_EXIT_PENDING

    with pytest.raises(ValueError, match="conflicting completed leg"):
        apm.liquidate(cooldown_seconds=0)

    assert apm.state == STATE_RECOVERY_BLOCKED
    assert apm.payload is not None
    assert [_key(row) for row in apm.trade_history] == [("P", 1)]
    assert apm.arm_and_enter(
        "blocked-entry", "CE", "NIFTY CE", 25000.0, "2026-11-20T10:05:00", lots=1,
    ) is False


def test_identical_completed_leg_retry_does_not_duplicate_history(tmp_path: Path):
    apm = ActivePositionManager(wal_path=str(tmp_path / "identical-leg-retry.json"))
    _enter_gear2_setup(apm)
    apm.payload.reentry_count = 1
    apm.payload.exit_reason = "RETRY"
    apm.payload.exit_price = 25010.0
    apm.payload.exit_time = "2026-11-20T10:04:00"
    retry_summary = dict(apm.payload.__dict__)
    apm.trade_history = [dict(retry_summary)]
    apm.state = STATE_EXIT_PENDING

    state, summary = apm.liquidate(cooldown_seconds=0)

    assert state == STATE_LIQUIDATED
    assert summary == retry_summary
    assert len(apm.trade_history) == 1
    assert apm.trade_history[0] == retry_summary


def test_pullback_abort_with_only_leg_zero_recovers_without_missing_leg_one_requirement(tmp_path: Path):
    wal = tmp_path / "aborted-before-reentry.json"
    apm = ActivePositionManager(wal_path=str(wal))
    _enter_gear2_setup(apm)
    apm.evaluate_tick(25010.0, current_opt_ltp=130.0, tick_time_str="2026-11-20T10:00:00")
    apm.evaluate_tick(25011.0, current_opt_ltp=119.5, tick_time_str="2026-11-20T10:01:00")
    assert apm.state == STATE_PULLBACK_WAIT
    assert [_key(row) for row in apm.trade_history] == [("P", 0)]

    state, payload = apm.evaluate_pullback_reentry(
        current_spot=24990.0, bounce_confirmed=False, atr_1m=10.0,
    )
    assert state == STATE_LIQUIDATED
    assert payload is None

    apm.close()
    restarted = ActivePositionManager(wal_path=str(wal))
    assert restarted.state == STATE_LIQUIDATED
    assert restarted.recovery_status == "DURABLE"
    assert restarted.payload is None
    assert [_key(row) for row in restarted.trade_history] == [("P", 0)]
    restarted.close()
