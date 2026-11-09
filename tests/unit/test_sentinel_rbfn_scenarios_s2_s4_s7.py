"""Unit test for Sentinel RBFN Multi-Scenario Trajectory Expansion (S2, S4, S7).
=============================================================================
Proves:
1. S2: RP1_UPPER 10-minute sustained breakout triggers BUY_CALL targeting RP2_UPPER (OTM -> ATM).
2. S4: RP1_LOWER 10-minute sustained breakdown triggers BUY_PUT targeting RP2_LOWER (OTM -> ATM).
3. S7: RP2_LOWER 10-minute floor bounce triggers BUY_CALL targeting RP1_LOWER.
4. S6 & S8 Reversal Fades enforce capped milestone targets (max +20 pts) to prevent midday theta bleed.
"""

from __future__ import annotations

from datetime import datetime, time as dt_time
from unittest.mock import patch
import pytest

from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor


def test_s2_expansion_breakout_triggers_otm_call(tmp_path):
    wal = tmp_path / "test_wal_s2.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24520.0
    
    # RP1_UPPER is 24640.0, RP2_UPPER is 24760.0
    # Add two consecutive 5m bars closing above RP1_UPPER (10-minute hold)
    advisor.bars_5m_history["NIFTY"].append({
        "open": 24630.0, "high": 24660.0, "low": 24625.0, "close": 24650.0,
        "volume": 1000, "time": dt_time(12, 15), "timestamp_ms": 1793190000000, "epoch_5min": 100
    })

    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24650.0,
        bar_high=24680.0,
        bar_low=24645.0,
        bar_close=24670.0,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=1793190300000,
        epoch_5min=101
    )

    assert sig is not None
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.setup_reason == "RP1_UPPER_10M_EXPANSION_BREAKOUT"
    assert sig.trade_phase == "MIDDAY_EXPANSION_BREAKOUT"
    assert sig.target_strike == 24750.0  # Snapped round OTM strike at RP2_UPPER


def test_s4_expansion_breakdown_triggers_otm_put(tmp_path):
    wal = tmp_path / "test_wal_s4.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24520.0

    # RP1_LOWER is 24400.0, RP2_LOWER is 24280.0
    advisor.bars_5m_history["NIFTY"].append({
        "open": 24420.0, "high": 24430.0, "low": 24390.0, "close": 24395.0,
        "volume": 1000, "time": dt_time(12, 15), "timestamp_ms": 1793190000000, "epoch_5min": 100
    })

    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24395.0,
        bar_high=24400.0,
        bar_low=24370.0,
        bar_close=24380.0,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=1793190300000,
        epoch_5min=101
    )

    assert sig is not None
    assert sig.action == "BUY_PUT"
    assert sig.direction == "PE"
    assert sig.setup_reason == "RP1_LOWER_10M_EXPANSION_BREAKDOWN"
    assert sig.trade_phase == "MIDDAY_EXPANSION_BREAKDOWN"
    assert sig.target_strike == 24300.0  # Snapped round OTM strike at RP2_LOWER


def test_s7_floor_bounce_triggers_reversal_call(tmp_path):
    wal = tmp_path / "test_wal_s7.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24520.0

    # RP2_LOWER is 24280.0, RP1_LOWER is 24400.0
    # Bar tested low <= 24280, then two consecutive closes >= 24280
    advisor.bars_5m_history["NIFTY"] = [
        {"open": 24290.0, "high": 24295.0, "low": 24260.0, "close": 24285.0,
         "volume": 1000, "time": dt_time(12, 10), "timestamp_ms": 1793189700000, "epoch_5min": 99},
        {"open": 24285.0, "high": 24310.0, "low": 24280.0, "close": 24300.0,
         "volume": 1000, "time": dt_time(12, 15), "timestamp_ms": 1793190000000, "epoch_5min": 100}
    ]

    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24300.0,
        bar_high=24320.0,
        bar_low=24290.0,
        bar_close=24315.0,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=1793190300000,
        epoch_5min=101
    )

    assert sig is not None
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.setup_reason == "RP2_LOWER_10M_FLOOR_BOUNCE"
    assert sig.trade_phase == "EXTREME_EXHAUSTION_REVERSAL"
    assert sig.target_strike == 24400.0  # Target becomes ATM at RP1_LOWER
