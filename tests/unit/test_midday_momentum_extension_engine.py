"""Unit tests for MiddayMomentumExtensionEngine.

Work Item: FEAT-SENTINEL-MIDDAY-MOMENTUM-001
Branch: feat/sentinel-unified-upstox-stream-advisor
Baseline PR: #987

Verifies:
1. Deterministic evaluation at 12:30 IST.
2. Invariant zero lookahead (drift calculated strictly from 09:15 open to 12:30 print).
3. Bullish drift (>= +0.60%) generates LONG (CE) continuation with 1:1 reward-to-risk (40 pts target / 40 pts stop).
4. Bearish drift (<= -0.60%) generates SHORT (PE) continuation with 1:1 reward-to-risk (40 pts target / 40 pts stop).
5. Drift between -0.60% and +0.60% generates ABSTAIN (avoids chop).
6. Strike resolution rounds strictly to Round-100 strikes for liquidity.
7. Non-negotiable repository safety invariants are guaranteed:
   - read_only = True
   - is_order_action = False
   - broker_api_called = False
   - allowed_for_live_execution = False
"""

import pytest
from datetime import time as dt_time
from core.midday_momentum_extension_engine import (
    MiddayMomentumExtensionEngine,
    MiddayDirection,
    MiddayMomentumSignal,
)


def test_outside_evaluation_window():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    engine.set_session_open(24000.0)

    # 10:15 IST - should return None
    sig = engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(10, 15),
        date_str="2026-10-15",
    )
    assert sig is None

    # 12:29 IST - should return None
    sig = engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 29),
        date_str="2026-10-15",
    )
    assert sig is None

    # 12:31 IST - should return None
    sig = engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 31),
        date_str="2026-10-15",
    )
    assert sig is None


def test_bullish_drift_long_setup():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    open_p = 24000.0
    engine.set_session_open(open_p)

    # +0.83% drift at 12:30 (24200 vs 24000)
    current_spot = 24200.0
    sig = engine.evaluate_at_1230(
        current_spot=current_spot,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30),
        date_str="2026-10-15",
    )

    assert sig is not None
    assert sig.direction == MiddayDirection.LONG
    assert sig.recommended_option_type == "CE"
    assert sig.recommended_strike == 24200.0  # nearest 100
    assert sig.drift_pct > 0.0060
    assert sig.target_pts == 40.0
    assert sig.stop_pts == 40.0
    assert sig.target_price == 24240.0
    assert sig.stop_price == 24160.0

    # Safety invariants
    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False
    assert sig.allowed_for_live_execution is False


def test_bearish_drift_short_setup():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    open_p = 24000.0
    engine.set_session_open(open_p)

    # -0.83% drift at 12:30 (23800 vs 24000)
    current_spot = 23800.0
    sig = engine.evaluate_at_1230(
        current_spot=current_spot,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30),
        date_str="2026-10-15",
    )

    assert sig is not None
    assert sig.direction == MiddayDirection.SHORT
    assert sig.recommended_option_type == "PE"
    assert sig.recommended_strike == 23800.0
    assert sig.drift_pct < -0.0060
    assert sig.target_pts == 40.0
    assert sig.stop_pts == 40.0
    assert sig.target_price == 23760.0
    assert sig.stop_price == 23840.0

    # Safety invariants
    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False
    assert sig.allowed_for_live_execution is False


def test_low_drift_abstain():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    open_p = 24000.0
    engine.set_session_open(open_p)

    # +0.20% drift at 12:30 (24050 vs 24000)
    current_spot = 24050.0
    sig = engine.evaluate_at_1230(
        current_spot=current_spot,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30),
        date_str="2026-10-15",
    )

    assert sig is not None
    assert sig.direction == MiddayDirection.ABSTAIN
    assert sig.recommended_option_type == "NONE"


def test_strike_liquidity_rounding():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    # 24240 should round to 24200
    assert engine.resolve_liquid_round_strike(24240.0) == 24200.0
    # 24260 should round to 24300
    assert engine.resolve_liquid_round_strike(24260.0) == 24300.0
    # 24250 should round to 24200 or 24300 (even round)
    assert engine.resolve_liquid_round_strike(24250.0) in (24200.0, 24300.0)


def test_idempotent_session_evaluation():
    engine = MiddayMomentumExtensionEngine(index_name="NIFTY")
    engine.set_session_open(24000.0)

    sig1 = engine.evaluate_at_1230(
        current_spot=24200.0,
        timestamp_ms=1793188800000,
        wall_time=dt_time(12, 30, 10),
        date_str="2026-10-15",
    )
    sig2 = engine.evaluate_at_1230(
        current_spot=24210.0,
        timestamp_ms=1793188810000,
        wall_time=dt_time(12, 30, 20),
        date_str="2026-10-15",
    )

    # Idempotent: returns cached signal from the first evaluation
    assert sig1 is not None
    assert sig2 is not None
    assert sig1 == sig2
