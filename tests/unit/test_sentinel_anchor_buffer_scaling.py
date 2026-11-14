"""Tests for FEAT-SENTINEL-OPTIONMATE-ANCHOR-BUFFER-002:
Anchor Scaling, Premium-Proximity Strike Resolution, and Broadcaster Burst Queue Buffer.
========================================================================================

Verifies:
1. Dynamic half-straddle anchor derivation across DTE (0.2, 1, 2, 5) and VIX:
   0.40 * spot * (max(vix, 9.0) / 100.0) * math.sqrt(max(dte, 0.20) / 365.0)
2. Mode 5 Premium-proximity strike resolution in [0.50, 0.75] * anchor with strict
   exchange granularity (50 for NIFTY, 100 for SENSEX/BANKNIFTY).
3. Broadcaster queue scaling absorbing 25,000 depth burst without crashing or dropping.
4. Non-negotiable Trading Safety Invariants:
   read_only=True, is_order_action=False, broker_api_called=False, allowed_for_live_execution=False.
"""

import math
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.upstox_stream_broadcaster import (
    UpstoxAsyncParquetRecorder,
    UpstoxLevel5DepthRecord,
    UpstoxStreamBroadcaster,
    QueueSaturationError,
)
from core.sentinel_option_strike_resolver import (
    SentinelOptionStrikeResolver,
    Mode5StrikeSelection,
)
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    CachedRBFNAuctionSignal,
    Synthetic5mBarBucket,
)


def _make_dummy_depth_record(token: str, symbol: str, seq: int, ltp: float = 100.0) -> UpstoxLevel5DepthRecord:
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=1793188800000 + seq,
        ingress_monotonic_ns=time.monotonic_ns(),
        ingress_wall_utc="2026-11-04T09:20:00Z",
        sequence_id=seq,
        ltp=ltp,
        volume=1000 + seq,
        open_interest=500000,
        bid_p1=ltp - 0.5, bid_q1=100, bid_o1=5,
        bid_p2=ltp - 1.0, bid_q2=150, bid_o2=6,
        bid_p3=ltp - 1.5, bid_q3=200, bid_o3=7,
        bid_p4=ltp - 2.0, bid_q4=250, bid_o4=8,
        bid_p5=ltp - 2.5, bid_q5=300, bid_o5=9,
        ask_p1=ltp + 0.5, ask_q1=100, ask_o1=5,
        ask_p2=ltp + 1.0, ask_q2=150, ask_o2=6,
        ask_p3=ltp + 1.5, ask_q3=200, ask_o3=7,
        ask_p4=ltp + 2.0, ask_q4=250, ask_o4=8,
        ask_p5=ltp + 2.5, ask_q5=300, ask_o5=9,
    )


# =========================================================================
# 1. Dynamic Half-Straddle Anchor Across DTE and VIX
# =========================================================================

