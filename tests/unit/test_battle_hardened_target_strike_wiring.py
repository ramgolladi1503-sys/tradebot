"""Unit and Hostile Tests for Battle-Hardened Target Strike & Marketable IOC Wiring in PR #987."""

from datetime import time as dt_time
import pytest
from core.midday_momentum_extension_engine import (
    MiddayMomentumExtensionEngine,
    MiddayDirection,
    MiddayMomentumSignal,
)


def test_geometric_target_strike_resolution_bullish():
    # Enabled with target_strike_mode=True and 50-pt strike resolution
    engine = MiddayMomentumExtensionEngine(
        index_name="NIFTY",
        target_pts=50.0,
        stop_pts=40.0,
        strike_round=50.0,
        target_strike_mode=True,
    )
    engine.set_session_open(24000.0)

    # Spot at 12:30 is 24200 (+0.83% drift)
    # Target spot is 24250.0 (+50 pts)
    # Target strike must be 24250 CE (The strike that becomes ATM at target!)
    sig = engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30),
        date_str="2026-11-04",
        morning_range=110.0,
    )

    assert sig is not None
    assert sig.direction == MiddayDirection.LONG
    assert sig.recommended_option_type == "CE"
    assert sig.recommended_strike == 24250.0
    assert sig.target_price == 24250.0
    assert sig.stop_price == 24160.0
    assert sig.order_type == "MARKETABLE_IOC_LIMIT"
    assert sig.ioc_slippage_cap == 0.30
    assert sig.max_spread_gate == 0.60


def test_geometric_target_strike_resolution_bearish():
    engine = MiddayMomentumExtensionEngine(
        index_name="NIFTY",
        target_pts=50.0,
        stop_pts=40.0,
        strike_round=50.0,
        target_strike_mode=True,
    )
    engine.set_session_open(24000.0)

    # Spot at 12:30 is 23800 (-0.83% drift)
    # Target spot is 23750.0 (-50 pts)
    # Target strike must be 23750 PE
    sig = engine.evaluate_at_1230(
        current_spot=23800.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30),
        date_str="2026-11-04",
        morning_range=120.0,
    )

    assert sig is not None
    assert sig.direction == MiddayDirection.SHORT
    assert sig.recommended_option_type == "PE"
    assert sig.recommended_strike == 23750.0
    assert sig.target_price == 23750.0
    assert sig.stop_price == 23840.0


def test_fail_closed_outside_window():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    engine.set_session_open(24000.0)

    # 12:29 must return None
    assert engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188799000,
        wall_time=dt_time(12, 29),
        date_str="2026-11-04",
    ) is None

    # 12:31 must return None
    assert engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188861000,
        wall_time=dt_time(12, 31),
        date_str="2026-11-04",
    ) is None


def test_strict_safety_invariants():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    engine.set_session_open(24000.0)
    sig = engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30),
        date_str="2026-11-04",
    )

    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False
    assert sig.allowed_for_live_execution is False
