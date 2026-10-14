from datetime import datetime, timezone
import pytest
import numpy as np

from core.causal_synchronized_buffer import (
    CausalSynchronizedBuffer,
    CausalityViolationError,
    MarketTick,
)
from core.market_state_cache import MarketStateCache


def test_synchronized_multi_stream_arrival():
    """Verifies Spot, Options, and VIX arrive asynchronously but latch to the exact same horizon."""
    buffer = CausalSynchronizedBuffer()
    t_start = datetime(2026, 10, 6, 9, 15, 0, tzinfo=timezone.utc)
    
    # 1. Option tick arrives first
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 2, tzinfo=timezone.utc),
        stream_type="OPTION",
        symbol="NIFTY26OCT22500CE",
        price=120.0,
        open_interest=5000000.0,
        metadata={"strike": 22500.0, "option_type": "CE"}
    ))
    
    # 2. Put option tick arrives
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 5, tzinfo=timezone.utc),
        stream_type="OPTION",
        symbol="NIFTY26OCT22500PE",
        price=95.0,
        open_interest=6500000.0,
        metadata={"strike": 22500.0, "option_type": "PE"}
    ))

    # 3. VIX tick arrives
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 8, tzinfo=timezone.utc),
        stream_type="VIX",
        symbol="INDIAVIX",
        price=14.25
    ))

    # 4. Spot ticks arrive throughout the minute
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 10, tzinfo=timezone.utc),
        stream_type="SPOT",
        symbol="NIFTY50",
        price=22510.0,
        volume=100.0
    ))
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 59, tzinfo=timezone.utc),
        stream_type="SPOT",
        symbol="NIFTY50",
        price=22520.0,
        volume=200.0
    ))

    # Close bar at 09:16:00
    t_horizon = datetime(2026, 10, 6, 9, 16, 0, tzinfo=timezone.utc)
    snapshot = buffer.close_bar_horizon(t_horizon)

    assert snapshot.horizon_timestamp == t_horizon
    assert snapshot.spot_price == 22520.0
    # VWAP: (22510*100 + 22520*200) / 300 = 22516.666...
    assert pytest.approx(snapshot.spot_vwap, rel=1e-3) == 22516.666
    assert snapshot.vix == 14.25
    assert snapshot.call_oi_total == 5000000.0
    assert snapshot.put_oi_total == 6500000.0
    assert pytest.approx(snapshot.strike_pcr, rel=1e-3) == 1.30


def test_causality_violation_guard():
    """Guarantees that any backward or out-of-horizon ticks fail closed."""
    buffer = CausalSynchronizedBuffer()
    t_h1 = datetime(2026, 10, 6, 9, 16, 0, tzinfo=timezone.utc)
    
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 30, tzinfo=timezone.utc),
        stream_type="SPOT",
        symbol="NIFTY50",
        price=22500.0,
    ))
    buffer.close_bar_horizon(t_h1)

    # Ingesting a tick from 09:15:45 AFTER closing horizon at 09:16:00 MUST FAIL CLOSED
    with pytest.raises(CausalityViolationError):
        buffer.ingest_tick(MarketTick(
            timestamp=datetime(2026, 10, 6, 9, 15, 45, tzinfo=timezone.utc),
            stream_type="SPOT",
            symbol="NIFTY50",
            price=22495.0,
        ))


def test_market_state_cache_fingerprint_and_lookup(tmp_path):
    """Proves that states can be cached immutably and looked up instantly when setups repeat."""
    cache = MarketStateCache(cache_dir=tmp_path / "state_cache")
    buffer = CausalSynchronizedBuffer()
    
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 10, tzinfo=timezone.utc),
        stream_type="SPOT",
        symbol="NIFTY50",
        price=22500.0,
        volume=100.0
    ))
    buffer.ingest_tick(MarketTick(
        timestamp=datetime(2026, 10, 6, 9, 15, 12, tzinfo=timezone.utc),
        stream_type="VIX",
        symbol="INDIAVIX",
        price=14.0
    ))
    
    t_h1 = datetime(2026, 10, 6, 9, 16, 0, tzinfo=timezone.utc)
    snapshot = buffer.close_bar_horizon(t_h1)

    fingerprint = cache.store_snapshot(snapshot, metadata={"regime": "EXPIRY_PIN_SETUP"})
    assert len(fingerprint) == 64  # SHA-256

    entry = cache.lookup_by_fingerprint(fingerprint)
    assert entry is not None
    assert entry["spot_price"] == 22500.0
    assert entry["metadata"]["regime"] == "EXPIRY_PIN_SETUP"
