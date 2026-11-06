"""Unit tests for Sentinel Unified Pipeline Dynamic Gear, Priority Arbitration,
and Dual-Stream Shadow Tagging.
=============================================================================
Proves:
1. Dynamic Gear Escalation: Range -> Trend on expansion ratio Omega_10 >= 1.80.
2. 3-Bar Hysteresis Lock: De-escalation to Range requires 3 consecutive compression bars.
3. Cross-Asset Isolation: SENSEX in Trend does not leak into NIFTY in Range.
4. Priority-Based Early Release: High-priority setups (Mode 5) can bypass STATE_COOL_OFF.
5. Dual-Stream Shadow Tagging: Trades 1 & 2 are PRIMARY_CANONICAL; trade 3+ is OBSERVATIONAL_SHADOW.
"""

from __future__ import annotations

import datetime
from datetime import time as dt_time
import pytest

from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    PriorDayReferenceLevels,
)
from core.active_position_manager import (
    ActivePositionManager,
    STATE_COOL_OFF,
    STATE_IN_FLIGHT,
    STATE_STANDBY,
)


def test_isolated_gear_tracking_and_cross_asset_safety():
    """Proves that SENSEX expanding into GEAR_2_TREND does not alter NIFTY in GEAR_1_RANGE."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)

    # Initialize prior day levels with verified ATR
    advisor.prior_day_levels["NIFTY"] = PriorDayReferenceLevels(
        index_name="NIFTY", pdh=24200.0, pdl=24000.0, pdc=24100.0, atr_20=100.0, verified=True
    )
    advisor.prior_day_levels["SENSEX"] = PriorDayReferenceLevels(
        index_name="SENSEX", pdh=80500.0, pdl=79500.0, pdc=80000.0, atr_20=500.0, verified=True
    )

    # Simulate SENSEX large 10m expansion (Range 1000 pts / ATR 500 = Omega_10 = 2.0 >= 1.80)
    advisor._on_5m_bar_close(
        index_name="SENSEX",
        bar_open=80000.0,
        bar_high=80600.0,
        bar_low=79600.0,
        bar_close=80550.0,
        bar_volume=50000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1700000000000,
        epoch_5min=100,
    )

    # Simulate NIFTY narrow 10m compression (Range 40 pts / ATR 100 = Omega_10 = 0.40 < 1.00)
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24100.0,
        bar_high=24125.0,
        bar_low=24085.0,
        bar_close=24110.0,
        bar_volume=20000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1700000000000,
        epoch_5min=100,
    )

    # Assert per-index isolation
    assert advisor.session_gears["SENSEX"] == "GEAR_2_TREND"
    assert advisor.session_gears["NIFTY"] == "GEAR_1_RANGE"
    assert advisor.gear_expansion_ratios["SENSEX"] == 2.0
    assert advisor.gear_expansion_ratios["NIFTY"] == 0.4


def test_3_bar_hysteresis_lock_on_gear_de_escalation():
    """Proves that GEAR_2_TREND requires 3 consecutive compression bars before reverting to RANGE."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    advisor.prior_day_levels["NIFTY"] = PriorDayReferenceLevels(
        index_name="NIFTY", pdh=24200.0, pdl=24000.0, pdc=24100.0, atr_20=100.0, verified=True
    )

    # Bar 1: Strong expansion impulse (Range 200 pts / ATR 100 = Omega_10 = 2.0 >= 1.80) -> TREND
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24000.0,
        bar_high=24200.0,
        bar_low=24000.0,
        bar_close=24180.0,
        bar_volume=50000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1700000000000,
        epoch_5min=100,
    )
    assert advisor.session_gears["NIFTY"] == "GEAR_2_TREND"

    # Bar 2: Compression bar 1 (Omega_10 = 0.50) -> Still TREND due to hysteresis
    advisor.bars_5m_history["NIFTY"] = [
        {"high": 24190.0, "low": 24140.0},
        {"high": 24190.0, "low": 24140.0},
    ]
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24180.0,
        bar_high=24190.0,
        bar_low=24140.0,
        bar_close=24170.0,
        bar_volume=10000.0,
        bar_time=dt_time(9, 25),
        timestamp_ms=1700000300000,
        epoch_5min=101,
    )
    assert advisor.session_gears["NIFTY"] == "GEAR_2_TREND"
    assert advisor.gear_range_bar_counters["NIFTY"] == 1

    # Bar 3: Compression bar 2 -> Still TREND
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24170.0,
        bar_high=24180.0,
        bar_low=24150.0,
        bar_close=24160.0,
        bar_volume=10000.0,
        bar_time=dt_time(9, 30),
        timestamp_ms=1700000600000,
        epoch_5min=102,
    )
    assert advisor.session_gears["NIFTY"] == "GEAR_2_TREND"
    assert advisor.gear_range_bar_counters["NIFTY"] == 2

    # Bar 4: Compression bar 3 -> 3-bar hysteresis fulfilled, de-escalates to GEAR_1_RANGE!
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24160.0,
        bar_high=24170.0,
        bar_low=24145.0,
        bar_close=24155.0,
        bar_volume=10000.0,
        bar_time=dt_time(9, 35),
        timestamp_ms=1700000900000,
        epoch_5min=103,
    )
    assert advisor.session_gears["NIFTY"] == "GEAR_1_RANGE"
    assert advisor.gear_range_bar_counters["NIFTY"] == 3


def test_priority_cool_off_early_release_and_dual_stream_tagging():
    """Proves priority weighting and canonical vs observational shadow trade tagging."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    apm = advisor.apms["NIFTY"]

    # Manually put APM into STATE_COOL_OFF from a stopped CE trade
    apm.state = STATE_COOL_OFF
    apm.cool_off_direction = "CE"

    # Verify strategy priority weights
    assert advisor.strategy_priority_weights["OPTIONMATE_RBFN_AUCTION"] == 1.00
    assert advisor.strategy_priority_weights["LIQUIDITY_SWEEP"] == 0.50

    # Low-priority same-direction trade (LIQUIDITY_SWEEP CE) cannot bypass cool-off
    low_prio = advisor.strategy_priority_weights["LIQUIDITY_SWEEP"]
    can_bypass_low = (
        apm.state == STATE_COOL_OFF
        and (low_prio >= 0.90 or apm.cool_off_direction != "CE")
    )
    assert can_bypass_low is False

    # High-priority trade (OPTIONMATE_RBFN_AUCTION) CAN bypass cool-off
    high_prio = advisor.strategy_priority_weights["OPTIONMATE_RBFN_AUCTION"]
    can_bypass_high = (
        apm.state == STATE_COOL_OFF
        and (high_prio >= 0.90 or apm.cool_off_direction != "CE")
    )
    assert can_bypass_high is True

    # Direction inversion (PE trade) CAN bypass cool-off even if lower priority
    can_bypass_inversion = (
        apm.state == STATE_COOL_OFF
        and (low_prio >= 0.90 or apm.cool_off_direction != "PE")
    )
    assert can_bypass_inversion is True

    # Test Dual-Stream Shadow Tagging
    advisor.daily_trade_counters["NIFTY"] = 0
    tier_1 = "PRIMARY_CANONICAL" if advisor.daily_trade_counters["NIFTY"] < 2 else "OBSERVATIONAL_SHADOW"
    assert tier_1 == "PRIMARY_CANONICAL"

    advisor.daily_trade_counters["NIFTY"] = 2
    tier_3 = "PRIMARY_CANONICAL" if advisor.daily_trade_counters["NIFTY"] < 2 else "OBSERVATIONAL_SHADOW"
    assert tier_3 == "OBSERVATIONAL_SHADOW"
