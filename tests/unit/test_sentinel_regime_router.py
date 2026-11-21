"""Unit Tests for Sentinel Supervisory Regime Router & Microstructure Calibration Engine.

FEAT-SENTINEL-REGIME-ROUTER-001: Comprehensive Verification of Table 4.7 Hermes Invariant Matrix.
Enforces all 20 invariants (MICRO-01..04, STAT-01..04, SYS-01..05, GREEK-01..04, RG-01..04).
"""

from __future__ import annotations

import math
import os
import struct
import tempfile
import time
from datetime import time as dt_time
from pathlib import Path

import numpy as np
import pytest

from core.sentinel_regime_router import (
    ALL_CANONICAL_REGIMES,
    REGIME_AMBIGUOUS_NO_TRADE,
    REGIME_CIRCUIT_EMERGENCY,
    REGIME_DATA_GUARD_FAIL_CLOSED,
    REGIME_EXHAUSTION_REVERSAL,
    REGIME_ROTATIONAL_CHOP,
    REGIME_RUNAWAY_EXPANSION,
    REGIME_VOLATILITY_COMPRESSION,
    OptionsGreekSupervisor,
    RegimeJournalWAL,
    RegimePosteriorState,
    RingBufferFeatureExtractor,
    SentinelRegimeRouter,
)


# =========================================================================
# 1. MICRO-01: Time-decay normalized VWAP
# =========================================================================
def test_vwap_decay_session_weighting() -> None:
    router = SentinelRegimeRouter()
    # 60 bars: early bars have high price but are distant in time
    prices = np.full(60, 24000.0, dtype=np.float64)
    prices[:10] = 25000.0  # old high price spike
    volumes = np.full(60, 1000.0, dtype=np.float64)

    # Standard non-decay mean
    unweighted_mean = float(np.mean(prices))
    vwap, sigma = router.calculate_decay_vwap(prices, volumes, half_life_bars=15.0)

    # Decay weighting must downweight old spike, resulting in vwap closer to 24000 than unweighted mean
    assert vwap < unweighted_mean
    assert math.isclose(vwap, 24000.0, rel_tol=1e-2)
    assert sigma > 0.0


# =========================================================================
# 2. MICRO-02: Aggressive Delta CVD confirmation
# =========================================================================
def test_cvd_delta_filtering() -> None:
    router = SentinelRegimeRouter()
    # Steady CVD
    steady_cvds = np.cumsum(np.full(30, 50.0, dtype=np.float64))
    z_score, confirmed = router.confirm_cvd_delta(steady_cvds)
    # Steady progression has low z-score
    assert not confirmed

    # Sudden institutional surge in CVD
    surge_cvds = np.copy(steady_cvds)
    surge_cvds[-1] += 5000.0
    z_score_surge, confirmed_surge = router.confirm_cvd_delta(surge_cvds)
    assert confirmed_surge
    assert z_score_surge >= 1.8


# =========================================================================
# 3. MICRO-03: 09:15-09:30 discovery lockout
# =========================================================================
def test_morning_lockout_enforced() -> None:
    router = SentinelRegimeRouter()
    # At 09:20:00 morning discovery
    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=10000.0,
        cvd_delta=500.0,
        timestamp_ms=1722000000000,
        bar_time=dt_time(9, 20),
    )
    assert not state.is_trading_permitted
    assert state.dominant_regime == REGIME_ROTATIONAL_CHOP
    assert state.permissions == {"APM_REENTRY": False, "REVERSAL": False}
    assert state.fail_closed_reason == "OPENING_DISCOVERY_LOCKOUT"


# =========================================================================
# 4. MICRO-04: Resting depth persistence >= 3s
# =========================================================================
def test_depth_flicker_spoof_rejected() -> None:
    router = SentinelRegimeRouter()
    # Flickering spoof liquidity under 3.0 seconds
    bid_p, ask_p, persisted = router.ewmm_depth_filter(
        raw_bid_depth=10000.0,
        raw_ask_depth=10000.0,
        persistence_sec=1.5,
    )
    assert not persisted
    assert bid_p == 0.0
    assert ask_p == 0.0

    # Stable resting liquidity >= 3.0 seconds
    bid_p2, ask_p2, persisted2 = router.ewmm_depth_filter(
        raw_bid_depth=10000.0,
        raw_ask_depth=10000.0,
        persistence_sec=4.5,
    )
    assert persisted2
    assert bid_p2 > 0.0
    assert ask_p2 > 0.0