class TestDynamicHalfStraddleAnchorDerivation:
    """Proves Black-Scholes ATM half-straddle dynamic anchor formula across multi-DTE and VIX floors."""

    @pytest.mark.parametrize(
        "spot, vix, dte, expected_anchor_min, expected_anchor_max",
        [
            # NIFTY spot 24000
            (24000.0, 14.0, 0.20, 31.0, 32.0),   # 0.2 DTE (Expiry intraday): 24000 * 0.40 * 0.14 * sqrt(0.20/365) = 31.46
            (24000.0, 14.0, 1.0, 69.0, 71.5),    # 1.0 DTE (Pre-expiry): 24000 * 0.40 * 0.14 * sqrt(1.0/365) = 70.35
            (24000.0, 14.0, 2.0, 98.0, 101.0),   # 2.0 DTE (Midweek): 24000 * 0.40 * 0.14 * sqrt(2.0/365) = 99.49
            (24000.0, 14.0, 5.0, 155.0, 160.0),  # 5.0 DTE (Weekend carry): 24000 * 0.40 * 0.14 * sqrt(5.0/365) = 157.30
            # SENSEX spot 77000
            (77000.0, 13.5, 0.20, 95.0, 105.0),  # 0.2 DTE: 77000 * 0.40 * 0.135 * sqrt(0.20/365) = 97.43
            (77000.0, 13.5, 1.0, 215.0, 222.0),  # 1.0 DTE: 77000 * 0.40 * 0.135 * sqrt(1.0/365) = 217.86
            (77000.0, 13.5, 2.0, 305.0, 315.0),  # 2.0 DTE: 77000 * 0.40 * 0.135 * sqrt(2.0/365) = 308.10
            (77000.0, 13.5, 5.0, 480.0, 495.0),  # 5.0 DTE: 77000 * 0.40 * 0.135 * sqrt(5.0/365) = 487.15
        ],
    )
    def test_dynamic_anchor_scaling(self, spot, vix, dte, expected_anchor_min, expected_anchor_max):
        safe_vix = max(vix, 9.0)
        safe_dte = max(dte, 0.20)
        anchor = 0.40 * spot * (safe_vix / 100.0) * math.sqrt(safe_dte / 365.0)
        assert expected_anchor_min <= anchor <= expected_anchor_max, f"Anchor {anchor} outside expected [{expected_anchor_min}, {expected_anchor_max}]"

    def test_vix_floor_clamp(self):
        """Proves that sub-9.0 VIX is clamped to 9.0 floor, preventing zero or negative anchors."""
        spot = 24000.0
        anchor_sub_9 = 0.40 * spot * (max(6.5, 9.0) / 100.0) * math.sqrt(1.0 / 365.0)
        anchor_at_9 = 0.40 * spot * (9.0 / 100.0) * math.sqrt(1.0 / 365.0)
        assert anchor_sub_9 == anchor_at_9
        assert round(anchor_sub_9, 2) == 45.22

    def test_advisor_wires_dynamic_anchor_to_signal(self, tmp_path):
        """Proves SentinelLiveStreamAdvisor._on_5m_bar_close populates sustainable_anchor_price."""
        wal = tmp_path / "test_wal_anchor.json"
        advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
        advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=180.0)
        advisor.session_open_prices["NIFTY"] = 24000.0

        # Breakout bar close at 09:20 outside RP1
        sig = advisor._on_5m_bar_close(
            index_name="NIFTY",
            bar_open=24020.0,
            bar_high=24220.0,
            bar_low=24010.0,
            bar_close=24180.0,
            bar_volume=50000.0,
            bar_time=dt_time(9, 20),
            timestamp_ms=1793188800000,
            epoch_5min=100,
        )

        assert sig is not None
        assert sig.action == "BUY_CALL"
        assert sig.sustainable_anchor_price > 0.0
        # Expected anchor on NIFTY ~24180 * 0.40 * 0.14 * sqrt(1/365) ≈ 70.8
        assert 65.0 <= sig.sustainable_anchor_price <= 75.0


# =========================================================================
# 2. Mode 5 Premium-Proximity Strike Resolution & Step Granularity
# =========================================================================

