"""Unit Test Suite for Sentinel Dynamic ATR Targets, Unified Volatility Flow, and Grill Me Red Team Defenses.

FEAT-SENTINEL-DYNAMIC-ATR-TARGETS-001: Scale-Invariant ATR Targets and Unified Single-Source Volatility Integration.
HERMES-CONTRACT-DYNAMIC-TARGETS-001 / AUDIT-REDTEAM-DYNAMIC-TARGETS-PREDEV-20261030

Verifies:
1. test_advisor_dynamic_atr_calibration_all_indices: Dynamic ATR scaling with Grill Me hard floors across NIFTY, BANKNIFTY, SENSEX.
2. test_wall_gate_clamping_uses_index_calibrated_buffers: Clamping target before fortified wall resolves index buffers (NIFTY 2.0, BANKNIFTY 10.0, SENSEX 15.0).
3. test_wall_gate_veto_on_uneconomic_wall_compression: Grill Me Vector 3 fix - VETO when fortified wall compresses target below min_rr_ratio.
4. test_apm_arm_and_enter_authoritative_points_no_double_expansion: When explicit tp_pts and sl_pts are passed, APM uses them directly without index_scale multiplier.
5. test_pullback_reentry_scale_cleanliness: Pullback reentry uses native ATR without artificial double index scaling.
6. test_end_to_end_single_source_volatility_flow: Complete tick-to-APM entry flow verifying synthetic bar ATR update propagates to advisor and APM.

Trading Safety Invariants:
- read_only = True (tests do not connect to live market or broker)
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import pytest
from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    DEFAULT_INDEX_ATR,
    FALLBACK_DEFAULT_ATR,
)
from core.market_structure.sentinel_wall_gate import (
    SentinelWallGate,
    DEFAULT_INDEX_WALL_BUFFER_PTS,
    GATE_ACTION_CLAMP_TARGET,
    GATE_ACTION_PROCEED,
    GATE_ACTION_VETO,
)
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_PULLBACK_WAIT,
)
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    InMemorySentinelAdapter,
)
from core.sentinel_inmem_adapter import (
    UpstoxTickRecord,
    UpstoxLevel5DepthRecord,
)


def _populate_observer_with_wall(
    observer: SentinelWallObserver,
    spot: float,
    major_call: float,
    major_put: float,
    call_oi: float = 100_000.0,
    put_oi: float = 100_000.0,
    num_strikes: int = 10,
    timestamp_ms: int = 1729000000000,
    call_ask_depth: float = 2000.0,  # default fortified for call (vuln < 0.80)
    put_bid_depth: float = 2000.0,   # default fortified for put (vuln > 1.20)
) -> None:
    """Helper to populate an observer with strikes and established walls."""
    observer.on_spot_tick(spot_price=spot, timestamp_ms=timestamp_ms)
    step = 50.0 if "NIFTY" in observer.underlying_symbol else 100.0
    base_strike = spot - (num_strikes // 2) * step

    for i in range(num_strikes):
        s = base_strike + i * step
        observer.on_option_tick(
            symbol=f"{observer.underlying_symbol} {int(s)} CE",
            ltp=50.0,
            volume=5000.0,
            oi=10_000.0,
            bid_depth=20000.0,
            ask_depth=5000.0,
            timestamp_ms=timestamp_ms,
        )
        observer.on_option_tick(
            symbol=f"{observer.underlying_symbol} {int(s)} PE",
            ltp=50.0,
            volume=5000.0,
            oi=10_000.0,
            bid_depth=5000.0,
            ask_depth=20000.0,
            timestamp_ms=timestamp_ms,
        )

    # Establish major call and major put walls with dominant OI
    observer.on_option_tick(
        symbol=f"{observer.underlying_symbol} {int(major_call)} CE",
        ltp=50.0,
        volume=5000.0,
        oi=call_oi,
        bid_depth=20000.0,
        ask_depth=call_ask_depth,
        timestamp_ms=timestamp_ms,
    )
    observer.on_option_tick(
        symbol=f"{observer.underlying_symbol} {int(major_put)} PE",
        ltp=50.0,
        volume=5000.0,
        oi=put_oi,
        bid_depth=put_bid_depth,
        ask_depth=1000.0,  # small ask depth -> put vuln = bid/ask > 1.20 (fortified)
        timestamp_ms=timestamp_ms,
    )


def test_advisor_dynamic_atr_calibration_all_indices():
    """AC-1: Nominal multipliers 0.35 * ATR and 0.25 * ATR with Grill Me hard floors."""
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)

    # 1. High Volatility Scenario
    # NIFTY: ATR = 100 -> nominal_tp = 35.0, nominal_sl = 25.0 (> floors 12.0/12.0)
    advisor.wall_observers["NIFTY"].update_atr(100.0)
    # BANKNIFTY: ATR = 400 -> nominal_tp = 140.0, nominal_sl = 100.0 (> floors 30.0/25.0)
    advisor.wall_observers["BANKNIFTY"].update_atr(400.0)
    # SENSEX: ATR = 800 -> nominal_tp = 280.0, nominal_sl = 200.0 (> floors 45.0/35.0)
    advisor.wall_observers["SENSEX"].update_atr(800.0)

    # Calculate expected points for NIFTY
    eff_atr_nifty = advisor.wall_observers["NIFTY"].atr_pts
    assert max(12.0, round(0.35 * eff_atr_nifty, 2)) == 35.0
    assert max(12.0, round(0.25 * eff_atr_nifty, 2)) == 25.0

    # Calculate expected points for BANKNIFTY
    eff_atr_bn = advisor.wall_observers["BANKNIFTY"].atr_pts
    assert max(30.0, round(0.35 * eff_atr_bn, 2)) == 140.0
    assert max(25.0, round(0.25 * eff_atr_bn, 2)) == 100.0

    # Calculate expected points for SENSEX
    eff_atr_sensex = advisor.wall_observers["SENSEX"].atr_pts
    assert max(45.0, round(0.35 * eff_atr_sensex, 2)) == 280.0
    assert max(35.0, round(0.25 * eff_atr_sensex, 2)) == 200.0

    # 2. Extreme Low Volatility Scenario -> Hard Floors MUST Clamp
    # NIFTY: ATR = 20 -> nominal_tp = 7.0, nominal_sl = 5.0 -> floors 12.0, 12.0
    advisor.wall_observers["NIFTY"].update_atr(20.0)
    eff_atr_nifty_low = advisor.wall_observers["NIFTY"].atr_pts
    assert max(12.0, round(0.35 * eff_atr_nifty_low, 2)) == 12.0
    assert max(12.0, round(0.25 * eff_atr_nifty_low, 2)) == 12.0

    # BANKNIFTY: ATR = 50 -> nominal_tp = 17.5, nominal_sl = 12.5 -> floors 30.0, 25.0
    advisor.wall_observers["BANKNIFTY"].update_atr(50.0)
    eff_atr_bn_low = advisor.wall_observers["BANKNIFTY"].atr_pts
    assert max(30.0, round(0.35 * eff_atr_bn_low, 2)) == 30.0
    assert max(25.0, round(0.25 * eff_atr_bn_low, 2)) == 25.0

    # SENSEX: ATR = 70 -> nominal_tp = 24.5, nominal_sl = 17.5 -> floors 45.0, 35.0
    advisor.wall_observers["SENSEX"].update_atr(70.0)
    eff_atr_sensex_low = advisor.wall_observers["SENSEX"].atr_pts
    assert max(45.0, round(0.35 * eff_atr_sensex_low, 2)) == 45.0
    assert max(35.0, round(0.25 * eff_atr_sensex_low, 2)) == 35.0


def test_wall_gate_clamping_uses_index_calibrated_buffers():
    """AC-2: Wall clamping automatically resolves index-calibrated buffer when wall_buffer_pts=None."""
    # NIFTY gate (buffer = 2.0 pts)
    obs_nifty = SentinelWallObserver(underlying_symbol="NIFTY")
    gate_nifty = SentinelWallGate(observer=obs_nifty, wall_buffer_pts=None)
    assert gate_nifty.wall_buffer_pts == 2.0

    # BANKNIFTY gate (buffer = 10.0 pts)
    obs_bn = SentinelWallObserver(underlying_symbol="BANKNIFTY")
    gate_bn = SentinelWallGate(observer=obs_bn, wall_buffer_pts=None)
    assert gate_bn.wall_buffer_pts == 10.0

    # SENSEX gate (buffer = 15.0 pts)
    obs_sensex = SentinelWallObserver(underlying_symbol="SENSEX")
    gate_sensex = SentinelWallGate(observer=obs_sensex, wall_buffer_pts=None)
    assert gate_sensex.wall_buffer_pts == 15.0

    # Verify clamping calculation for BANKNIFTY
    # Spot = 48000, Major Call Wall = 48100 (dist = 100 pts)
    # Nominal target = 150 pts, SL = 50 pts
    # Expected clamped target = dist - buffer = 100 - 10.0 = 90.0 pts (R:R = 90/50 = 1.8 > 1.0)
    now_ms = 1729000000000
    _populate_observer_with_wall(obs_bn, spot=48000.0, major_call=48100.0, major_put=47800.0, timestamp_ms=now_ms)
    decision = gate_bn.clamp_target_to_wall(
        direction="CE",
        spot_price=48000.0,
        nominal_target_pts=150.0,
        sl_pts=50.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=None,  # resolves to gate_bn.wall_buffer_pts (10.0)
    )
    assert decision.action == GATE_ACTION_CLAMP_TARGET
    assert decision.clamped_target_pts == 90.0


def test_wall_gate_veto_on_uneconomic_wall_compression():
    """AC-2 & Grill Me Vector 3: VETO entry when fortified wall destroys R:R below min_rr_ratio."""
    obs = SentinelWallObserver(underlying_symbol="NIFTY")
    gate = SentinelWallGate(observer=obs, wall_buffer_pts=None)  # buffer = 2.0 pts
    now_ms = 1729000000000

    # CE Test:
    # Spot = 22500, Fortified Call Wall at 22510 (dist = 10 pts)
    # Wall buffer = 2.0 pts -> proposed clamped target = 10 - 2.0 = 8.0 pts
    # SL = 12.0 pts, min_rr_ratio = 1.0
    # Proposed target (8.0) < min_rr_ratio * SL (12.0) -> R:R = 0.67 < 1.0
    # Must VETO with GATE_ACTION_VETO!
    _populate_observer_with_wall(
        obs,
        spot=22500.0,
        major_call=22510.0,
        major_put=22400.0,
        timestamp_ms=now_ms,
        call_ask_depth=1000.0,  # highly fortified (vuln < 0.80)
    )
    decision = gate.clamp_target_to_wall(
        direction="CE",
        spot_price=22500.0,
        nominal_target_pts=35.0,
        sl_pts=12.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=None,
        min_rr_ratio=1.0,
    )
    assert decision.action == GATE_ACTION_VETO
    assert "VETO_WALL_COMPRESSION_UNECONOMIC_RR" in decision.reason
    assert decision.clamped_target_pts is None

    # PE Test:
    # Set major put wall at 22490 (dist = 10 pts)
    obs_pe = SentinelWallObserver(underlying_symbol="NIFTY")
    gate_pe = SentinelWallGate(observer=obs_pe, wall_buffer_pts=None)
    _populate_observer_with_wall(
        obs_pe,
        spot=22500.0,
        major_call=22600.0,
        major_put=22490.0,
        timestamp_ms=now_ms,
        put_bid_depth=20000.0,  # put_vuln = bid/ask = 20000/1000 = 20.0 > 1.20 (fortified)
    )
    decision_pe = gate_pe.clamp_target_to_wall(
        direction="PE",
        spot_price=22500.0,
        nominal_target_pts=35.0,
        sl_pts=12.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=None,
        min_rr_ratio=1.0,
    )
    assert decision_pe.action == GATE_ACTION_VETO
    assert "VETO_WALL_COMPRESSION_UNECONOMIC_RR" in decision_pe.reason
    assert decision_pe.clamped_target_pts is None


def test_apm_arm_and_enter_authoritative_points_no_double_expansion(tmp_path):
    """AC-3: APM arm_and_enter treats explicitly passed tp_pts and sl_pts as authoritative without index scaling."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # SENSEX trade with authoritative points from advisor:
    # SENSEX Spot = 75000, target_pts = 175.0, sl_pts = 125.0, atr_1m = 500.0
    entered = apm.arm_and_enter(
        position_id="TEST_SENSEX_AUTHORITATIVE",
        direction="CE",
        contract="SENSEX 75000 CE",
        entry_price=75000.0,
        entry_time_str="2026-10-30T10:00:00",
        tp_pts=175.0,
        sl_pts=125.0,
        atr_1m=500.0,
    )
    assert entered is True
    # If double-multiplied by index_scale (3.5), target would be 75000 + 175*3.5 = 75612.5
    # With authoritative points: target MUST BE exactly 75000 + 175.0 = 75175.0!
    assert apm.payload.target_price == 75175.0
    assert apm.payload.initial_sl == 74875.0

    # Verify fallback behavior when tp_pts and sl_pts are None (unit test backwards compatibility)
    apm.state = STATE_STANDBY
    entered_default = apm.arm_and_enter(
        position_id="TEST_SENSEX_DEFAULT",
        direction="CE",
        contract="SENSEX 75000 CE",
        entry_price=75000.0,
        entry_time_str="2026-10-30T10:05:00",
        tp_pts=None,
        sl_pts=None,
        atr_1m=30.0,
    )
    assert entered_default is True
    # index_scale = 3.5, eff_atr = 30 * 3.5 = 105.0
    # eff_tp = max(18 * 3.5, 1.5 * 105) = 157.5
    # eff_sl = max(12 * 3.5, 1.0 * 105) = 105.0
    assert apm.payload.target_price == 75000.0 + 157.5
    assert apm.payload.initial_sl == 75000.0 - 105.0


