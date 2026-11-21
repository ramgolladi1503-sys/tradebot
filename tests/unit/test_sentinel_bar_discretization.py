"""Unit Tests for Sentinel Invariant 4.1 Bar Discretization.

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
    SentinelRegimeRouter,
)
from core.upstox_stream_broadcaster import UpstoxTickRecord


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


def test_safety_invariants_preserved():
    """Verify non-negotiable safety invariants remain strictly intact."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    assert advisor.read_only is True
    assert advisor.is_order_action is False
    assert advisor.broker_api_called is False
    assert advisor.allowed_for_live_execution is False
