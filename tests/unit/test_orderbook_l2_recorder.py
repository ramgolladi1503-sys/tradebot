"""Comprehensive Unit and Stress Tests for Level-2 Order Book Recorder & Features.

Validates:
1. Microstructure feature math: OBI bounds in [-1, 1], Micro-price convergence, Spread pct.
2. Triple Barrier Labeling logic.
3. Thread-safe asynchronous buffering and snappy Parquet chunk persistence.
4. Fail-closed queue saturation enforcement.
5. Disk space exhaustion safety guards.
6. Safety invariants verification.
"""

from __future__ import annotations

import queue
import time
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq
import pytest

from core.microstructure_features import (
    Level5BookSnapshot,
    compute_stoikov_micro_price,
    compute_triple_barrier_label,
    compute_weighted_obi,
    extract_microstructure_features,
)
from core.orderbook_l2_recorder import (
    DiskSpaceExhaustionError,
    OrderBookL2Recorder,
)
from core.upstox_stream_broadcaster import (
    QueueSaturationError,
    UpstoxLevel5DepthRecord,
)


def _make_dummy_depth_record(token: str = "NSE_INDEX|Nifty 50", seq: int = 1) -> UpstoxLevel5DepthRecord:
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol="NIFTY",
        exchange_timestamp_ms=1762235400000 + seq * 100,
        ingress_monotonic_ns=time.monotonic_ns(),
        ingress_wall_utc="2026-11-04T09:15:00.000Z",
        sequence_id=seq,
        ltp=25000.0,
        volume=100000,
        open_interest=50000,
        bid_p1=24995.0, bid_q1=100, bid_o1=10,
        bid_p2=24990.0, bid_q2=200, bid_o2=20,
        bid_p3=24985.0, bid_q3=300, bid_o3=30,
        bid_p4=24980.0, bid_q4=400, bid_o4=40,
        bid_p5=24975.0, bid_q5=500, bid_o5=50,
        ask_p1=25005.0, ask_q1=50, ask_o1=5,
        ask_p2=25010.0, ask_q2=150, ask_o2=15,
        ask_p3=25015.0, ask_q3=250, ask_o3=25,
        ask_p4=25020.0, ask_q4=350, ask_o4=35,
        ask_p5=25025.0, ask_q5=450, ask_o5=45,
    )


class TestMicrostructureMath:
    def test_obi_bounds_and_symmetry(self):
        # Balanced book -> OBI = 0.0
        assert compute_weighted_obi([100, 100], [100, 100]) == pytest.approx(0.0)

        # Pure bids -> OBI = +1.0
        assert compute_weighted_obi([500], [0]) == pytest.approx(1.0)

        # Pure asks -> OBI = -1.0
        assert compute_weighted_obi([0], [500]) == pytest.approx(-1.0)

        # Zero depth -> safe 0.0
        assert compute_weighted_obi([0], [0]) == pytest.approx(0.0)
        assert compute_weighted_obi([], []) == pytest.approx(0.0)

        # Weighted calculation
        # w = [1.0, 0.5], bids=[100, 200] -> 100 + 100 = 200
        # asks=[50, 100] -> 50 + 50 = 100
        # OBI = (200 - 100) / (200 + 100) = 100 / 300 = 0.333333
        obi = compute_weighted_obi([100, 200], [50, 100], weights=[1.0, 0.5])
        assert obi == pytest.approx(1.0 / 3.0)

    def test_stoikov_micro_price(self):
        # Bid = 100 (qty 10), Ask = 110 (qty 90)
        # Big ask queue -> price pressured downward toward bid
        # P_micro = (100*90 + 110*10) / (10 + 90) = (9000 + 1100) / 100 = 101.0
        micro_p = compute_stoikov_micro_price(100.0, 10, 110.0, 90)
        assert micro_p == pytest.approx(101.0)

        # Symmetrical quantities -> equals mid price (105.0)
        assert compute_stoikov_micro_price(100.0, 50, 110.0, 50) == pytest.approx(105.0)

        # Zero quantity fallback
        assert compute_stoikov_micro_price(100.0, 0, 110.0, 0) == pytest.approx(105.0)

    def test_triple_barrier_labeling(self):
        # Current mid = 100.0, half_spread = 1.0, pt=1.5, sl=1.0
        # Upper barrier = 100 + 1.5*1 = 101.5
        # Lower barrier = 100 - 1.0*1 = 99.0

        # Bullish case
        labels_bull = compute_triple_barrier_label(100.0, [100.2, 100.8, 101.6], pt_multiplier=1.5, sl_multiplier=1.0, half_spread=1.0)
        assert labels_bull == 1

        # Bearish case
        labels_bear = compute_triple_barrier_label(100.0, [99.5, 98.9], pt_multiplier=1.5, sl_multiplier=1.0, half_spread=1.0)
        assert labels_bear == -1

        # Flat / Neutral expiry
        labels_flat = compute_triple_barrier_label(100.0, [100.1, 100.3, 100.2], pt_multiplier=1.5, sl_multiplier=1.0, half_spread=1.0)
        assert labels_flat == 0