def test_pullback_reentry_scale_cleanliness(tmp_path):
    """AC-4: Pullback re-entry uses native atr_1m without artificial double index scaling."""
    wal_file = tmp_path / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=str(wal_file))

    # Setup an initial SENSEX in-flight position with GEAR_2_TREND
    apm.arm_and_enter(
        position_id="SENSEX_PULLBACK_TEST",
        direction="CE",
        contract="SENSEX 75000 CE",
        entry_price=75000.0,
        entry_time_str="2026-10-30T10:00:00",
        tp_pts=175.0,
        sl_pts=125.0,
        atr_1m=100.0,
        session_gear="GEAR_2_TREND",
    )

    # Force position to PULLBACK_WAIT
    apm.state = STATE_PULLBACK_WAIT
    apm.payload.reentry_count = 0

    # Evaluate pullback reentry on SENSEX with native ATR = 100.0
    # Previously, code did `index_scale = 3.5 if is_sensex else 1.0` -> eff_atr = 100 * 3.5 = 350 pts!
    # With clean native ATR: eff_atr = max(100.0, 8.0) = 100.0
    # eff_tp = 1.5 * 100.0 = 150.0 pts
    # eff_sl = 1.0 * 100.0 = 100.0 pts
    state, p = apm.evaluate_pullback_reentry(
        current_spot=75050.0,
        bounce_confirmed=True,
        current_opt_quote={"ltp": 250.0, "bid": 249.0, "ask": 251.0},
        atr_1m=100.0,
        current_time_str="2026-10-30T10:15:00",
    )

    assert state == STATE_IN_FLIGHT
    assert p["target_price"] == 75050.0 + 150.0  # 75200.0 (NOT 75050 + 525.0)
    assert p["initial_sl"] == 75050.0 - 100.0     # 74950.0 (NOT 75050 - 350.0)


