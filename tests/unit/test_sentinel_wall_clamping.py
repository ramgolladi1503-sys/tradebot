"""Unit tests for Sentinel Option Wall Target Clamping.

Validates the adversarial invariants and mathematical boundaries defined in:
- Pre-Development Adversarial Gauntlet (5 Attackers vs 5 Reviewers)
- Attacker 1: Dynamic Wall Shifting (causal PIT immutable clamping contract)
- Attacker 2: Target Truncation Fallacy (min R:R ratio >= 1.0 enforcement)
- Attacker 3: Phantom Wall Noise (fortified wall criteria: major/secondary & vulnerability)
- Attacker 4: False Breakout Trap (fragile walls bypass clamping)
- Attacker 5: Race Condition & Feed Staleness (fail-closed / neutral fallback)
- Safety Invariants: read_only=True, is_order_action=False, broker_api_called=False
"""

import time
import pytest
from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    SentinelWallState,
    StrikeWallProfile,
)
from core.market_structure.sentinel_wall_gate import (
    SentinelWallGate,
    GATE_ACTION_PROCEED,
    GATE_ACTION_CLAMP_TARGET,
    GATE_ACTION_VETO,
)


def _build_test_observer(
    spot: float = 22500.0,
    strikes: list = None,
    atr_pts: float = 12.0,
    now_ms: int = 1729000000000,
) -> SentinelWallObserver:
    """Helper to populate an observer with deterministic strike depth and OI."""
    obs = SentinelWallObserver(
        underlying_symbol="NIFTY",
        atr_pts=atr_pts,
        min_strike_span=5,
        feed_freshness_max_skew_ms=60_000,
    )
    obs.on_spot_tick(spot_price=spot, timestamp_ms=now_ms)

    if strikes is None:
        strikes = [22400.0, 22450.0, 22500.0, 22550.0, 22600.0, 22650.0]

    for s in strikes:
        obs.on_option_tick(
            symbol=f"NIFTY {int(s)} CE",
            ltp=100.0,
            volume=5000.0,
            oi=50000.0,
            bid_depth=10000.0,
            ask_depth=10000.0,
            timestamp_ms=now_ms,
        )
        obs.on_option_tick(
            symbol=f"NIFTY {int(s)} PE",
            ltp=100.0,
            volume=5000.0,
            oi=50000.0,
            bid_depth=10000.0,
            ask_depth=10000.0,
            timestamp_ms=now_ms,
        )
    return obs


def test_clamping_call_wall_closer_than_nominal_tp():
    """Validates that a fortified call wall closer than nominal TP clamps target."""
    now_ms = 1729000000000
    spot = 22500.0
    obs = _build_test_observer(spot=spot, now_ms=now_ms)

    # Establish fortified Call wall at 22512.0 (distance = 12.0 pts)
    # Fortified call wall: vuln = ask_depth / bid_depth < 0.80
    obs.on_option_tick(
        symbol="NIFTY 22512 CE",
        ltp=80.0,
        volume=25000.0,
        oi=250000.0,  # Max Call OI
        bid_depth=25000.0,
        ask_depth=5000.0,  # vuln = 5000 / 25000 = 0.20 < 0.80
        timestamp_ms=now_ms,
    )
    obs.on_option_tick(
        symbol="NIFTY 22512 PE",
        ltp=80.0,
        volume=5000.0,
        oi=20000.0,
        bid_depth=2000.0,
        ask_depth=20000.0,
        timestamp_ms=now_ms,
    )

    gate = SentinelWallGate(observer=obs)

    # Nominal target = 18.0 pts, SL = 10.0 pts
    # Distance to wall = 12.0 pts. Wall buffer = 1.0 pt -> Clamped = 11.0 pts.
    # R:R = 11.0 / 10.0 = 1.1 >= min_rr (1.0).
    decision = gate.clamp_target_to_wall(
        direction="CE",
        spot_price=spot,
        nominal_target_pts=18.0,
        sl_pts=10.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=1.0,
        min_rr_ratio=1.0,
    )

    assert decision.action == GATE_ACTION_CLAMP_TARGET
    assert decision.clamped_target_pts == 11.0
    assert "CLAMP_TARGET_BEFORE_CALL_WALL" in decision.reason
    assert decision.read_only is True
    assert decision.is_order_action is False
    assert decision.broker_api_called is False


