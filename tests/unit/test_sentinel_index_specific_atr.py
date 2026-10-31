"""Unit tests for Sentinel Index-Specific ATR and Wall Buffer Calibration.

Verifies:
1. Index-specific ATR resolution (DEFAULT_INDEX_ATR / FALLBACK_DEFAULT_ATR)
2. Thread-safe dynamic update_atr() with dirty state invalidation and bounds validation
3. Advisory proximity checks (is_spot_near_*_wall) defaulting to 0.50 * self.atr_pts
4. Index-specific wall buffer resolution (DEFAULT_INDEX_WALL_BUFFER_PTS)
5. Genuine wall detection (_is_genuine_*_wall) eliminating phantom wall noise
6. Advisor end-to-end index calibration and 1-minute synthetic bar ATR wiring

Trading Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
"""

import threading
import time
import pytest
from core.market_structure.sentinel_wall_observer import (
    SentinelWallObserver,
    DEFAULT_INDEX_ATR,
    FALLBACK_DEFAULT_ATR,
    StrikeWallProfile,
)
from core.market_structure.sentinel_wall_gate import (
    SentinelWallGate,
    DEFAULT_INDEX_WALL_BUFFER_PTS,
    GATE_ACTION_CLAMP_TARGET,
    GATE_ACTION_PROCEED,
)
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    InMemorySentinelAdapter,
)
from core.sentinel_inmem_adapter import UpstoxTickRecord


def _populate_observer(
    observer: SentinelWallObserver,
    spot: float,
    major_call: float,
    major_put: float,
    call_oi: float = 100_000.0,
    put_oi: float = 100_000.0,
    num_strikes: int = 10,
    timestamp_ms: int = 1729000000000,
) -> None:
    """Helper to populate an observer with sufficient strikes to be HEALTHY."""
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
            bid_depth=20000.0,
            ask_depth=5000.0,
            timestamp_ms=timestamp_ms,
        )

    # Explicitly establish major call and major put walls with dominant OI
    observer.on_option_tick(
        symbol=f"{observer.underlying_symbol} {int(major_call)} CE",
        ltp=50.0,
        volume=5000.0,
        oi=call_oi,
        bid_depth=20000.0,
        ask_depth=5000.0,
        timestamp_ms=timestamp_ms,
    )
    observer.on_option_tick(
        symbol=f"{observer.underlying_symbol} {int(major_put)} PE",
        ltp=50.0,
        volume=5000.0,
        oi=put_oi,
        bid_depth=20000.0,
        ask_depth=5000.0,
        timestamp_ms=timestamp_ms,
    )


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


def test_default_index_atr_resolution():
    """Verify observer resolves index-specific baseline ATR when atr_pts is None."""
    expected_atrs = {
        "NIFTY": 65.0,
        "BANKNIFTY": 300.0,
        "SENSEX": 500.0,
        "FINNIFTY": 120.0,
        "MIDCPNIFTY": 100.0,
        "BANKEX": 500.0,
    }
    for symbol, expected_atr in expected_atrs.items():
        obs = SentinelWallObserver(underlying_symbol=symbol)
        assert obs.atr_pts == expected_atr, f"Failed for {symbol}: expected {expected_atr}, got {obs.atr_pts}"

    # Fallback for unlisted index
    obs_custom = SentinelWallObserver(underlying_symbol="UNKNOWN_INDEX")
    assert obs_custom.atr_pts == FALLBACK_DEFAULT_ATR

    # Explicit override takes precedence
    obs_override = SentinelWallObserver(underlying_symbol="NIFTY", atr_pts=45.0)
    assert obs_override.atr_pts == 45.0