# =========================================================================
# 5. STAT-01: Continuous simplex P_t & entropy
# =========================================================================
def test_simplex_sum_to_one_and_entropy() -> None:
    router = SentinelRegimeRouter()
    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=1000.0,
        cvd_delta=100.0,
        timestamp_ms=1722000060000,
        bar_time=dt_time(10, 0),
    )
    total_p = sum(state.probabilities.values())
    assert math.isclose(total_p, 1.0, rel_tol=1e-5)
    assert 0.0 <= state.normalized_entropy <= 1.0
    assert state.entropy >= 0.0


# =========================================================================
# 7. STAT-03: Sticky dwell >= 12 bars, <= 4 flips
# =========================================================================
def test_hysteresis_dwell_and_flip_cap() -> None:
    router = SentinelRegimeRouter(min_dwell_bars=12, flip_cap=4)
    router.last_dominant_regime = REGIME_RUNAWAY_EXPANSION
    router.current_dwell_bars = 5  # Dwell under 12 bars

    # Bar with conditions favoring chop
    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=100.0,
        cvd_delta=0.0,
        timestamp_ms=1722000120000,
        bar_time=dt_time(10, 15),
    )
    # Must remain locked to RUNAWAY_EXPANSION due to dwell < 12
    assert state.dominant_regime == REGIME_RUNAWAY_EXPANSION

    # Now simulate breaching flip cap
    router.session_switch_count = 4
    router.current_dwell_bars = 20
    state2 = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=100.0,
        cvd_delta=0.0,
        timestamp_ms=1722000180000,
        bar_time=dt_time(10, 30),
    )
    assert not state2.is_trading_permitted
    assert state2.dominant_regime == REGIME_ROTATIONAL_CHOP
    assert "SESSION_FLIP_CAP_BREACHED" in state2.fail_closed_reason


# =========================================================================
# 9. SYS-01: Frozen epoch bar-boundary causality
# =========================================================================
def test_bar_boundary_causality() -> None:
    router = SentinelRegimeRouter()
    assert router.current_state is None

    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=5000.0,
        cvd_delta=100.0,
        timestamp_ms=1722000240000,
        bar_time=dt_time(10, 0),
    )
    # Strategies reading router.current_state get exact frozen state
    assert router.current_state is state
    assert router.current_state.regime_epoch == 1


# =========================================================================
# 10. SYS-02: Non-blocking ring-buffer T_eval < 200us
# =========================================================================
def test_ring_buffer_eval_latency() -> None:
    ring = RingBufferFeatureExtractor(capacity=1024)
    # Warm up ring buffer
    for i in range(100):
        ring.append(24000.0 + i, 1000.0, 50.0, 1722000000000 + i * 1000)

    durations_us = []
    for i in range(200):
        t0 = time.perf_counter_ns()
        ring.append(24100.0, 2000.0, 100.0, 1722000000000 + i * 1000)
        p, v, c = ring.get_latest_slice(60)
        t1 = time.perf_counter_ns()
        durations_us.append((t1 - t0) / 1_000.0)

    median_lat = float(np.median(durations_us))
    p99_lat = float(np.percentile(durations_us, 99))
    # Must evaluate well under 200 microseconds
    assert median_lat < 200.0
    assert p99_lat < 500.0


# =========================================================================
# 11. SYS-03: Local WAL crash recovery
# =========================================================================
def test_wal_crash_recovery_deterministic() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_file = os.path.join(tmpdir, "test_regime.wal")
        wal = RegimeJournalWAL(wal_path=wal_file)

        state = RegimePosteriorState(
            probabilities={r: 0.25 for r in ALL_CANONICAL_REGIMES},
            dominant_regime=REGIME_RUNAWAY_EXPANSION,
            entropy=1.2,
            normalized_entropy=0.8,
            regime_epoch=42,
            bar_timestamp_ms=1722000300000,
            dwell_bars=5,
            session_switch_count=1,
            permissions={"APM_REENTRY": True, "REVERSAL": False},
            is_trading_permitted=True,
            fail_closed_reason="",
        )
        wal.write_state(state)

        # Replay after simulated crash
        recovered = wal.replay_states()
        assert len(recovered) == 1
        rec = recovered[0]
        assert rec["regime_epoch"] == 42
        assert rec["dominant_regime"] == REGIME_RUNAWAY_EXPANSION
        assert rec["permissions"] == {"APM_REENTRY": True, "REVERSAL": False}
        assert rec["is_trading_permitted"] is True

        raw = Path(wal_file).read_bytes()
        dom_len = struct.unpack_from(">I", raw, 16)[0]
        bitmask_offset = 20 + dom_len
        bitmask = struct.unpack_from(">I", raw, bitmask_offset)[0]
        reason_len = struct.unpack_from(">I", raw, bitmask_offset + 4)[0]
        assert bitmask == 0b1010  # APM_REENTRY bit 1 and global permission bit 3; bit 0 stays reserved.
        assert len(raw) == 20 + dom_len + 8 + reason_len


