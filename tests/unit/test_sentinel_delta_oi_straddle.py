"""Unit and regression tests for Sentinel Intraday Delta-OI Velocity and Straddle Breakeven."""

import time
import pytest
from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    SentinelWallState,
    StraddleBreakevenProfile,
)


def test_delta_oi_velocity_and_unwinding():
    """Verify causal rolling Delta-OI velocity calculation and unwinding flags."""
    obs = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=2)
    obs.on_spot_tick(spot_price=24500.0, timestamp_ms=1000)

    # Base time: 10:00:00 AM (e.g. 1,700,000,000,000 ms)
    base_ts = 1_700_000_000_000

    # Initial high open interest at 24600 CE (100,000 contracts) and 24400 PE (100,000 contracts)
    obs.on_option_tick("NIFTY 24600 CE", ltp=100.0, volume=5000.0, oi=100_000.0, timestamp_ms=base_ts)
    obs.on_option_tick("NIFTY 24400 PE", ltp=100.0, volume=5000.0, oi=100_000.0, timestamp_ms=base_ts)

    # Advance 4 minutes (240,000 ms): Call writers panic and unwind 20,000 contracts (-20%)
    adv_ts = base_ts + 240_000
    obs.on_option_tick("NIFTY 24600 CE", ltp=140.0, volume=25000.0, oi=80_000.0, timestamp_ms=adv_ts)
    obs.on_option_tick("NIFTY 24400 PE", ltp=70.0, volume=10000.0, oi=110_000.0, timestamp_ms=adv_ts)

    # Compute wall state
    state = obs.compute_wall_state(force_recompute=True)
    assert state.is_valid is False or state.status == "INSUFFICIENT_COVERAGE"  # Only 2 strikes fed

    # Check the 24600 CE profile
    c_prof = state.wall_density_map[24600.0]
    assert c_prof.call_oi == 80_000.0
    assert c_prof.call_oi_delta_5m == -20_000.0
    assert c_prof.is_call_unwinding is True  # -20,000 < -0.05 * 80,000

    # Check the 24400 PE profile (put accumulation, not unwinding)
    p_prof = state.wall_density_map[24400.0]
    assert p_prof.put_oi == 110_000.0
    assert p_prof.put_oi_delta_5m == 10_000.0
    assert p_prof.is_put_unwinding is False


def test_straddle_breakeven_and_market_maker_stress():
    """Verify ATM straddle breakeven boundaries and market maker stress score."""
    obs = SentinelWallObserver(underlying_symbol="NIFTY", atr_pts=60.0, min_strike_span=2)
    obs.on_spot_tick(spot_price=24500.0, timestamp_ms=1000)

    # ATM Strike: 24500
    # CE LTP: 80.0, PE LTP: 70.0 -> Combined Straddle = 150.0 pts
    # Upper Breakeven = 24650.0, Lower Breakeven = 24350.0
    obs.on_option_tick("NIFTY 24500 CE", ltp=80.0, volume=10000.0, oi=50000.0, timestamp_ms=2000)
    obs.on_option_tick("NIFTY 24500 PE", ltp=70.0, volume=10000.0, oi=50000.0, timestamp_ms=2000)

    # Inside Range scenario
    state1 = obs.compute_wall_state(force_recompute=True)
    sb1 = state1.straddle_profile
    assert sb1.atm_strike == 24500.0
    assert sb1.straddle_premium == 150.0
    assert sb1.upper_breakeven == 24650.0
    assert sb1.lower_breakeven == 24350.0
    assert sb1.spot_position == "INSIDE_RANGE"
    assert sb1.is_pin_risk is True  # 24500 == spot
    assert state1.market_maker_stress_score == 0.0

    # Bullish Squeeze Breakout scenario: Spot surges to 24710 (> 24650)
    obs.on_spot_tick(spot_price=24710.0, timestamp_ms=3000)
    state2 = obs.compute_wall_state(force_recompute=True)
    sb2 = state2.straddle_profile
    assert sb2.spot_position == "ABOVE_UPPER"
    assert sb2.distance_to_upper_pts == -60.0  # 60 pts above upper breakeven
    assert state2.market_maker_stress_score == 1.0  # (24710 - 24650) / 60.0 ATR = 1.0 (Full Bullish MM Stress)


def test_option_lead_lag_aggression():
    """Verify detection of sudden ATM option buying volume surges."""
    obs = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=2)
    obs.on_spot_tick(spot_price=24500.0, timestamp_ms=1000)

    base_ts = 1_700_000_000_000
    # Initial baseline volume: 10,000 contracts
    obs.on_option_tick("NIFTY 24500 CE", ltp=80.0, volume=10_000.0, oi=50000.0, bid_depth=5000.0, ask_depth=2000.0, timestamp_ms=base_ts)
    obs.on_option_tick("NIFTY 24500 PE", ltp=70.0, volume=10_000.0, oi=50000.0, bid_depth=2000.0, ask_depth=5000.0, timestamp_ms=base_ts)

    # 2 minutes later: CE volume explodes to 35,000 contracts (+25,000 contracts surge) with net bullish depth
    adv_ts = base_ts + 120_000
    obs.on_option_tick("NIFTY 24500 CE", ltp=95.0, volume=35_000.0, oi=48000.0, bid_depth=8000.0, ask_depth=2000.0, timestamp_ms=adv_ts)

    state = obs.compute_wall_state(force_recompute=True)
    c_prof = state.wall_density_map[24500.0]
    assert c_prof.call_volume == 35_000.0
    assert c_prof.call_volume_surge_ratio >= 2.0
    assert c_prof.is_call_aggressive_buy is True
    assert c_prof.is_put_aggressive_buy is False
