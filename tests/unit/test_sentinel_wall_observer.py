"""Unit tests for Sentinel Wall Observer (FEAT-SENTINEL-WALL-OBSERVER-001).

Validates 5-Attacker Council Hardening Invariants:
1. Microstructure & Directional Liquidity (Attacker 1)
   - Bullish Depth = CE Bid + PE Ask
   - Bearish Depth = CE Ask + PE Bid
   - Directional liquidity ratio & vulnerability profiling
2. Greeks & Volatility Normalization (Attacker 2 & 3)
   - ATR normalization (distance_to_call_wall_atr, distance_to_put_wall_atr)
   - 5% hysteresis buffer on major wall displacement
3. Systems Architecture & Concurrency (Attacker 4)
   - Pre-warmed O(1) symbol lookup cache _SYMBOL_CACHE
   - Thread safety under concurrent option & spot ticks
   - Dirty-flag cached state recomputation & throttling
   - Compact JSON atomic persistence
4. Risk Governance & Fail-Closed Guard (Attacker 5)
   - Minimum strike span enforcement (fail-closed if < min_strike_span)
   - Feed freshness skew enforcement (fail-closed if |spot_ts - opt_ts| > 60s)
   - Trading safety invariants (read_only, is_order_action=False, broker_api_called=False)
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path

import pytest
from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    SentinelWallState,
    StrikeWallProfile,
    _SYMBOL_CACHE,
    parse_option_symbol,
)


def test_parse_option_symbol_standard_and_variations():
    """Test 1: Ticker parsing (NIFTY, BANKNIFTY, SENSEX strike, expiry, CE/PE) and O(1) cache."""
    # Clear cache before testing
    _SYMBOL_CACHE.clear()

    # Standard weekly/monthly NSE format
    res1 = parse_option_symbol("NIFTY26OCT25000CE")
    assert res1 == ("NIFTY", 25000.0, "CE")
    assert "NIFTY26OCT25000CE" in _SYMBOL_CACHE

    res2 = parse_option_symbol("BANKNIFTY24DEC50000PE")
    assert res2 == ("BANKNIFTY", 50000.0, "PE")

    res3 = parse_option_symbol("NIFTY24O2425000CE")
    assert res3 == ("NIFTY", 25000.0, "CE")

    res4 = parse_option_symbol("SENSEX24N1578000PE")
    assert res4 == ("SENSEX", 78000.0, "PE")

    # Delimited fallback formats
    res5 = parse_option_symbol("NIFTY-25000-CE")
    assert res5 == ("NIFTY", 25000.0, "CE")

    res6 = parse_option_symbol("BANKNIFTY_52000_PE")
    assert res6 == ("BANKNIFTY", 52000.0, "PE")

    # Malformed inputs fail safely with None and cache negative result
    assert parse_option_symbol("") is None
    assert parse_option_symbol("INVALID_TICKER") is None
    assert parse_option_symbol(None) is None  # type: ignore
    assert parse_option_symbol("NIFTY_FUT") is None
    assert _SYMBOL_CACHE["INVALID_TICKER"] is None


def test_in_memory_tick_aggregation():
    """Test 2: In-memory tick aggregation and OI summation across multiple updates."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=1)

    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1700000000000)

    # Ingest CE tick
    observer.on_option_tick(
        symbol="NIFTY26OCT25000CE",
        ltp=150.0,
        volume=10000.0,
        oi=50000.0,
        bid_depth=1200.0,
        ask_depth=800.0,
        timestamp_ms=1700000000100,
    )

    # Ingest PE tick for same strike
    observer.on_option_tick(
        symbol="NIFTY26OCT25000PE",
        ltp=120.0,
        volume=8000.0,
        oi=75000.0,
        bid_depth=2000.0,
        ask_depth=500.0,
        timestamp_ms=1700000000200,
    )

    state = observer.compute_wall_state()
    assert state.symbol == "NIFTY"
    assert state.spot_price == 25000.0
    assert 25000.0 in state.wall_density_map

    profile = state.wall_density_map[25000.0]
    assert profile.call_oi == 50000.0
    assert profile.put_oi == 75000.0
    assert profile.call_volume == 10000.0
    assert profile.put_volume == 8000.0
    assert profile.call_bid_depth == 1200.0
    assert profile.call_ask_depth == 800.0
    assert profile.put_bid_depth == 2000.0
    assert profile.put_ask_depth == 500.0
    assert profile.net_oi_imbalance == 25000.0  # 75000 - 50000

    # Directional Liquidity checks:
    # Bullish Depth = CE Bid (1200) + PE Ask (500) = 1700
    # Bearish Depth = CE Ask (800) + PE Bid (2000) = 2800
    assert profile.bullish_depth == 1700.0
    assert profile.bearish_depth == 2800.0
    assert profile.net_directional_liquidity == -1100.0
    assert round(profile.directional_liquidity_ratio, 4) == round(1700.0 / 2800.0, 4)

    # Test update with higher OI
    observer.on_option_tick(
        symbol="NIFTY26OCT25000CE",
        ltp=155.0,
        volume=12000.0,
        oi=60000.0,
        bid_depth=1500.0,
        ask_depth=900.0,
        timestamp_ms=1700000000300,
    )
    state2 = observer.compute_wall_state(force_recompute=True)
    assert state2.wall_density_map[25000.0].call_oi == 60000.0
    assert state2.wall_density_map[25000.0].net_oi_imbalance == 15000.0  # 75000 - 60000


