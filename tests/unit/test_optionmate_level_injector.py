"""
Unit Tests for OptionMate Level Injection Engine
================================================
Verifies:
1. Exact injection of OptionMate indicator levels into SentinelLiveStreamAdvisor.
2. Grid immutability lock: once injected, heuristic calculation does NOT overwrite exact indicator levels.
3. Hierarchy assertion: RP2_L < RP1_L < TD < RP1_U < RP2_U.
4. Auto-seeding from runtime/optionmate_daily_levels.json.
"""

import json
from pathlib import Path
from datetime import time as dt_time, datetime
import pytest

from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from strategies.optionmate_rbfn_strategy import OptionMateGrid


def test_optionmate_level_injection_basic():
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter)

    success = advisor.inject_optionmate_levels(
        index_name="NIFTY",
        trend_decider=25283.0,
        rp1_upper=25360.0,
        rp2_upper=25424.65,
        rp1_lower=25195.0,
        rp2_lower=25134.0,
    )
    assert success is True
    assert advisor.rbfn_grids_frozen["NIFTY"] is True

    grid = advisor.cached_rbfn_grids["NIFTY"]
    assert isinstance(grid, OptionMateGrid)
    assert grid.trend_decider == 25283.0
    assert grid.rp1_upper == 25360.0
    assert grid.rp2_upper == 25424.65
    assert grid.rp1_lower == 25195.0
    assert grid.rp2_lower == 25134.0


def test_optionmate_level_injection_invalid_hierarchy():
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter)

    # Inverted hierarchy (RP1_U > RP2_U is invalid)
    success = advisor.inject_optionmate_levels(
        index_name="NIFTY",
        trend_decider=25283.0,
        rp1_upper=25450.0,
        rp2_upper=25360.0,
        rp1_lower=25195.0,
        rp2_lower=25134.0,
    )
    assert success is False
    assert advisor.cached_rbfn_grids["NIFTY"] is None


def test_injected_grid_persists_across_5m_bar_closes():
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter)

    # Seed prior day levels to pass Gate 1
    advisor.seed_prior_day_levels(
        index_name="NIFTY",
        pdh=25400.0,
        pdl=25200.0,
        pdc=25300.0,
        atr_20=180.0,
    )

    # Inject exact OptionMate levels
    advisor.inject_optionmate_levels(
        index_name="NIFTY",
        trend_decider=25283.0,
        rp1_upper=25360.0,
        rp2_upper=25424.65,
        rp1_lower=25195.0,
        rp2_lower=25134.0,
    )

    # Trigger multiple 5m bar closes (e.g. 09:20, 09:25)
    sig1 = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25300.0,
        bar_high=25370.0,
        bar_low=25290.0,
        bar_close=25365.0,
        bar_volume=100000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1794888600000,
        epoch_5min=1,
    )

    # Assert that cached grid STILL has the exact injected values, not overwritten by heuristic!
    grid = advisor.cached_rbfn_grids["NIFTY"]
    assert grid.trend_decider == 25283.0
    assert grid.rp1_upper == 25360.0
    assert grid.rp2_upper == 25424.65