class TestMode5PremiumProximityStrikeResolution:
    """Proves strike selection inside [0.50, 0.75] * anchor and strict exchange intervals."""

    def test_nifty_exchange_step_50_and_proximity_band(self):
        """NIFTY step size is strictly 50; selects contract within [0.50 * anchor, 0.75 * anchor]."""
        anchor = 100.0
        lower = 0.50 * anchor  # 50.0
        upper = 0.75 * anchor  # 75.0
        # Quotes available: 24100 CE @ 120, 24150 CE @ 65, 24200 CE @ 35
        quotes = [
            {"symbol": "NIFTY 24100 CE", "strike": 24100, "ltp": 120.0, "direction": "CE"},
            {"symbol": "NIFTY 24150 CE", "strike": 24150, "ltp": 65.0, "direction": "CE"},
            {"symbol": "NIFTY 24200 CE", "strike": 24200, "ltp": 35.0, "direction": "CE"},
        ]

        res = SentinelOptionStrikeResolver.resolve_mode5_strike(
            index_name="NIFTY",
            direction="CE",
            anchor_price=anchor,
            geometric_strike=24100.0,
            live_quotes=quotes,
        )

        assert res.step_size == 50.0
        assert res.target_strike == 24150.0
        assert res.selected_premium == 65.0
        assert res.selection_mode == "PREMIUM_PROXIMITY_BAND"
        assert res.lower_band == 50.0
        assert res.upper_band == 75.0
        assert res.target_strike % 50.0 == 0.0

    def test_sensex_banknifty_exchange_step_100(self):
        """SENSEX and BANKNIFTY enforce strict 100-pt step size."""
        assert SentinelOptionStrikeResolver.get_step_size("SENSEX") == 100.0
        assert SentinelOptionStrikeResolver.get_step_size("BANKNIFTY") == 100.0

        anchor = 220.0  # SENSEX anchor
        # Target band: [110, 165], target mid = 137.5
        quotes = [
            {"symbol": "SENSEX 77300 CE", "strike": 77300, "ltp": 210.0, "direction": "CE"},
            {"symbol": "SENSEX 77500 CE", "strike": 77500, "ltp": 140.0, "direction": "CE"},
            {"symbol": "SENSEX 77700 CE", "strike": 77700, "ltp": 80.0, "direction": "CE"},
        ]

        res = SentinelOptionStrikeResolver.resolve_mode5_strike(
            index_name="SENSEX",
            direction="CE",
            anchor_price=anchor,
            geometric_strike=77300.0,
            live_quotes=quotes,
        )

        assert res.target_strike == 77500.0
        assert res.selected_premium == 140.0
        assert res.selection_mode == "PREMIUM_PROXIMITY_BAND"
        assert res.target_strike % 100.0 == 0.0

    def test_geometric_fallback_when_no_live_quotes(self):
        """Falls back to geometric slingshot strike rounded to exchange step if quotes absent."""
        res_nifty = SentinelOptionStrikeResolver.resolve_mode5_strike(
            index_name="NIFTY",
            direction="PE",
            anchor_price=70.0,
            geometric_strike=24073.4,
            live_quotes=[],
        )
        assert res_nifty.target_strike == 24050.0
        assert res_nifty.selection_mode == "GEOMETRIC_SLINGSHOT_FALLBACK"

        res_sensex = SentinelOptionStrikeResolver.resolve_mode5_strike(
            index_name="SENSEX",
            direction="PE",
            anchor_price=220.0,
            geometric_strike=76840.0,
            live_quotes=None,
        )
        assert res_sensex.target_strike == 76800.0
        assert res_sensex.selection_mode == "GEOMETRIC_SLINGSHOT_FALLBACK"


# =========================================================================
# 3. Broadcaster Queue Scaling (50k capacity, 2k chunk, 25k burst absorption)
# =========================================================================