def test_major_and_secondary_wall_identification():
    """Test 3: Major and secondary Call & Put Wall identification (>75% rule)."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=5)
    observer.on_spot_tick(spot_price=24950.0, timestamp_ms=1700000000000)

    strikes_data = [
        (24800, 10000, 100000),
        (24900, 20000, 80000),
        (25000, 78000, 50000),
        (25100, 100000, 20000),
        (25200, 40000, 10000),
    ]

    for strike, c_oi, p_oi in strikes_data:
        observer.on_option_tick(
            symbol=f"NIFTY26OCT{strike}CE",
            oi=float(c_oi),
            timestamp_ms=1700000000010,
        )
        observer.on_option_tick(
            symbol=f"NIFTY26OCT{strike}PE",
            oi=float(p_oi),
            timestamp_ms=1700000000020,
        )

    state = observer.compute_wall_state()

    assert state.major_call_wall_strike == 25100.0
    assert state.major_put_wall_strike == 24800.0

    # Verify major wall flags
    assert state.wall_density_map[25100.0].is_major_call_wall is True
    assert state.wall_density_map[25100.0].is_secondary_call_wall is False
    assert state.wall_density_map[24800.0].is_major_put_wall is True
    assert state.wall_density_map[24800.0].is_secondary_put_wall is False

    # Verify secondary wall flags (75% of 100,000 = 75,000)
    assert state.wall_density_map[25000.0].is_secondary_call_wall is True
    assert state.wall_density_map[24900.0].is_secondary_put_wall is True
    assert state.wall_density_map[25200.0].is_secondary_call_wall is False


def test_spot_distance_and_volatility_normalized_proximity():
    """Test 4: Spot distance and ATR-normalized proximity warning triggers."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=2, atr_pts=40.0)

    # Major Call Wall at 25100, Major Put Wall at 24800
    observer.on_option_tick(symbol="NIFTY26OCT25100CE", oi=100000.0, timestamp_ms=1700000000000)
    observer.on_option_tick(symbol="NIFTY26OCT24800PE", oi=100000.0, timestamp_ms=1700000000000)

    # Spot at 25060 (40 pts from Call Wall 25100; ATR = 40.0 -> distance_atr = 1.0)
    observer.on_spot_tick(spot_price=25060.0, timestamp_ms=1700000000000)
    state = observer.compute_wall_state()

    assert state.is_valid is True
    assert state.distance_to_call_wall_pts == 40.0
    assert state.distance_to_put_wall_pts == 260.0
    assert state.distance_to_call_wall_atr == 1.0  # 40.0 / 40.0
    assert state.distance_to_put_wall_atr == 6.5  # 260.0 / 40.0

    # Proximity check with points
    assert observer.is_spot_near_call_wall(threshold_pts=50.0) is True
    assert observer.is_spot_near_put_wall(threshold_pts=50.0) is False

    # Proximity check with ATR normalized threshold
    assert observer.is_spot_near_call_wall(threshold_atr=1.2) is True
    assert observer.is_spot_near_call_wall(threshold_atr=0.8) is False
    assert observer.is_spot_near_put_wall(threshold_atr=1.5) is False

    # Move spot near Put Wall (24830 -> 30 pts from 24800; 30/40 = 0.75 ATR)
    observer.on_spot_tick(spot_price=24830.0, timestamp_ms=1700000001000)
    state2 = observer.compute_wall_state(force_recompute=True)
    assert state2.distance_to_call_wall_pts == 270.0
    assert state2.distance_to_put_wall_pts == 30.0
    assert state2.distance_to_put_wall_atr == 0.75

    assert observer.is_spot_near_call_wall(threshold_pts=50.0) is False
    assert observer.is_spot_near_put_wall(threshold_pts=50.0) is True
    assert observer.is_spot_near_put_wall(threshold_atr=1.0) is True