def test_clamping_rejected_by_min_rr_ratio():
    """Attacker 2 (Target Truncation Fallacy): Clamping rejected if sub-1.0 R:R."""
    now_ms = 1729000000000
    spot = 22500.0
    obs = _build_test_observer(spot=spot, now_ms=now_ms)

    # Fortified wall at 22508.0 (distance = 8.0 pts)
    obs.on_option_tick(
        symbol="NIFTY 22508 CE",
        ltp=85.0,
        volume=30000.0,
        oi=300000.0,
        bid_depth=25000.0,
        ask_depth=5000.0,  # vuln = 0.20 < 0.80 (fortified)
        timestamp_ms=now_ms,
    )
    gate = SentinelWallGate(observer=obs)

    # Nominal target = 15.0 pts, SL = 12.0 pts
    # Distance to wall = 8.0 pts. Buffer = 1.0 -> Proposed = 7.0 pts.
    # R:R = 7.0 / 12.0 = 0.58 < min_rr (1.0).
    # Clamping MUST be rejected to prevent negative mathematical expectancy.
    decision = gate.clamp_target_to_wall(
        direction="CE",
        spot_price=spot,
        nominal_target_pts=15.0,
        sl_pts=12.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=1.0,
        min_rr_ratio=1.0,
    )

    assert decision.action == GATE_ACTION_PROCEED
    assert decision.clamped_target_pts is None
    assert "CLAMP_REJECTED_SUB_MIN_RR" in decision.reason


def test_fragile_call_wall_bypasses_clamping_for_breakout():
    """Attacker 4 (False Breakout Trap): Fragile walls bypass clamping."""
    now_ms = 1729000000000
    spot = 22500.0
    obs = _build_test_observer(spot=spot, now_ms=now_ms)

    # Wall at 22512.0, but fragile:
    # High vulnerability (ask_depth >> bid_depth) and bullish depth supporting breakout (ratio >= 1.0)
    obs.on_option_tick(
        symbol="NIFTY 22512 CE",
        ltp=85.0,
        volume=30000.0,
        oi=200000.0,
        bid_depth=10000.0,
        ask_depth=20000.0,  # vuln = 2.0 >= 0.80
        timestamp_ms=now_ms,
    )
    obs.on_option_tick(
        symbol="NIFTY 22512 PE",
        ltp=85.0,
        volume=30000.0,
        oi=50000.0,
        bid_depth=5000.0,
        ask_depth=25000.0,  # bullish depth = 10000 + 25000 = 35000 vs bear = 20000 + 5000 = 25000 -> ratio = 1.4 >= 1.0
        timestamp_ms=now_ms,
    )
    gate = SentinelWallGate(observer=obs)

    decision = gate.clamp_target_to_wall(
        direction="CE",
        spot_price=spot,
        nominal_target_pts=18.0,
        sl_pts=10.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=1.0,
        min_rr_ratio=1.0,
    )

    assert decision.action == GATE_ACTION_PROCEED
    assert decision.clamped_target_pts is None
    assert "PROCEED_FRAGILE_WALL_NO_CLAMP" in decision.reason


def test_put_floor_clamping_for_pe():
    """Validates put floor clamping for PE short trades."""
    now_ms = 1729000000000
    spot = 22500.0
    obs = _build_test_observer(spot=spot, now_ms=now_ms)

    # Put floor at 22485.0 (distance = 15.0 pts below spot)
    # PE trade: SL = 10.0 pts, Nominal target = 20.0 pts
    # For put floor, vuln = pe_bid / pe_ask > 1.20 indicates strong put bids defending floor
    obs.on_option_tick(
        symbol="NIFTY 22485 PE",
        ltp=90.0,
        volume=40000.0,
        oi=300000.0,
        bid_depth=30000.0,
        ask_depth=5000.0,   # PE vuln = bid / ask = 6.0 > 1.20 (fortified floor)
        timestamp_ms=now_ms,
    )
    gate = SentinelWallGate(observer=obs)

    decision = gate.clamp_target_to_wall(
        direction="PE",
        spot_price=spot,
        nominal_target_pts=20.0,
        sl_pts=10.0,
        timestamp_ms=now_ms,
        wall_buffer_pts=1.0,
        min_rr_ratio=1.0,
    )

    assert decision.action == GATE_ACTION_CLAMP_TARGET
    assert decision.clamped_target_pts == 14.0  # 15.0 - 1.0 buffer
    assert "CLAMP_TARGET_BEFORE_PUT_WALL" in decision.reason


def test_clamping_fail_closed_on_unhealthy_observer():
    """Attacker 5 (Feed Staleness & Race Conditions): Bypasses clamping if feed stale."""
    now_ms = 1729000000000
    obs = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=10)
    obs.on_spot_tick(spot_price=22500.0, timestamp_ms=now_ms)
    gate = SentinelWallGate(observer=obs)

    decision = gate.clamp_target_to_wall(
        direction="CE",
        spot_price=22500.0,
        nominal_target_pts=15.0,
        sl_pts=10.0,
        timestamp_ms=now_ms,
    )

    assert decision.action == GATE_ACTION_PROCEED
    assert decision.clamped_target_pts is None
    assert "BYPASS_UNHEALTHY_OBSERVER" in decision.reason
    assert decision.read_only is True
    assert decision.is_order_action is False
    assert decision.broker_api_called is False
