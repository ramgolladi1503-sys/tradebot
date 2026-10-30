"""Unit Tests for Sentinel Invariant 4.1 Bar Discretization & Mode 2 ORB Permission Gating.

Strict Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
"""

import math
from unittest.mock import MagicMock
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    SyntheticBarBucket,
)
from core.sentinel_regime_router import (
    RegimePosteriorState,
    SentinelRegimeRouter,
    REGIME_RUNAWAY_EXPANSION,
    REGIME_ROTATIONAL_CHOP,
    REGIME_AMBIGUOUS_NO_TRADE,
    REGIME_EXHAUSTION_REVERSAL,
    REGIME_VOLATILITY_COMPRESSION,
)
from core.upstox_stream_broadcaster import (
    UpstoxTickRecord,
    UpstoxLevel5DepthRecord,
)


def test_synthetic_bar_bucket_slots_and_initialization():
    """Verify SyntheticBarBucket slots and default fields."""
    bucket = SyntheticBarBucket()
    assert hasattr(bucket, "__slots__")
    assert bucket.bucket_epoch_min == -1
    assert bucket.open == 0.0
    assert bucket.high == -math.inf
    assert bucket.low == math.inf
    assert bucket.close == 0.0
    assert bucket.volume == 0.0
    assert bucket.tick_count == 0


def test_synthetic_bar_aggregation_same_minute_zero_router_calls():
    """100 ticks within the same minute invoke router.on_bar_close 0 times."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router_mock = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router_mock

    # Start at 2026-10-30 10:00:00 UTC (epoch = 1793354400 s -> 1793354400000 ms)
    # Minute boundary is 1793354400 // 60 = 29889240
    base_ts = 1793354400000

    for i in range(100):
        # All ticks within the first 50 seconds of that minute (same epoch_min)
        tick_ts = base_ts + (i * 500)  # up to 49.5 seconds
        advisor.on_tick(
            UpstoxTickRecord(
                token="NSE_INDEX|Nifty 50",
                symbol="NIFTY 50",
                exchange_timestamp_ms=tick_ts,
                ingress_monotonic_ns=0,
                ingress_wall_utc="",
                sequence_id=i,
                ltp=24000.0 + i,
                volume=10,
                open_interest=0,
                best_bid=24000.0,
                best_ask=24000.0,
            )
        )

    # Within the same minute, no bar has closed yet -> 0 router.on_bar_close invocations
    assert router_mock.on_bar_close.call_count == 0
    bucket = advisor.bar_buckets["NIFTY"]
    assert bucket.tick_count == 100
    assert bucket.open == 24000.0
    assert bucket.high == 24099.0
    assert bucket.low == 24000.0
    assert bucket.close == 24099.0
    assert bucket.volume == 1000.0


def test_synthetic_bar_aggregation_crossing_boundary_invokes_router_once():
    """Ticking across minute boundary invokes router.on_bar_close exactly 1 time with exact prior close and aggregated volume."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router_mock = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router_mock

    base_ts = 1793354400000  # Minute 29889240

    # Send 10 ticks in Minute 0
    for i in range(10):
        tick_ts = base_ts + (i * 1000)
        advisor.on_tick(
            UpstoxTickRecord(
                token="NSE_INDEX|Nifty 50",
                symbol="NIFTY 50",
                exchange_timestamp_ms=tick_ts,
                ingress_monotonic_ns=0,
                ingress_wall_utc="",
                sequence_id=i,
                ltp=24000.0 + (i * 2.0),
                volume=100,
                open_interest=0,
                best_bid=24000.0,
                best_ask=24000.0,
            )
        )

    assert router_mock.on_bar_close.call_count == 0

    # Now send a tick in Minute 1 (base_ts + 60_000 ms)
    next_min_ts = base_ts + 60_000
    advisor.on_tick(
        UpstoxTickRecord(
            token="NSE_INDEX|Nifty 50",
            symbol="NIFTY 50",
            exchange_timestamp_ms=next_min_ts,
            ingress_monotonic_ns=0,
            ingress_wall_utc="",
            sequence_id=11,
            ltp=24050.0,
            volume=50,
            open_interest=0,
            best_bid=24050.0,
            best_ask=24050.0,
        )
    )

    # Exactly 1 call triggered for Minute 0
    assert router_mock.on_bar_close.call_count == 1
    call_kwargs = router_mock.on_bar_close.call_args.kwargs
    assert call_kwargs["bar_close"] == 24018.0  # Last close of Minute 0
    assert call_kwargs["bar_volume"] == 1000.0  # Sum of 10 ticks * 100 volume
    assert call_kwargs["cvd_delta"] == 0.0

    # New bucket initialized for Minute 1
    bucket = advisor.bar_buckets["NIFTY"]
    assert bucket.tick_count == 1
    assert bucket.open == 24050.0
    assert bucket.close == 24050.0
    assert bucket.volume == 50.0