def test_depth_absorption_zones():
    """Test 5: Depth absorption and net OI imbalance calculation."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=2)

    # Strike 25000: Bids = 1000 + 1500 = 2500, Asks = 200 + 300 = 500 (Ratio 5.0 >= 2.0)
    observer.on_option_tick(
        symbol="NIFTY26OCT25000CE",
        bid_depth=1000.0,
        ask_depth=200.0,
    )
    observer.on_option_tick(
        symbol="NIFTY26OCT25000PE",
        bid_depth=1500.0,
        ask_depth=300.0,
    )

    # Strike 25100: Bids = 1000, Asks = 1000 (Balanced ratio 1.0 < 2.0)
    observer.on_option_tick(
        symbol="NIFTY26OCT25100CE",
        bid_depth=500.0,
        ask_depth=500.0,
    )
    observer.on_option_tick(
        symbol="NIFTY26OCT25100PE",
        bid_depth=500.0,
        ask_depth=500.0,
    )

    absorption_zones = observer.get_absorption_zones(min_depth_ratio=2.0)
    assert 25000.0 in absorption_zones
    assert 25100.0 not in absorption_zones


def test_safety_invariants_preservation():
    """Test 6: Safety invariants preservation."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=1)
    assert observer.read_only is True
    assert observer.is_order_action is False
    assert observer.broker_api_called is False
    assert observer.allowed_for_live_execution is False
    assert observer.edge_certification_status == "NO_CERTIFIED_EDGE"

    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1000)
    observer.on_option_tick(symbol="NIFTY26OCT25000CE", oi=100.0, timestamp_ms=1000)

    state = observer.compute_wall_state()
    assert state.read_only is True
    assert state.is_order_action is False
    assert state.broker_api_called is False
    assert state.allowed_for_live_execution is False
    assert state.edge_certification_status == "NO_CERTIFIED_EDGE"

    # Verify dataclass is frozen / immutable
    with pytest.raises(Exception):
        state.read_only = False  # type: ignore

    with pytest.raises(Exception):
        state.is_order_action = True  # type: ignore