def test_observer_thread_safe_update_atr():
    """Verify observer.update_atr() validates inputs, updates atr_pts, sets dirty flag, and is thread-safe."""
    obs = SentinelWallObserver(underlying_symbol="NIFTY")
    assert obs.atr_pts == 65.0

    # 1. Valid update
    obs._is_dirty = False
    obs.update_atr(85.5)
    assert obs.atr_pts == 85.5
    assert obs._is_dirty is True

    # 2. Invalid updates raise ValueError
    with pytest.raises(ValueError):
        obs.update_atr(0.0)

    with pytest.raises(ValueError):
        obs.update_atr(-10.0)

    with pytest.raises(ValueError):
        obs.update_atr(None)

    # 3. Concurrency test: multiple threads updating ATR concurrently
    def worker(val: float):
        for _ in range(50):
            obs.update_atr(val)

    threads = [threading.Thread(target=worker, args=(50.0 + i * 5.0,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert obs.atr_pts >= 50.0
    assert obs._is_dirty is True


def test_advisory_proximity_uses_half_atr_default():
    """Verify is_spot_near_*_wall defaults to 0.50 * self.atr_pts when threshold_pts is None."""
    now_ms = 1729000000000

    # Case 1: NIFTY (ATR = 65.0 -> 0.50 * ATR = 32.5 pts)
    nifty_obs = SentinelWallObserver(underlying_symbol="NIFTY")
    assert nifty_obs.atr_pts == 65.0
    # Spot = 22500, Call wall = 22530 (dist = 30 pts <= 32.5 pts -> True)
    # Put wall = 22400 (dist = 100 pts > 32.5 pts -> False)
    _populate_observer(nifty_obs, spot=22500.0, major_call=22530.0, major_put=22400.0, timestamp_ms=now_ms)
    assert nifty_obs.is_spot_near_call_wall() is True
    assert nifty_obs.is_spot_near_put_wall() is False

    # Move spot to 22495 (dist = 35 pts > 32.5 pts -> False)
    nifty_obs.on_spot_tick(spot_price=22495.0, timestamp_ms=now_ms + 100)
    assert nifty_obs.is_spot_near_call_wall() is False

    # Case 2: SENSEX (ATR = 500.0 -> 0.50 * ATR = 250.0 pts)
    sensex_obs = SentinelWallObserver(underlying_symbol="SENSEX")
    assert sensex_obs.atr_pts == 500.0
    # Spot = 75000, Call wall = 75200 (dist = 200 pts <= 250 pts -> True)
    _populate_observer(sensex_obs, spot=75000.0, major_call=75200.0, major_put=74000.0, timestamp_ms=now_ms)
    assert sensex_obs.is_spot_near_call_wall() is True

    # Spot = 75000, dist = 300 pts > 250 pts -> False
    sensex_obs.on_spot_tick(spot_price=74700.0, timestamp_ms=now_ms + 100)
    assert sensex_obs.is_spot_near_call_wall() is False

    # Explicit threshold_pts overrides 0.5 * ATR default
    assert sensex_obs.is_spot_near_call_wall(threshold_pts=600.0) is True


def test_default_index_wall_buffer_resolution():
    """Verify SentinelWallGate resolves index-calibrated wall buffers."""
    expected_buffers = {
        "NIFTY": 2.0,
        "BANKNIFTY": 10.0,
        "SENSEX": 15.0,
        "FINNIFTY": 4.0,
        "MIDCPNIFTY": 3.0,
        "BANKEX": 15.0,
    }
    for symbol, expected_buf in expected_buffers.items():
        obs = SentinelWallObserver(underlying_symbol=symbol)
        gate = SentinelWallGate(observer=obs)
        assert gate.wall_buffer_pts == expected_buf, f"Failed for {symbol}: expected {expected_buf}, got {gate.wall_buffer_pts}"

    # Explicit override takes precedence
    obs_nifty = SentinelWallObserver(underlying_symbol="NIFTY")
    gate_custom = SentinelWallGate(observer=obs_nifty, wall_buffer_pts=5.5)
    assert gate_custom.wall_buffer_pts == 5.5


def test_genuine_wall_detection_and_clamping():
    """Verify _is_genuine_*_wall eliminates noise and clamp_target_to_wall uses default buffer."""
    now_ms = 1729000000000
    obs = SentinelWallObserver(underlying_symbol="NIFTY")
    gate = SentinelWallGate(observer=obs)
    assert gate.wall_buffer_pts == 2.0

    # Build scenario with 10 strikes:
    # 22500 Spot
    # Total Call OI = 200,000 across 10 strikes -> chain_avg = 20,000
    # Major Call wall at 22550 with OI = 80,000
    # Genuine threshold: >= 1.5 * chain_avg (30,000) AND >= 0.50 * major_oi (40,000) -> 40,000
    _populate_observer(obs, spot=22500.0, major_call=22550.0, major_put=22400.0, timestamp_ms=now_ms)

    # Add strike with 15,000 OI (above old 0.60 * chain_avg = 12,000, but NOT genuine)
    obs.on_option_tick(
        symbol="NIFTY 22520 CE",
        ltp=40.0,
        volume=1000.0,
        oi=15000.0,
        bid_depth=10000.0,
        ask_depth=2000.0,  # vuln = 0.20 (fortified)
        timestamp_ms=now_ms,
    )
    state = obs.compute_wall_state()
    prof_noise = state.wall_density_map[22520.0]

    # Verify noise strike is NOT genuine
    assert gate._is_genuine_call_wall(prof_noise, state) is False

    # Verify major wall IS genuine
    prof_major = state.wall_density_map[22550.0]
    assert gate._is_genuine_call_wall(prof_major, state) is True

    # Clamping test: Target = 60 pts (aiming for 22560), SL = 20 pts
    # Distance to major wall = 50 pts (22550 - 22500)
    # Nominal target (60 pts) exceeds major wall distance (50 pts).
    # Noise strike at 22520 (20 pts away) MUST NOT clamp because it is not genuine!
    # Major wall at 22550 (50 pts away) MUST clamp with default buffer = 2.0 pts -> 48.0 pts
    decision = gate.clamp_target_to_wall(
        direction="CE",
        spot_price=22500.0,
        nominal_target_pts=60.0,
        sl_pts=20.0,
        timestamp_ms=now_ms,
    )
    assert decision.action == GATE_ACTION_CLAMP_TARGET
    assert decision.clamped_target_pts == 48.0  # 50.0 - 2.0 (default NIFTY buffer)
    assert decision.major_wall_strike == 22550.0


def test_advisor_index_calibration_and_bar_true_range_wiring():
    """Verify SentinelLiveStreamAdvisor wires index calibrations and updates ATR from 1-min synthetic bars."""
    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)

    # 1. Verify index calibrations
    assert advisor.wall_observers["NIFTY"].atr_pts == 65.0
    assert advisor.wall_observers["SENSEX"].atr_pts == 500.0
    assert advisor.wall_observers["BANKNIFTY"].atr_pts == 300.0

    assert advisor.wall_gates["NIFTY"].wall_buffer_pts == 2.0
    assert advisor.wall_gates["SENSEX"].wall_buffer_pts == 15.0
    assert advisor.wall_gates["BANKNIFTY"].wall_buffer_pts == 10.0

    # 2. Verify synthetic bar range updates into bar_true_ranges and observer ATR
    # Minute 1: epoch_min = 100 (ts = 6000000)
    # Push high=22540, low=22500 -> range = 40.0
    advisor.on_tick(_make_tick(
        token="Nifty 50",
        ltp=22500.0,
        volume=1000,
        ts_ms=6_000_000,
    ))
    advisor.on_tick(_make_tick(
        token="Nifty 50",
        ltp=22540.0,
        volume=2000,
        ts_ms=6_030_000,
    ))

    # Minute 2: epoch_min = 101 (ts = 6060000)
    # Minute boundary roll triggers bar finalization and ATR update
    advisor.on_tick(_make_tick(
        token="Nifty 50",
        ltp=22520.0,
        volume=3000,
        ts_ms=6_060_000,
    ))

    assert len(advisor.bar_true_ranges["NIFTY"]) == 1
    assert advisor.bar_true_ranges["NIFTY"][0] == 40.0
    # Observer ATR should now reflect completed bar range average (40.0)
    assert advisor.wall_observers["NIFTY"].atr_pts == 40.0

    # Minute 2 ticks: initialized at 22520.0, high reaches 22580.0 -> range = 60.0
    advisor.on_tick(_make_tick(
        token="Nifty 50",
        ltp=22580.0,
        volume=4000,
        ts_ms=6_090_000,
    ))

    # Minute 3: epoch_min = 102 (ts = 6120000)
    advisor.on_tick(_make_tick(
        token="Nifty 50",
        ltp=22550.0,
        volume=5000,
        ts_ms=6_120_000,
    ))

    assert len(advisor.bar_true_ranges["NIFTY"]) == 2
    assert advisor.bar_true_ranges["NIFTY"][1] == 60.0
    # Rolling average of [40.0, 60.0] = 50.0
    assert advisor.wall_observers["NIFTY"].atr_pts == 50.0