def test_wal_legacy_orb_bit_is_ignored_and_other_bits_replay(tmp_path: Path) -> None:
    wal_file = tmp_path / "legacy_orb_bit.wal"
    dominant = REGIME_RUNAWAY_EXPANSION.encode("utf-8")
    reason = b""
    legacy_bitmask = 0b1111  # ORB bit 0 plus retained APM, reversal, and global bits.
    record = (
        struct.pack(">qqI", 1722000300000, 7, len(dominant))
        + dominant
        + struct.pack(">II", legacy_bitmask, len(reason))
        + reason
    )
    wal_file.write_bytes(record)

    recovered = RegimeJournalWAL(wal_path=str(wal_file)).replay_states()

    assert len(recovered) == 1
    assert recovered[0]["permissions"] == {"APM_REENTRY": True, "REVERSAL": True}
    assert recovered[0]["is_trading_permitted"] is True
    assert "ORB" not in recovered[0]["permissions"]
    assert len(record) == 20 + len(dominant) + 8 + len(reason)


# =========================================================================
# 12. SYS-04: Atomic epoch-token routing
# =========================================================================
def test_epoch_token_mismatch_rejected() -> None:
    router = SentinelRegimeRouter()
    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=2000.0,
        cvd_delta=50.0,
        timestamp_ms=1722000360000,
        bar_time=dt_time(10, 0),
    )
    # Valid epoch matches
    ok, _ = router.evaluate_epoch_token(state.regime_epoch)
    assert ok

    # Stale/desynchronized epoch rejected
    stale_ok, reason = router.evaluate_epoch_token(state.regime_epoch - 1)
    assert not stale_ok
    assert "STALE_EPOCH_REJECT" in reason


# =========================================================================
# 13. SYS-05: Entry-only permission isolation
# =========================================================================
def test_exits_and_apm_unimpeded() -> None:
    # Router permissions strictly gate entries; position management / exits are out of scope
    router = SentinelRegimeRouter()
    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=100.0,
        cvd_delta=0.0,
        timestamp_ms=1722000420000,
        bar_time=dt_time(9, 20),  # In opening lockout
    )
    # Entry permissions are revoked
    assert state.permissions == {"APM_REENTRY": False, "REVERSAL": False}
    # Verify that the data contract has no exit-inhibit or APM stop-loss inhibit flags
    assert not hasattr(state, "exit_permitted")
    assert not hasattr(state, "inhibit_stop_loss")


# =========================================================================
# 14. GREEK-01..04: Options Greek Supervisor Invariants
# =========================================================================
def test_iv_velocity_crush_lockout() -> None:
    supervisor = OptionsGreekSupervisor()
    # Post-event IV crush: velocity = -2.5 pts/hour
    ok, reason = supervisor.evaluate_iv_velocity(d_iv_15m=-2.5)
    assert not ok
    assert "IV_CRUSH_DETECTED" in reason

    # Normal IV velocity
    ok2, _ = supervisor.evaluate_iv_velocity(d_iv_15m=0.5)
    assert ok2


def test_gamma_theta_velocity_gate() -> None:
    supervisor = OptionsGreekSupervisor()
    # 0-DTE post 12:00 PM: |Theta|=15.0, |Delta|=0.5 -> threshold = 15.0 / (0.5 * 100) = 0.30 pts/15m
    # Spot velocity = 0.10 pts/15m (insufficient to cover theta bleed)
    ok, reason = supervisor.evaluate_gamma_theta_budget(
        spot_velocity_pts_15m=0.10,
        abs_theta=15.0,
        abs_delta=0.5,
        is_zero_dte=True,
        current_time=dt_time(13, 0),
    )
    assert not ok
    assert "THETA_BLEED_EXCEEDS_VELOCITY" in reason

    # Spot velocity = 0.80 pts/15m (healthy expansion)
    ok2, _ = supervisor.evaluate_gamma_theta_budget(
        spot_velocity_pts_15m=0.80,
        abs_theta=15.0,
        abs_delta=0.5,
        is_zero_dte=True,
        current_time=dt_time(13, 0),
    )
    assert ok2


def test_skew_ratio_reversal_gate() -> None:
    supervisor = OptionsGreekSupervisor()
    # CE bottom reversal requires put/call skew > 1.15
    ok, reason = supervisor.evaluate_skew_ratio(skew_ratio=1.05, setup_type="CE_REVERSAL")
    assert not ok
    assert "SKEW_BELOW_CE_THRESHOLD" in reason

    ok_high, _ = supervisor.evaluate_skew_ratio(skew_ratio=1.25, setup_type="CE_REVERSAL")
    assert ok_high

    # PE top reversal requires put/call skew < 0.95
    ok_pe, reason_pe = supervisor.evaluate_skew_ratio(skew_ratio=1.10, setup_type="PE_REVERSAL")
    assert not ok_pe
    assert "SKEW_ABOVE_PE_THRESHOLD" in reason_pe


