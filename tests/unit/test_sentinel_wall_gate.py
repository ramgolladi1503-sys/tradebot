"""Unit and invariant tests for SentinelWallGate."""

import time
import pytest

from core.market_structure.sentinel_wall_observer import SentinelWallObserver
from core.market_structure.sentinel_wall_gate import (
    SentinelWallGate,
    GATE_ACTION_PROCEED,
    GATE_ACTION_VETO,
    GATE_ACTION_WARN,
    GATE_ACTION_CONFIRM_BREACH,
    GATE_ACTION_TIGHTEN_RUNNER,
)


def _populate_observer_with_walls(
    observer: SentinelWallObserver,
    now_ms: int,
    call_wall_strike: float = 73500.0,
    put_wall_strike: float = 72500.0,
    call_vuln_fortified: bool = True,
    put_vuln_fortified: bool = True,
):
    """Helper to populate >= 10 strikes with controllable call/put wall characteristics."""
    strikes = [72000.0 + i * 100.0 for i in range(21)]  # 72000 to 74000
    for s in strikes:
        # Base background OI
        c_oi = 50000.0
        p_oi = 50000.0
        c_bid, c_ask = 300.0, 300.0
        p_bid, p_ask = 300.0, 300.0

        if s == call_wall_strike:
            c_oi = 500000.0  # Dominant call wall
            if call_vuln_fortified:
                # Fortified call wall: Low vulnerability (high bid depth, low ask depth)
                c_bid, c_ask = 800.0, 100.0
            else:
                # Fragile call wall: High vulnerability (low bid depth, high ask depth)
                c_bid, c_ask = 100.0, 800.0

        if s == put_wall_strike:
            p_oi = 500000.0  # Dominant put wall
            if put_vuln_fortified:
                # Fortified floor: Strong put bid depth
                p_bid, p_ask = 800.0, 100.0
            else:
                # Fragile floor: High vuln
                p_bid, p_ask = 100.0, 800.0

        observer.on_option_tick(
            f"SENSEX {int(s)} CE 29 OCT 26",
            oi=c_oi,
            volume=10000.0,
            bid_depth=c_bid,
            ask_depth=c_ask,
            timestamp_ms=now_ms,
        )
        observer.on_option_tick(
            f"SENSEX {int(s)} PE 29 OCT 26",
            oi=p_oi,
            volume=10000.0,
            bid_depth=p_bid,
            ask_depth=p_ask,
            timestamp_ms=now_ms,
        )


def test_wall_gate_fail_closed_on_unhealthy_observer():
    """Unhealthy or empty observer defaults to PROCEED (neutral bypass) without raising."""
    observer = SentinelWallObserver(underlying_symbol="SENSEX")
    gate = SentinelWallGate(observer=observer)
    
    decision = gate.evaluate_entry_gate("CE", 73000.0, 1000)
    assert decision.action == GATE_ACTION_PROCEED
    assert "BYPASS_UNHEALTHY_OBSERVER" in decision.reason
    assert decision.read_only is True
    assert decision.is_order_action is False


def test_wall_gate_veto_adverse_call_wall():
    """Buying CE directly below a fortified Call Wall is VETOED."""
    now_ms = int(time.time() * 1000)
    observer = SentinelWallObserver(underlying_symbol="SENSEX", atr_pts=100.0)
    observer.on_spot_tick(73450.0, now_ms)  # 50 pts below 73500 (0.50 ATR <= 0.75 ATR)
    _populate_observer_with_walls(observer, now_ms, call_wall_strike=73500.0, call_vuln_fortified=True)

    gate = SentinelWallGate(observer=observer, proximity_veto_atr=0.75)
    decision = gate.evaluate_entry_gate("CE", 73450.0, now_ms)

    assert decision.action == GATE_ACTION_VETO
    assert "VETO_FORTIFIED_CALL_WALL" in decision.reason
    assert decision.major_wall_strike == 73500.0
    assert decision.proximity_pts == 50.0
    assert decision.proximity_atr == 0.50


def test_wall_gate_veto_adverse_put_wall():
    """Buying PE directly above a fortified Put Wall floor is VETOED."""
    now_ms = int(time.time() * 1000)
    observer = SentinelWallObserver(underlying_symbol="SENSEX", atr_pts=100.0)
    observer.on_spot_tick(72550.0, now_ms)  # 50 pts above 72500 (0.50 ATR <= 0.75 ATR)
    _populate_observer_with_walls(observer, now_ms, put_wall_strike=72500.0, put_vuln_fortified=True)

    gate = SentinelWallGate(observer=observer, proximity_veto_atr=0.75)
    decision = gate.evaluate_entry_gate("PE", 72550.0, now_ms)

    assert decision.action == GATE_ACTION_VETO
    assert "VETO_FORTIFIED_PUT_WALL" in decision.reason
    assert decision.major_wall_strike == 72500.0
    assert decision.proximity_pts == 50.0
    assert decision.proximity_atr == 0.50


def test_wall_gate_confirm_call_wall_breach():
    """Breaking through a fragile Call Wall confirms breakout continuation."""
    now_ms = int(time.time() * 1000)
    observer = SentinelWallObserver(underlying_symbol="SENSEX", atr_pts=100.0)
    observer.on_spot_tick(73510.0, now_ms)  # Spot has breached 73500
    _populate_observer_with_walls(observer, now_ms, call_wall_strike=73500.0, call_vuln_fortified=False)

    gate = SentinelWallGate(observer=observer)
    decision = gate.evaluate_entry_gate("CE", 73510.0, now_ms)

    assert decision.action == GATE_ACTION_CONFIRM_BREACH
    assert "CALL_WALL_BREACH_CONFIRMED" in decision.reason


def test_wall_gate_tighten_runner_trailing_stop():
    """Active runner approaching opposing fortified wall triggers trailing stop tightening."""
    now_ms = int(time.time() * 1000)
    observer = SentinelWallObserver(underlying_symbol="SENSEX", atr_pts=100.0)
    observer.on_spot_tick(73460.0, now_ms)  # 40 pts from 73500 Call Wall (0.40 ATR <= 0.50 ATR)
    _populate_observer_with_walls(observer, now_ms, call_wall_strike=73500.0, call_vuln_fortified=True)

    gate = SentinelWallGate(observer=observer, runner_tighten_atr=0.50)
    decision = gate.evaluate_runner_tightening("CE", 73460.0, now_ms)

    assert decision.action == GATE_ACTION_TIGHTEN_RUNNER
    assert "RUNNER_TIGHTEN_RECOMMENDED" in decision.reason
    assert decision.major_wall_strike == 73500.0


def test_wall_gate_safety_invariants():
    """Gate decision strictly preserves trading safety invariants."""
    observer = SentinelWallObserver(underlying_symbol="SENSEX")
    gate = SentinelWallGate(observer=observer)
    decision = gate.evaluate_entry_gate("CE", 73000.0, 1000)

    assert decision.read_only is True
    assert decision.is_order_action is False
    assert decision.broker_api_called is False
    assert decision.edge_certification_status == "NO_CERTIFIED_EDGE"