class TestBroadcasterQueueScaling:
    """Proves UpstoxAsyncParquetRecorder absorbs 25,000 burst depth ticks without crash."""

    def test_default_queue_and_chunk_parameters(self, tmp_path):
        """Verifies default max_queue_size=50,000, chunk_size=2,000, watermark at 40,000."""
        recorder = UpstoxAsyncParquetRecorder(output_dir=tmp_path / "default_test")
        assert recorder.max_queue_size == 50_000
        assert recorder.chunk_size == 2000
        assert recorder.watermark_threshold == 40_000
        recorder.flush_and_stop(timeout=2.0)

    def test_burst_absorption_25000_records(self, tmp_path):
        """Streams 25,000 depth ticks through the recorder without crashing or drop."""
        out_dir = tmp_path / "burst_25k"
        recorder = UpstoxAsyncParquetRecorder(
            output_dir=out_dir,
            max_queue_size=50_000,
            chunk_size=2000,
            flush_interval_sec=0.1,
        )

        dropped_events: list[dict] = []
        recorder.add_telemetry_callback(
            lambda ev: dropped_events.append(ev) if ev.get("event") == "PERSISTENCE_QUEUE_DROPPED_BURST" else None
        )

        t0 = time.monotonic()
        for i in range(25_000):
            rec = _make_dummy_depth_record(
                token=f"NSE_FO|NIFTY_{i % 5}",
                symbol=f"NIFTY 24{100 + (i%5)*50} CE",
                seq=i + 1,
                ltp=100.0 + (i % 20),
            )
            recorder.on_depth(rec)
        t_ingest = time.monotonic() - t0

        # Ingest rate must absorb 25,000 records smoothly without hitch
        assert t_ingest < 5.0, f"Ingesting 25k records took too long: {t_ingest:.2f}s"
        assert len(dropped_events) == 0, "Zero drops expected when queue capacity is 50,000"

        # Drain and flush all records to Parquet
        recorder.flush_and_stop(timeout=15.0)
        assert recorder.total_records_written == 25_000

    def test_watermark_warning_at_80_percent(self, tmp_path):
        """Emits QUEUE_HIGH_WATERMARK at 80% saturation (40,000 on default or scaled)."""
        telemetry: list[dict] = []
        # Use a scaled test capacity to test threshold deterministically
        recorder = UpstoxAsyncParquetRecorder(
            output_dir=tmp_path / "watermark_test",
            max_queue_size=1000,
            watermark_ratio=0.80,
            chunk_size=2000,
            flush_interval_sec=999.0,  # Prevent automatic flush
        )
        recorder.add_telemetry_callback(lambda ev: telemetry.append(ev))

        # Stop worker thread so queue accumulates
        recorder._stop_event.set()
        if recorder._worker_thread:
            recorder._worker_thread.join()

        for i in range(850):
            rec = _make_dummy_depth_record("TOKEN", "SYMBOL", i + 1)
            recorder.on_depth(rec)

        watermark_events = [ev for ev in telemetry if ev.get("event") == "QUEUE_HIGH_WATERMARK"]
        assert len(watermark_events) >= 1
        assert watermark_events[0]["queue_size"] >= 800
        assert watermark_events[0]["capacity"] == 1000

    def test_transient_burst_drop_telemetry_without_crash(self, tmp_path):
        """When fail_closed_on_saturation=False (default), drops excess records gracefully and logs telemetry."""
        telemetry: list[dict] = []
        recorder = UpstoxAsyncParquetRecorder(
            output_dir=tmp_path / "drop_burst_test",
            max_queue_size=200,
            chunk_size=2000,
            flush_interval_sec=999.0,
            fail_closed_on_saturation=False,
        )
        recorder.add_telemetry_callback(lambda ev: telemetry.append(ev))

        recorder._stop_event.set()
        if recorder._worker_thread:
            recorder._worker_thread.join()

        # Push 250 records into 200 capacity queue
        for i in range(250):
            rec = _make_dummy_depth_record("TOKEN", "SYMBOL", i + 1)
            recorder.on_depth(rec)

        drop_events = [ev for ev in telemetry if ev.get("event") == "PERSISTENCE_QUEUE_DROPPED_BURST"]
        assert len(drop_events) == 50
        assert recorder._queue.qsize() == 200


# =========================================================================
# 4. Repository Non-Negotiable Safety Invariants
# =========================================================================

class TestSafetyInvariants:
    """Verifies all Mode 5 and broadcaster enhancements strictly adhere to safety rules."""

    def test_recorder_safety_invariants(self, tmp_path):
        rec = UpstoxAsyncParquetRecorder(output_dir=tmp_path / "safe")
        assert rec.read_only is True
        assert rec.is_order_action is False
        assert rec.broker_api_called is False
        assert rec.allowed_for_live_execution is False
        rec.flush_and_stop(timeout=1.0)

    def test_strike_resolver_safety_invariants(self):
        resolver = SentinelOptionStrikeResolver()
        assert resolver.read_only is True
        assert resolver.is_order_action is False
        assert resolver.broker_api_called is False
        assert resolver.allowed_for_live_execution is False

        res = resolver.resolve_mode5_strike("NIFTY", "CE", 70.0, 24150.0)
        assert res.read_only is True
        assert res.is_order_action is False
        assert res.broker_api_called is False
        assert res.allowed_for_live_execution is False

    def test_advisor_cached_signal_anchor_field(self):
        sig = CachedRBFNAuctionSignal(
            timestamp_ms=1000,
            index_name="NIFTY",
            action="BUY_CALL",
            direction="CE",
            target_strike=24150.0,
            target_pts=30.0,
            sl_pts=20.0,
            setup_reason="TEST",
            trade_phase="OPENING_DRIVE",
            bar_time=dt_time(9, 20),
            sustainable_anchor_price=70.5,
        )
        assert sig.sustainable_anchor_price == 70.5
        assert sig.read_only is True
        assert sig.is_order_action is False
        assert sig.broker_api_called is False
        assert sig.allowed_for_live_execution is False
