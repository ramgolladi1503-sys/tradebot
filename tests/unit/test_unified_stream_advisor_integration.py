from __future__ import annotations

import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.upstox_stream_broadcaster import (
    UpstoxAsyncParquetRecorder,
    UpstoxLevel5DepthRecord,
    UpstoxStreamBroadcaster,
    UpstoxTickRecord,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor


def test_unified_broadcaster_to_sentinel_and_recorder():
    """Verify that a single UpstoxStreamBroadcaster dispatches synchronously
    to both InMemorySentinelAdapter, SentinelLiveStreamAdvisor, and the
    UpstoxAsyncParquetRecorder with zero dropped records.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_unified_stream_"))
    try:
        recorder = UpstoxAsyncParquetRecorder(
            output_dir=temp_dir,
            chunk_size=50,
            flush_interval_sec=0.2,
            max_queue_size=1000,
        )
        adapter = InMemorySentinelAdapter(skew_threshold_ms=250.0, staleness_timeout_ms=1000.0)
        advisor = SentinelLiveStreamAdvisor(
            adapter=adapter,
            spread_veto_threshold=0.04,
            enable_stdout=False,
        )

        broadcaster = UpstoxStreamBroadcaster([recorder, adapter, advisor])

        now_ms = int(time.time() * 1000)

        # 1. Dispatch Index Spot Tick
        spot_tick = {
            "token": "NSE_INDEX|Nifty 50",
            "symbol": "NIFTY 50",
            "exchange_timestamp_ms": now_ms,
            "ltp": 25100.5,
            "volume": 0,
            "oi": 0,
            "best_bid": 25100.5,
            "best_ask": 25100.5,
        }
        broadcaster.dispatch_tick(spot_tick)

        # Check adapter received spot tick in memory
        latest_tick = adapter.get_latest_tick("NSE_INDEX|Nifty 50")
        assert latest_tick is not None
        assert latest_tick.ltp == 25100.5
        assert advisor.latest_spot == 25100.5

        # 2. Dispatch Level-5 Option Depth
        option_depth = {
            "token": "NSE_FO|NIFTY26OCT25100CE",
            "symbol": "NIFTY 25100 CE",
            "exchange_timestamp_ms": now_ms + 10,
            "ltp": 120.50,
            "volume": 150000,
            "oi": 3200000,
            "depth": [
                {"bid_price": 120.40, "bid_quantity": 1800, "bid_orders": 12, "ask_price": 120.60, "ask_quantity": 2100, "ask_orders": 15},
                {"bid_price": 120.30, "bid_quantity": 3000, "bid_orders": 20, "ask_price": 120.70, "ask_quantity": 2500, "ask_orders": 18},
                {"bid_price": 120.20, "bid_quantity": 4500, "bid_orders": 31, "ask_price": 120.80, "ask_quantity": 4000, "ask_orders": 25},
                {"bid_price": 120.10, "bid_quantity": 6000, "bid_orders": 45, "ask_price": 120.90, "ask_quantity": 5500, "ask_orders": 38},
                {"bid_price": 120.00, "bid_quantity": 10000, "bid_orders": 70, "ask_price": 121.00, "ask_quantity": 8000, "ask_orders": 55},
            ],
        }
        broadcaster.dispatch_depth(option_depth)

        # Check adapter received depth in memory
        latest_depth = adapter.get_latest_depth("NSE_FO|NIFTY26OCT25100CE")
        assert latest_depth is not None
        assert latest_depth.bid_p1 == 120.40
        assert latest_depth.ask_p1 == 120.60
        assert latest_depth.bid_q1 == 1800
        assert latest_depth.ask_q1 == 2100

        # Verify cross-strike causal synchronization
        is_valid, legs, reason = adapter.get_synchronized_legs(["NSE_FO|NIFTY26OCT25100CE"])
        assert is_valid is True
        assert reason == "OK"

        # Verify stop and flush of persistent recorder
        recorder.flush_and_stop()
        assert recorder.total_records_written == 1

        # Check parquet chunk exists and readable
        written = recorder.written_files
        assert len(written) == 1
        assert written[0].exists()

        # Check master stitched output
        master_file = temp_dir / "master_stitched.parquet"
        recorder.stitch_chunks(master_file)
        assert master_file.exists()
        assert master_file.stat().st_size > 0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