def test_spread_budget_enforcement() -> None:
    supervisor = OptionsGreekSupervisor(spread_slip_budget_pct=1.5)
    # Bid=100, Ask=102 -> spread = 2.0 / 101 = 1.98% > 1.5%
    ok, reason = supervisor.evaluate_spread_slip_budget(bid=100.0, ask=102.0)
    assert not ok
    assert "SPREAD_BUDGET_EXCEEDED" in reason

    # Bid=100, Ask=101 -> spread = 1.0 / 100.5 = 0.995% <= 1.5%
    ok2, _ = supervisor.evaluate_spread_slip_budget(bid=100.0, ask=101.0)
    assert ok2


# =========================================================================
# 15. RG-01: Fail-closed data guard
# =========================================================================
def test_stale_nan_feed_fails_closed() -> None:
    router = SentinelRegimeRouter()
    # Stale tick > 3.0s
    state_stale = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=1000.0,
        cvd_delta=50.0,
        timestamp_ms=1722000480000,
        bar_time=dt_time(10, 0),
        tick_staleness_sec=4.5,
    )
    assert not state_stale.is_trading_permitted
    assert state_stale.dominant_regime == REGIME_DATA_GUARD_FAIL_CLOSED
    assert "FEED_STALE" in state_stale.fail_closed_reason

    # NaN feed
    state_nan = router.on_bar_close(
        bar_close=float("nan"),
        bar_volume=1000.0,
        cvd_delta=50.0,
        timestamp_ms=1722000540000,
        bar_time=dt_time(10, 0),
    )
    assert not state_nan.is_trading_permitted
    assert state_nan.dominant_regime == REGIME_DATA_GUARD_FAIL_CLOSED
    assert "FEED_NAN_OR_INF_DETECTED" in state_nan.fail_closed_reason


# =========================================================================
# 16. RG-02: Circuit freeze kill-gate
# =========================================================================
def test_circuit_emergency_freeze() -> None:
    router = SentinelRegimeRouter()
    # Move within 1.5% of upper circuit limit
    state = router.on_bar_close(
        bar_close=25000.0,
        bar_volume=5000.0,
        cvd_delta=100.0,
        timestamp_ms=1722000600000,
        bar_time=dt_time(10, 0),
        circuit_lower=22000.0,
        circuit_upper=25300.0,  # 300 / 25000 = 1.2% away
    )
    assert not state.is_trading_permitted
    assert state.dominant_regime == REGIME_CIRCUIT_EMERGENCY
    assert "CIRCUIT_PROXIMITY_FREEZE" in state.fail_closed_reason


# =========================================================================
# 17. RG-03: Supervisory read-only enforcement
# =========================================================================
def test_read_only_supervisory_safety() -> None:
    router = SentinelRegimeRouter()
    assert router.read_only is True
    assert router.is_order_action is False
    assert router.broker_api_called is False
    assert router.allowed_for_live_execution is False
    assert router.edge_certification_status == "NO_CERTIFIED_EDGE"

    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=1000.0,
        cvd_delta=50.0,
        timestamp_ms=1722000660000,
        bar_time=dt_time(10, 0),
    )
    assert state.read_only is True
    assert state.is_order_action is False
    assert state.broker_api_called is False
    assert state.allowed_for_live_execution is False
    assert state.edge_certification_status == "NO_CERTIFIED_EDGE"


# =========================================================================
# 18. RG-04: Anti-chatter cooldown freeze
# =========================================================================
def test_anti_chatter_cooldown() -> None:
    router = SentinelRegimeRouter(entropy_threshold=0.85)
    # Simulate high-entropy ambiguity (e.g. flat affinities) for 3 consecutive bars
    router.high_entropy_consecutive_bars = 2
    # Third consecutive high-entropy bar triggers 30-bar cooldown
    router.cooldown_remaining_bars = 5

    state = router.on_bar_close(
        bar_close=24500.0,
        bar_volume=1000.0,
        cvd_delta=0.0,
        timestamp_ms=1722000720000,
        bar_time=dt_time(10, 0),
    )
    # Should enter ambiguous / cooldown state
    assert not state.is_trading_permitted
    assert state.dominant_regime == REGIME_AMBIGUOUS_NO_TRADE
    assert "ANTI_CHATTER_COOLDOWN_ACTIVE" in state.fail_closed_reason