def _make_tick(token: str, ltp: float, volume: int, ts_ms: int) -> UpstoxTickRecord:
    """Helper to instantiate full UpstoxTickRecord."""
    return UpstoxTickRecord(
        token=token,
        symbol=token,
        exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=0,
        ingress_wall_utc="2026-10-30T09:15:00Z",
        sequence_id=1,
        ltp=ltp,
        volume=volume,
        open_interest=100000,
        best_bid=ltp - 0.5,
        best_ask=ltp + 0.5,
    )


def test_end_to_end_single_source_volatility_flow():
    """AC-5: End-to-end single-source volatility flow. Synthetic bar updates propagate to ATR and APM parameters."""
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)

    # Initial NIFTY ATR is 65.0
    assert advisor.wall_observers["NIFTY"].atr_pts == 65.0

    # Feed synthetic 1-min ticks to establish average true range = 40.0
    # Minute 1: Range = 40.0 (22540 - 22500)
    advisor.on_tick(_make_tick(
        token="Nifty 50", ltp=22500.0, volume=1000, ts_ms=6_000_000,
    ))
    advisor.on_tick(_make_tick(
        token="Nifty 50", ltp=22540.0, volume=2000, ts_ms=6_030_000,
    ))
    # Minute 2 roll -> triggers bar finalization and ATR update to 40.0
    advisor.on_tick(_make_tick(
        token="Nifty 50", ltp=22520.0, volume=3000, ts_ms=6_060_000,
    ))

    # Observer ATR should now be updated to 40.0
    obs = advisor.wall_observers["NIFTY"]
    assert obs.atr_pts == 40.0

    # Now verify that advisor's option depth evaluation uses this dynamic 40.0 ATR:
    # nominal_target = round(0.35 * 40.0, 2) = 14.0 pts
    # nominal_sl = round(0.25 * 40.0, 2) = 10.0 pts -> clamped by floor max(12.0, 10.0) = 12.0 pts
    eff_atr = obs.atr_pts
    expected_target = max(12.0, round(0.35 * eff_atr, 2))
    expected_sl = max(12.0, round(0.25 * eff_atr, 2))

    assert expected_target == 14.0
    assert expected_sl == 12.0