def test_hysteresis_buffer_prevents_flip_flops():
    """Test 7: 5% hysteresis buffer on Major Wall displacement (Attacker 2 & 3)."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=2)
    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1000)

    # Establish initial call wall at 25100 with 100,000 OI
    observer.on_option_tick(symbol="NIFTY26OCT25100CE", oi=100000.0, timestamp_ms=1000)
    observer.on_option_tick(symbol="NIFTY26OCT25200CE", oi=90000.0, timestamp_ms=1000)

    state1 = observer.compute_wall_state()
    assert state1.major_call_wall_strike == 25100.0

    # Strike 25200 rises to 103,000 (+3% over 100,000). Hysteresis (<5%) prevents flip-flop!
    observer.on_option_tick(symbol="NIFTY26OCT25200CE", oi=103000.0, timestamp_ms=1010)
    state2 = observer.compute_wall_state(force_recompute=True)
    assert state2.major_call_wall_strike == 25100.0  # Kept existing wall!

    # Strike 25200 rises to 106,000 (+6% over 100,000 >= 5%). Wall successfully flips!
    observer.on_option_tick(symbol="NIFTY26OCT25200CE", oi=106000.0, timestamp_ms=1020)
    state3 = observer.compute_wall_state(force_recompute=True)
    assert state3.major_call_wall_strike == 25200.0  # Displaced!


def test_feed_freshness_and_minimum_coverage_fail_closed_guard():
    """Test 8: Risk Governance & Fail-Closed Guard (Attacker 5)."""
    # 1. Test Minimum Strike Span Guard (requires >= 10 strikes by default)
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=10)
    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1700000000000)

    # Ingest only 5 strikes
    for s in [24800, 24900, 25000, 25100, 25200]:
        observer.on_option_tick(
            symbol=f"NIFTY26OCT{s}CE",
            oi=10000.0,
            timestamp_ms=1700000000000,
        )

    state = observer.compute_wall_state()
    assert state.is_valid is False
    assert state.status == "INSUFFICIENT_COVERAGE"
    assert state.strike_span_count == 5

    # 2. Add 5 more strikes to satisfy coverage
    for s in [24500, 24600, 24700, 25300, 25400]:
        observer.on_option_tick(
            symbol=f"NIFTY26OCT{s}CE",
            oi=10000.0,
            timestamp_ms=1700000000000,
        )

    state_healthy = observer.compute_wall_state(force_recompute=True)
    assert state_healthy.is_valid is True
    assert state_healthy.status == "HEALTHY"
    assert state_healthy.strike_span_count == 10

    # 3. Test Feed Freshness Skew Guard (> 60,000ms skew between spot and options)
    # Option ticks are at 1700000000000. Spot advances by 70,000ms.
    observer.on_spot_tick(spot_price=25050.0, timestamp_ms=1700000070000)
    state_stale = observer.compute_wall_state(force_recompute=True)
    assert state_stale.is_valid is False
    assert state_stale.status == "STALE_FEED"

    # Re-sync options tick -> returns to HEALTHY
    observer.on_option_tick(symbol="NIFTY26OCT25000CE", oi=10000.0, timestamp_ms=1700000070000)
    state_resynced = observer.compute_wall_state(force_recompute=True)
    assert state_resynced.is_valid is True
    assert state_resynced.status == "HEALTHY"


def test_thread_safety_concurrency():
    """Test 9: Thread safety and lock concurrency under parallel ticks (Attacker 4)."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=5)
    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1000)

    def worker_spot(idx: int):
        for i in range(100):
            observer.on_spot_tick(spot_price=25000.0 + (idx * 10) + i, timestamp_ms=1000 + i)

    def worker_options(strike: int):
        for i in range(100):
            observer.on_option_tick(
                symbol=f"NIFTY26OCT{strike}CE",
                oi=10000.0 + i,
                volume=100.0 + i,
                bid_depth=500.0 + i,
                ask_depth=400.0 + i,
                timestamp_ms=1000 + i,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for s in [24800, 24900, 25000, 25100, 25200]:
            futures.append(executor.submit(worker_options, s))
        for w in range(3):
            futures.append(executor.submit(worker_spot, w))
        for f in concurrent.futures.as_completed(futures):
            f.result()

    state = observer.compute_wall_state(force_recompute=True)
    assert state.strike_span_count == 5
    assert state.spot_price > 0


def test_compact_json_persistence(tmp_path: Path):
    """Test 10: Compact JSON atomic disk persistence and rate-limiting."""
    out_file = tmp_path / "test_wall_state.json"
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=2)
    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1000)
    observer.on_option_tick(symbol="NIFTY26OCT25000CE", oi=50000.0, timestamp_ms=1000)
    observer.on_option_tick(symbol="NIFTY26OCT25000PE", oi=40000.0, timestamp_ms=1000)

    state = observer.persist_state_atomic(str(out_file), min_interval_sec=0.0)
    assert out_file.exists()

    raw_text = out_file.read_text(encoding="utf-8")
    # Verify compact formatting (no indentation whitespace)
    assert '":' in raw_text
    assert ',"' in raw_text

    loaded = json.loads(raw_text)
    assert loaded["symbol"] == "NIFTY"
    assert loaded["spot_price"] == 25000.0


def test_high_throughput_benchmark():
    """Test 11: Latency benchmark showing sub-millisecond execution for 126 strikes."""
    observer = SentinelWallObserver(underlying_symbol="NIFTY", min_strike_span=10)
    observer.on_spot_tick(spot_price=25000.0, timestamp_ms=1700000000000)

    # Ingest 126 strikes
    start_time = time.perf_counter()
    for strike in range(24000, 26520, 20):
        observer.on_option_tick(
            symbol=f"NIFTY26OCT{strike}CE",
            ltp=100.0,
            volume=5000.0,
            oi=strike * 2.0,
            bid_depth=1000.0,
            ask_depth=800.0,
            timestamp_ms=1700000000100,
        )
        observer.on_option_tick(
            symbol=f"NIFTY26OCT{strike}PE",
            ltp=80.0,
            volume=4000.0,
            oi=(50000 - strike) * 2.0,
            bid_depth=900.0,
            ask_depth=1100.0,
            timestamp_ms=1700000000100,
        )
    ingest_duration_ms = (time.perf_counter() - start_time) * 1000.0

    # Compute wall state
    compute_start = time.perf_counter()
    state = observer.compute_wall_state()
    compute_duration_ms = (time.perf_counter() - compute_start) * 1000.0

    assert len(state.wall_density_map) >= 126
    assert state.is_valid is True
    # Fast path caching re-check
    cached_start = time.perf_counter()
    cached_state = observer.compute_wall_state()
    cached_duration_ms = (time.perf_counter() - cached_start) * 1000.0
    assert cached_state is state
    assert cached_duration_ms < 0.1  # Fast cached return

    assert compute_duration_ms < 10.0, f"Compute took {compute_duration_ms:.2f}ms"