def test_mode2_orb_gating_rotational_chop_veto():
    """ROTATIONAL_CHOP blocks ORB breakout."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router

    post = RegimePosteriorState(
        probabilities={REGIME_ROTATIONAL_CHOP: 0.85, REGIME_RUNAWAY_EXPANSION: 0.05, REGIME_EXHAUSTION_REVERSAL: 0.05, REGIME_VOLATILITY_COMPRESSION: 0.05},
        dominant_regime=REGIME_ROTATIONAL_CHOP,
        entropy=0.5,
        normalized_entropy=0.35,
        regime_epoch=1,
        bar_timestamp_ms=100000,
        dwell_bars=5,
        session_switch_count=1,
        permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": True},
        is_trading_permitted=True,
        fail_closed_reason="",
    )
    router.current_state = post

    assert advisor._evaluate_orb_regime_permission(router) is False


def test_mode2_orb_gating_is_trading_permitted_false_veto():
    """is_trading_permitted=False blocks ORB breakout."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router

    post = RegimePosteriorState(
        probabilities={REGIME_RUNAWAY_EXPANSION: 0.90, REGIME_ROTATIONAL_CHOP: 0.04, REGIME_EXHAUSTION_REVERSAL: 0.03, REGIME_VOLATILITY_COMPRESSION: 0.03},
        dominant_regime=REGIME_RUNAWAY_EXPANSION,
        entropy=0.2,
        normalized_entropy=0.15,
        regime_epoch=2,
        bar_timestamp_ms=100000,
        dwell_bars=3,
        session_switch_count=0,
        permissions={"ORB": True, "APM_REENTRY": True, "REVERSAL": False},
        is_trading_permitted=False,  # Emergency circuit or data guard tripped
        fail_closed_reason="DATA_GUARD_FAIL_CLOSED",
    )
    router.current_state = post

    assert advisor._evaluate_orb_regime_permission(router) is False