class TestOrderBookL2Recorder:
    def test_recorder_invariants_and_flushing(self, tmp_path: Path):
        recorder = OrderBookL2Recorder(
            output_dir=tmp_path / "l2_data",
            chunk_size=10,
            flush_interval_sec=0.1,
        )

        assert recorder.read_only is True
        assert recorder.is_order_action is False
        assert recorder.broker_api_called is False
        assert recorder.allowed_for_live_execution is False

        # Ingest 25 records
        for i in range(25):
            recorder.on_depth(_make_dummy_depth_record(seq=i + 1))

        time.sleep(0.3)
        recorder.stop()

        assert recorder.total_records_written == 25
        written = recorder.written_files
        assert len(written) >= 2  # At least 2 chunks for 25 items with chunk_size 10

        # Verify Parquet schema and readability
        table = pq.read_table(written[0])
        assert "bid_p1" in table.column_names
        assert "ask_p5" in table.column_names
        assert "exchange_timestamp_ms" in table.column_names
        assert len(table) > 0

    def test_realtime_feature_callback(self, tmp_path: Path):
        recorder = OrderBookL2Recorder(
            output_dir=tmp_path / "l2_features",
            chunk_size=5,
            flush_interval_sec=0.1,
            enable_feature_extraction=True,
        )

        emitted_features = []
        recorder.add_feature_callback(lambda f: emitted_features.append(f))

        recorder.on_depth(_make_dummy_depth_record(seq=1))
        recorder.on_depth(_make_dummy_depth_record(seq=2))

        time.sleep(0.2)
        recorder.stop()

        assert len(emitted_features) == 2
        feat = emitted_features[0]
        assert -1.0 <= feat.obi_weighted <= 1.0
        assert feat.spread_abs == pytest.approx(10.0)  # ask 25005 - bid 24995

    def test_fail_closed_queue_saturation(self, tmp_path: Path):
        # Tiny queue of size 2
        recorder = OrderBookL2Recorder(
            output_dir=tmp_path / "l2_saturation",
            max_queue_size=2,
            chunk_size=100,
            flush_interval_sec=10.0,
        )
        # Stop worker so queue fills immediately
        recorder._stop_event.set()

        recorder.on_depth(_make_dummy_depth_record(seq=1))
        recorder.on_depth(_make_dummy_depth_record(seq=2))

        with pytest.raises(QueueSaturationError):
            recorder.on_depth(_make_dummy_depth_record(seq=3))

    def test_disk_space_guard_enforcement(self, tmp_path: Path):
        # Mock free disk space to 500 MB (below 1GB limit)
        mock_usage = (100 * 1024**3, 99 * 1024**3, 500 * 1024**2)

        with patch("shutil.disk_usage", return_value=mock_usage):
            with pytest.raises(DiskSpaceExhaustionError):
                OrderBookL2Recorder(
                    output_dir=tmp_path / "l2_disk_test",
                    min_free_bytes=1024 * 1024 * 1024,
                )