def test_mode2_orb_gating_runaway_expansion_permits():
    """RUNAWAY_EXPANSION permits ORB breakout."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router

    post = RegimePosteriorState(
        probabilities={REGIME_RUNAWAY_EXPANSION: 0.85, REGIME_ROTATIONAL_CHOP: 0.05, REGIME_EXHAUSTION_REVERSAL: 0.05, REGIME_VOLATILITY_COMPRESSION: 0.05},
        dominant_regime=REGIME_RUNAWAY_EXPANSION,
        entropy=0.4,
        normalized_entropy=0.3,
        regime_epoch=3,
        bar_timestamp_ms=100000,
        dwell_bars=4,
        session_switch_count=1,
        permissions={"ORB": True, "APM_REENTRY": True, "REVERSAL": False},
        is_trading_permitted=True,
        fail_closed_reason="",
    )
    router.current_state = post

    assert advisor._evaluate_orb_regime_permission(router) is True


def test_mode2_orb_gating_volatility_compression_entropy_threshold():
    """Low entropy VOLATILITY_COMPRESSION permits ORB breakout, while high entropy blocks it."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router

    # Case A: Low entropy (< 0.70) under VOLATILITY_COMPRESSION
    post_low_entropy = RegimePosteriorState(
        probabilities={REGIME_VOLATILITY_COMPRESSION: 0.75, REGIME_RUNAWAY_EXPANSION: 0.15, REGIME_ROTATIONAL_CHOP: 0.05, REGIME_EXHAUSTION_REVERSAL: 0.05},
        dominant_regime=REGIME_VOLATILITY_COMPRESSION,
        entropy=0.6,
        normalized_entropy=0.45,  # < 0.70
        regime_epoch=4,
        bar_timestamp_ms=100000,
        dwell_bars=10,
        session_switch_count=2,
        permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": False},
        is_trading_permitted=True,
        fail_closed_reason="",
    )
    router.current_state = post_low_entropy
    assert advisor._evaluate_orb_regime_permission(router) is True

    # Case B: High entropy (>= 0.70) under VOLATILITY_COMPRESSION
    post_high_entropy = RegimePosteriorState(
        probabilities={REGIME_VOLATILITY_COMPRESSION: 0.40, REGIME_RUNAWAY_EXPANSION: 0.25, REGIME_ROTATIONAL_CHOP: 0.20, REGIME_EXHAUSTION_REVERSAL: 0.15},
        dominant_regime=REGIME_VOLATILITY_COMPRESSION,
        entropy=1.1,
        normalized_entropy=0.78,  # >= 0.70
        regime_epoch=5,
        bar_timestamp_ms=100000,
        dwell_bars=2,
        session_switch_count=3,
        permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": False},
        is_trading_permitted=True,
        fail_closed_reason="",
    )
    router.current_state = post_high_entropy
    assert advisor._evaluate_orb_regime_permission(router) is False


def test_mode2_orb_gating_ambiguous_and_exhaustion_veto():
    """AMBIGUOUS_NO_TRADE and EXHAUSTION_REVERSAL veto ORB breakout."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    router = MagicMock(spec=SentinelRegimeRouter)
    advisor.regime_routers["NIFTY"] = router

    post_ambiguous = RegimePosteriorState(
        probabilities={REGIME_AMBIGUOUS_NO_TRADE: 0.50, REGIME_RUNAWAY_EXPANSION: 0.20, REGIME_ROTATIONAL_CHOP: 0.15, REGIME_VOLATILITY_COMPRESSION: 0.15},
        dominant_regime=REGIME_AMBIGUOUS_NO_TRADE,
        entropy=1.2,
        normalized_entropy=0.85,
        regime_epoch=6,
        bar_timestamp_ms=100000,
        dwell_bars=1,
        session_switch_count=4,
        permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": False},
        is_trading_permitted=True,
        fail_closed_reason="",
    )
    router.current_state = post_ambiguous
    assert advisor._evaluate_orb_regime_permission(router) is False

    post_exhaustion = RegimePosteriorState(
        probabilities={REGIME_EXHAUSTION_REVERSAL: 0.80, REGIME_RUNAWAY_EXPANSION: 0.10, REGIME_ROTATIONAL_CHOP: 0.05, REGIME_VOLATILITY_COMPRESSION: 0.05},
        dominant_regime=REGIME_EXHAUSTION_REVERSAL,
        entropy=0.5,
        normalized_entropy=0.35,
        regime_epoch=7,
        bar_timestamp_ms=100000,
        dwell_bars=2,
        session_switch_count=4,
        permissions={"ORB": False, "APM_REENTRY": False, "REVERSAL": True},
        is_trading_permitted=True,
        fail_closed_reason="",
    )
    router.current_state = post_exhaustion
    assert advisor._evaluate_orb_regime_permission(router) is False


def test_safety_invariants_preserved():
    """Verify non-negotiable safety invariants remain strictly intact."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    assert advisor.read_only is True
    assert advisor.is_order_action is False
    assert advisor.broker_api_called is False
    assert advisor.allowed_for_live_execution is False
