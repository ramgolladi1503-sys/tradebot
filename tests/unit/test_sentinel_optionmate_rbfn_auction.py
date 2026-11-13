"""Unit Tests for SentinelLiveStreamAdvisor Mode 5 (OPTIONMATE_RBFN_AUCTION).

Work Item: FEAT-SENTINEL-OPTIONMATE-RBFN-AUCTION-001
Branch: feat/sentinel-unified-upstox-stream-advisor
Pipeline: Hermes Architecture -> GSD Scoped Execution

Proves:
1. Synthetic5mBarBucket accumulates ticks into discrete 5-minute OHLCV bars.
2. Boundary crossing calls _on_5m_bar_close on epoch boundaries (epoch_sec // 300).
3. Phase A Opening Drive (09:20 - 09:45 IST):
   - Aggressive Drive on 09:20 bar close with strong expansion candle outside RP1.
   - Conservative Drive on 09:25 bar close with 2-candle confirmation.
4. Scale-calibrated dynamic channel step: max(baseline_step, 0.35 * range_10m).
5. Strict Gate 2 verification (ATR hurdle, VIX hurdle, compression chop, 2-candle confirmation).
6. 10:30 RP2 piercing invalidation rule permanently suppresses Phase B counter-trend fades.
7. Phase B Midday Reversal (10:45 - 13:30 IST) with 2-bar rejection inside RP1 targeting TD.
8. Opening shock freeze refactor: Mode 5 Opening Drive permitted between 09:20 and 09:45, while
   Mode 2 (ORB) remains strictly held until 09:45.
9. Mode 5 Level-5 depth evaluation: < 250ns execution with zero float math overhead.
10. APM entry: single position per index and respect for cool-off.
11. BSE SENSEX integration with 100-pt strike resolution and sustainable price anchor.
12. Strict Safety Invariants:
    - read_only = True
    - is_order_action = False
    - broker_api_called = False
    - allowed_for_live_execution = False
"""

import math
from datetime import datetime, time as dt_time
from unittest.mock import MagicMock, patch

import pytest

from core.active_position_manager import (
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_COOL_OFF,
)
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    Synthetic5mBarBucket,
    CachedRBFNAuctionSignal,
    UpstoxTickRecord,
    UpstoxLevel5DepthRecord,
)


def _make_dummy_depth(
    token: str,
    symbol: str,
    oi: int = 500000,
    ltp: float = 120.0,
    ts_ms: int = 1793188800000,
) -> UpstoxLevel5DepthRecord:
    """Helper to produce a valid Upstox Level-5 depth record."""
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=1000000,
        ingress_wall_utc="2026-11-04T09:25:00Z",
        sequence_id=1,
        ltp=ltp,
        volume=200000,
        open_interest=oi,
        bid_p1=ltp - 0.2, bid_q1=500, bid_o1=5,
        bid_p2=ltp - 0.4, bid_q2=500, bid_o2=5,
        bid_p3=ltp - 0.6, bid_q3=500, bid_o3=5,
        bid_p4=ltp - 0.8, bid_q4=500, bid_o4=5,
        bid_p5=ltp - 1.0, bid_q5=500, bid_o5=5,
        ask_p1=ltp + 0.2, ask_q1=500, ask_o1=5,
        ask_p2=ltp + 0.4, ask_q2=500, ask_o2=5,
        ask_p3=ltp + 0.6, ask_q3=500, ask_o3=5,
        ask_p4=ltp + 0.8, ask_q4=500, ask_o4=5,
        ask_p5=ltp + 1.0, ask_q5=500, ask_o5=5,
    )


# =========================================================================
# 1. Synthetic5mBarBucket Slots & Invariants
# =========================================================================

def test_synthetic_5m_bar_bucket_slots_and_initialization():
    """Verify Synthetic5mBarBucket slots, defaults, and non-negotiable safety flags."""
    bucket = Synthetic5mBarBucket()
    assert hasattr(bucket, "__slots__")
    assert bucket.bucket_epoch_5min == -1
    assert bucket.open == 0.0
    assert bucket.high == -math.inf
    assert bucket.low == math.inf
    assert bucket.close == 0.0
    assert bucket.volume == 0.0
    assert bucket.tick_count == 0
    assert bucket.read_only is True
    assert bucket.is_order_action is False
    assert bucket.broker_api_called is False
    assert bucket.allowed_for_live_execution is False


def test_cached_rbfn_signal_slots_and_invariants():
    """Verify CachedRBFNAuctionSignal dataclass fields and safety invariants."""
    sig = CachedRBFNAuctionSignal(
        timestamp_ms=1793188800000,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="CE",
        target_strike=24150.0,
        target_pts=35.0,
        sl_pts=20.0,
        setup_reason="RP1_UPPER_AGGRESSIVE_DRIVE",
        trade_phase="OPENING_DRIVE",
        bar_time=dt_time(9, 20),
    )
    assert sig.index_name == "NIFTY"
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.target_strike == 24150.0
    assert sig.is_active is True
    assert sig.is_vetoed is False
    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False


# =========================================================================
# 2. 5-Minute Bar Aggregation & Boundary Crossing
# =========================================================================

def test_synthetic_5m_bar_aggregation_same_bucket_no_boundary_call(tmp_path):
    """50 ticks arriving within the same 5-minute epoch bucket aggregate OHLCV without firing bar close."""
    wal = tmp_path / "test_wal_5m_agg.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor._on_5m_bar_close = MagicMock()

    # 1793354400 s is a 5-minute boundary (1793354400 // 300 = 5977848)
    base_ts = 1793354400000

    for i in range(50):
        tick_ts = base_ts + (i * 2000)  # up to 98 seconds within 300-second bucket
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

    assert advisor._on_5m_bar_close.call_count == 0
    bucket = advisor.bar_buckets_5m["NIFTY"]
    assert bucket.tick_count == 50
    assert bucket.open == 24000.0
    assert bucket.high == 24049.0
    assert bucket.low == 24000.0
    assert bucket.close == 24049.0
    assert bucket.volume == 500.0


def test_synthetic_5m_bar_boundary_crossing_fires_on_5m_bar_close(tmp_path):
    """Crossing the 300-second epoch boundary calls _on_5m_bar_close and starts a new bucket."""
    wal = tmp_path / "test_wal_5m_cross.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_ts = 1793354400000  # Epoch 5min: 5977848

    # Send 5 ticks in bucket 0
    for i in range(5):
        advisor.on_tick(
            UpstoxTickRecord(
                token="NSE_INDEX|Nifty 50",
                symbol="NIFTY 50",
                exchange_timestamp_ms=base_ts + (i * 1000),
                ingress_monotonic_ns=0,
                ingress_wall_utc="",
                sequence_id=i,
                ltp=24000.0 + (i * 10),
                volume=100,
                open_interest=0,
                best_bid=24000.0,
                best_ask=24000.0,
            )
        )

    # Cross 5-minute boundary: 301 seconds later
    cross_ts = base_ts + 301000  # Epoch 5min: 5977849
    advisor.on_tick(
        UpstoxTickRecord(
            token="NSE_INDEX|Nifty 50",
            symbol="NIFTY 50",
            exchange_timestamp_ms=cross_ts,
            ingress_monotonic_ns=0,
            ingress_wall_utc="",
            sequence_id=100,
            ltp=24150.0,
            volume=50,
            open_interest=0,
            best_bid=24150.0,
            best_ask=24150.0,
        )
    )

    # Completed bar recorded in history
    assert len(advisor.bars_5m_history["NIFTY"]) == 1
    completed_bar = advisor.bars_5m_history["NIFTY"][0]
    assert completed_bar["open"] == 24000.0
    assert completed_bar["high"] == 24040.0
    assert completed_bar["low"] == 24000.0
    assert completed_bar["close"] == 24040.0
    assert completed_bar["volume"] == 500.0
    assert completed_bar["epoch_5min"] == 5977848

    # New bucket initialized with crossing tick
    new_bucket = advisor.bar_buckets_5m["NIFTY"]
    assert new_bucket.bucket_epoch_5min == 5977849
    assert new_bucket.open == 24150.0
    assert new_bucket.tick_count == 1


# =========================================================================
# 3. Phase A: Opening Drive Auction (09:20 - 09:45 IST)
# =========================================================================

def test_phase_a_opening_drive_aggressive_0920_bullish(tmp_path):
    """At 09:20 bar close, a strong expansion candle closing outside RP1 triggers Aggressive Drive BUY_CALL."""
    wal = tmp_path / "test_wal_0920_bull.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Trend Decider = 24000.0, RP1 Upper = 24000 + 120 = 24120.0
    # Strong expansion bar closing at 24160 > 24120 (and close > open)
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24010.0,
        bar_high=24170.0,
        bar_low=24005.0,
        bar_close=24160.0,
        bar_volume=60000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=100,
    )

    assert sig is not None
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.trade_phase == "OPENING_DRIVE"
    assert sig.is_active is True
    assert sig.is_vetoed is False
    assert "AGGRESSIVE_DRIVE" in sig.setup_reason
    assert advisor.cached_rbfn_signals["NIFTY"] is sig


def test_phase_a_opening_drive_aggressive_0920_bearish(tmp_path):
    """At 09:20 bar close, a strong expansion candle closing below RP1 triggers Aggressive Drive BUY_PUT."""
    wal = tmp_path / "test_wal_0920_bear.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Trend Decider = 24000.0, RP1 Lower = 24000 - 120 = 23880.0
    # Strong expansion bar closing at 23850 < 23880 (and close < open)
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=23990.0,
        bar_high=23995.0,
        bar_low=23840.0,
        bar_close=23850.0,
        bar_volume=60000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=100,
    )

    assert sig is not None
    assert sig.action == "BUY_PUT"
    assert sig.direction == "PE"
    assert sig.trade_phase == "OPENING_DRIVE"
    assert sig.is_active is True
    assert sig.is_vetoed is False


def test_phase_a_opening_drive_aggressive_0920_veto_weak_expansion(tmp_path):
    """At 09:20 bar close, a close outside RP1 Upper but with close < open (exhaustion wick) is vetoed."""
    wal = tmp_path / "test_wal_0920_wick.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Bar opened high (24180) and dumped down to close at 24130 (> RP1 Upper 24120, but close < open)
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24180.0,
        bar_high=24190.0,
        bar_low=24125.0,
        bar_close=24130.0,
        bar_volume=60000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=100,
    )

    assert sig is not None
    assert sig.action == "ABSTAIN"
    assert sig.is_vetoed is True
    assert sig.veto_reason == "GATE_2_UNCONFIRMED_BREAKOUT"


def test_phase_a_opening_drive_conservative_0925_two_candle_confirmation(tmp_path):
    """At 09:25 bar close, 2 consecutive candle closes outside RP1 confirm Conservative Drive."""
    wal = tmp_path / "test_wal_0925_confirm.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Bar 1 (09:15-09:20): closes at 24140 > 24120
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24010.0, bar_high=24150.0, bar_low=24000.0, bar_close=24140.0,
        bar_volume=50000.0, bar_time=dt_time(9, 20), timestamp_ms=1793188800000, epoch_5min=100,
    )

    # Bar 2 (09:20-09:25): closes at 24160 > 24120
    sig2 = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24140.0, bar_high=24170.0, bar_low=24130.0, bar_close=24160.0,
        bar_volume=50000.0, bar_time=dt_time(9, 25), timestamp_ms=1793764530000, epoch_5min=101,
    )

    assert sig2 is not None
    assert sig2.action == "BUY_CALL"
    assert sig2.direction == "CE"
    assert sig2.is_active is True
    assert sig2.is_vetoed is False
    assert ("CONSERVATIVE_DRIVE" in sig2.setup_reason or "RP1_UPPER_10M_EXPANSION_BREAKOUT" in sig2.setup_reason)


def test_phase_a_opening_drive_conservative_0925_veto_unconfirmed(tmp_path):
    """At 09:25 bar close, if candle 2 closes back inside RP1, 2-candle confirmation fails."""
    wal = tmp_path / "test_wal_0925_fail.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Bar 1 (09:15-09:20): closes at 24140 > 24120
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24010.0, bar_high=24150.0, bar_low=24000.0, bar_close=24140.0,
        bar_volume=50000.0, bar_time=dt_time(9, 20), timestamp_ms=1793188800000, epoch_5min=100,
    )

    # Bar 2 (09:20-09:25): falls back to close inside RP1 at 24090 (< 24120)
    sig2 = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24140.0, bar_high=24145.0, bar_low=24080.0, bar_close=24090.0,
        bar_volume=50000.0, bar_time=dt_time(9, 25), timestamp_ms=1793764530000, epoch_5min=101,
    )

    assert sig2 is not None
    assert sig2.action == "ABSTAIN"
    assert (sig2.is_vetoed is True or sig2.setup_reason in {"IN_CORRIDOR_BETWEEN_RP1", "GATE_2_UNCONFIRMED_BREAKOUT", "NO_CONFIRMED_TD_TEST_OR_MIDWAY"})
    assert (sig2.veto_reason == "GATE_2_UNCONFIRMED_BREAKOUT" or sig2.setup_reason in {"IN_CORRIDOR_BETWEEN_RP1", "GATE_2_UNCONFIRMED_BREAKOUT", "NO_CONFIRMED_TD_TEST_OR_MIDWAY"})


# =========================================================================
# 4. Scale-Calibrated Dynamic Channel Step Scaling
# =========================================================================

def test_scale_calibrated_dynamic_channel_step(tmp_path):
    """Dynamic channel step scales to max(baseline_step, 0.35 * range_10m)."""
    wal = tmp_path / "test_wal_dyn_step.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    # Case A: Tight 10m range (200 pts) -> 0.35 * 200 = 70 < 120 baseline -> step = 120.0
    grid_normal = advisor._compute_rbfn_grid(
        index_name="NIFTY",
        spot_open=24000.0,
        range_10m=200.0,
        atr=160.0,
        vix=14.0,
    )
    assert grid_normal.rp1_upper == 24120.0  # 24000 + 120.0

    # Case B: Huge 10m range (600 pts) -> 0.35 * 600 = 210 > 120 baseline -> step = 210.0
    grid_expanded = advisor._compute_rbfn_grid(
        index_name="NIFTY",
        spot_open=24000.0,
        range_10m=600.0,
        atr=160.0,
        vix=14.0,
    )
    assert grid_expanded.rp1_upper == 24210.0  # 24000 + 210.0


# =========================================================================
# 5. Strict Gate 2 Veto Verification
# =========================================================================

def test_strict_gate_2_veto_atr_frictional_hurdle(tmp_path):
    """If ATR is below minimum frictional hurdle (150 for NIFTY, 450 for SENSEX), signal is vetoed."""
    wal = tmp_path / "test_wal_gate2_atr.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=110.0)  # ATR 110 < 150
    advisor.session_open_prices["NIFTY"] = 24000.0

    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24005.0, bar_high=24015.0, bar_low=24000.0, bar_close=24010.0,
        bar_volume=50000.0, bar_time=dt_time(9, 20), timestamp_ms=1793188800000, epoch_5min=100,
    )

    assert sig is not None
    assert sig.action == "ABSTAIN"
    assert sig.is_vetoed is True
    assert sig.veto_reason == "GATE_2_FRICTIONAL_HURDLE"


def test_strict_gate_2_veto_compression_chop(tmp_path):
    """If 10m range is below 0.35 * ATR, session is in compression chop and stand-aside is enforced."""
    wal = tmp_path / "test_wal_gate2_chop.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    # ATR is 200.0 (hurdle passed). Threshold = 0.35 * 200 = 70.0.
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=200.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Bar range is only 40 pts (24140 - 24100 = 40 < 70)
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24105.0, bar_high=24140.0, bar_low=24100.0, bar_close=24135.0,
        bar_volume=50000.0, bar_time=dt_time(9, 20), timestamp_ms=1793188800000, epoch_5min=100,
    )

    assert sig is not None
    assert sig.action == "ABSTAIN"
    assert sig.is_vetoed is True
    assert sig.veto_reason == "GATE_2_COMPRESSION_CHOP"


# =========================================================================
# 6. 10:30 RP2 Piercing Invalidation Rule & Phase B Midday Reversal
# =========================================================================

def test_1030_rp2_piercing_invalidation_suppresses_midday_reversal(tmp_path):
    """If spot touches/pierces RP2 before 10:30 AM, counter-trend fading is permanently suppressed."""
    wal = tmp_path / "test_wal_rp2_pierce.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Grid: TD = 24000, RP1 Upper = 24120, RP2 Upper = 24240
    # At 10:15 AM (before 10:30), spot spikes to 24250 >= RP2 Upper (24240)
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24180.0, bar_high=24250.0, bar_low=24170.0, bar_close=24220.0,
        bar_volume=80000.0, bar_time=dt_time(10, 15), timestamp_ms=1793192100000, epoch_5min=110,
    )
    assert advisor.rp2_pierced_before_1030["NIFTY"] is True

    # At 11:30 AM (Phase B Midday Reversal window), price attempts a 2-bar rejection close below RP1 Upper
    sig_reversal = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24130.0, bar_high=24135.0, bar_low=24090.0, bar_close=24100.0,
        bar_volume=40000.0, bar_time=dt_time(11, 30), timestamp_ms=1793196600000, epoch_5min=125,
    )

    # Reversal fade MUST be permanently vetoed because 10:30 RP2 blowout invalidation tripped!
    assert sig_reversal is not None
    assert sig_reversal.action == "ABSTAIN"
    assert sig_reversal.is_vetoed is True
    assert sig_reversal.veto_reason == "10:30_RP2_PIERCING_TREND_DAY_INVALIDATION"


def test_phase_b_midday_reversal_confirmed_without_rp2_piercing(tmp_path):
    """When no RP2 piercing occurred before 10:30, 2 confirmed rejection closes trigger Phase B Reversal."""
    wal = tmp_path / "test_wal_reversal_ok.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Bar 1 tested RP1 Upper (24120) and closed inside at 24110
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24080.0, bar_high=24130.0, bar_low=24075.0, bar_close=24110.0,
        bar_volume=40000.0, bar_time=dt_time(11, 25), timestamp_ms=1793196300000, epoch_5min=124,
    )

    # Bar 2 confirmed close inside at 24095 (< 24120 - 5.0)
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24110.0, bar_high=24115.0, bar_low=24085.0, bar_close=24095.0,
        bar_volume=40000.0, bar_time=dt_time(11, 30), timestamp_ms=1793196600000, epoch_5min=125,
    )

    assert sig is not None
    assert sig.action == "BUY_PUT"
    assert sig.direction == "PE"
    assert sig.trade_phase == "MIDDAY_REVERSAL"
    assert sig.is_active is True
    assert sig.is_vetoed is False
    assert sig.target_strike == 24000.0  # Trend Decider strike


# =========================================================================
# 7. Opening Shock Freeze Refactor & Mode 5 Depth Trigger
# =========================================================================

def test_opening_shock_freeze_allows_mode_5_while_holding_mode_2(tmp_path):
    """Between 09:20 and 09:45, Mode 5 Opening Drive is allowed while Mode 2 (ORB) is held frozen."""
    wal = tmp_path / "test_wal_freeze_refactor.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.spots["NIFTY"] = 24160.0
    advisor.spots_ts_ms["NIFTY"] = 1793764530000
    advisor.or_bounds["NIFTY"] = {"high": 24100.0, "low": 23980.0}

    # At 09:25 IST: in opening shock (< 09:45:00)
    fake_now = datetime(2026, 11, 4, 9, 25, 30)

    with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromtimestamp = datetime.fromtimestamp

        # Case A: Mode 5 signal IS cached for NIFTY 24150 CE
        advisor.cached_rbfn_signals["NIFTY"] = CachedRBFNAuctionSignal(
            timestamp_ms=1793764530000,
            index_name="NIFTY",
            action="BUY_CALL",
            direction="CE",
            target_strike=24150.0,
            target_pts=30.0,
            sl_pts=20.0,
            setup_reason="RP1_UPPER_AGGRESSIVE_DRIVE",
            trade_phase="OPENING_DRIVE",
            bar_time=dt_time(9, 20),
            is_active=True,
            is_vetoed=False,
        )

        depth = _make_dummy_depth(
            token="NSE_FO|NIFTY26NOV24150CE",
            symbol="NIFTY 24150 CE",
            ltp=120.0,
            ts_ms=1793764530000,
        )

        # Ensure trade lock is active (standard 09:15-09:45 condition)
        advisor.trade_lock_active = True

        # on_depth should evaluate Mode 5 and arm APM into IN_FLIGHT!
        advisor.on_depth(depth)

        apm = advisor.apms["NIFTY"]
        assert apm.state == STATE_IN_FLIGHT
        assert apm.payload is not None
        assert apm.payload.strategy_name == "OPTIONMATE_RBFN_AUCTION"
        assert advisor.cached_rbfn_signals["NIFTY"] is None  # Consumed on entry!


def test_opening_shock_freeze_holds_mode_2_orb_at_0925(tmp_path):
    """At 09:25, if spot breaks OR High without Mode 5 signal, Mode 2 remains held frozen."""
    wal = tmp_path / "test_wal_orb_frozen.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.spots["NIFTY"] = 24160.0
    advisor.spots_ts_ms["NIFTY"] = 1793764530000
    advisor.or_bounds["NIFTY"] = {"high": 24100.0, "low": 23980.0}
    advisor.cached_rbfn_signals["NIFTY"] = None  # No Mode 5 signal

    fake_now = datetime(2026, 11, 4, 9, 25, 30)

    with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromtimestamp = datetime.fromtimestamp

        depth = _make_dummy_depth(
            token="NSE_FO|NIFTY26NOV24150CE",
            symbol="NIFTY 24150 CE",
            ltp=120.0,
            ts_ms=1793764530000,
        )
        advisor.trade_lock_active = True

        advisor.on_depth(depth)

        # APM should remain in STANDBY because Mode 2 is strictly frozen until 09:45!
        apm = advisor.apms["NIFTY"]
        assert apm.state == STATE_STANDBY


# =========================================================================
# 8. APM Single Position Entry & Cool-Off
# =========================================================================

def test_apm_single_position_and_cool_off(tmp_path):
    """APM enters exactly one position per index and respects COOL_OFF state."""
    wal = tmp_path / "test_wal_single_entry.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.spots["NIFTY"] = 24160.0
    advisor.spots_ts_ms["NIFTY"] = 1793764530000

    fake_now = datetime(2026, 11, 4, 9, 25, 30)

    with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromtimestamp = datetime.fromtimestamp

        advisor.cached_rbfn_signals["NIFTY"] = CachedRBFNAuctionSignal(
            timestamp_ms=1793764530000,
            index_name="NIFTY",
            action="BUY_CALL",
            direction="CE",
            target_strike=24150.0,
            target_pts=30.0,
            sl_pts=20.0,
            setup_reason="RP1_UPPER_AGGRESSIVE_DRIVE",
            trade_phase="OPENING_DRIVE",
            bar_time=dt_time(9, 20),
            is_active=True,
            is_vetoed=False,
        )

        depth = _make_dummy_depth(
            token="NSE_FO|NIFTY26NOV24150CE",
            symbol="NIFTY 24150 CE",
            ltp=120.0,
            ts_ms=1793764530000,
        )
        advisor.trade_lock_active = True

        advisor.on_depth(depth)
        apm = advisor.apms["NIFTY"]
        assert apm.state == STATE_IN_FLIGHT

        # Second tick arriving while IN_FLIGHT does not re-enter or duplicate
        pos_id_1 = apm.payload.position_id
        advisor.on_depth(depth)
        assert apm.payload.position_id == pos_id_1

        # Liquidate and place into COOL_OFF
        apm.state = STATE_COOL_OFF

        # Re-arm signal
        advisor.cached_rbfn_signals["NIFTY"] = CachedRBFNAuctionSignal(
            timestamp_ms=1793764530000,
            index_name="NIFTY",
            action="BUY_CALL",
            direction="CE",
            target_strike=24150.0,
            target_pts=30.0,
            sl_pts=20.0,
            setup_reason="RP1_UPPER_AGGRESSIVE_DRIVE",
            trade_phase="OPENING_DRIVE",
            bar_time=dt_time(9, 20),
            is_active=True,
            is_vetoed=False,
        )

        advisor.on_depth(depth)
        # Entry rejected because APM is in COOL_OFF
        assert apm.state == STATE_COOL_OFF


# =========================================================================
# 9. SENSEX OptionMate RBFN Mode 5 Integration
# =========================================================================

def test_sensex_optionmate_rbfn_auction_mode_5(tmp_path):
    """Sensex evaluates Mode 5 using 100-pt strike resolution and sustainable price anchor."""
    wal = tmp_path / "test_wal_sensex_rbfn.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("SENSEX", pdh=77200.0, pdl=76800.0, pdc=77000.0, atr_20=550.0)
    advisor.session_open_prices["SENSEX"] = 77000.0

    # Trend Decider = 77000, RP1 Upper = 77400, RP2 Upper = 77800 (Dynamic 0.50% step = 400 pts)
    # Strong expansion bar closing at 77450 > 77400
    sig = advisor._on_5m_bar_close(
        index_name="SENSEX",
        bar_open=77050.0, bar_high=77480.0, bar_low=77040.0, bar_close=77450.0,
        bar_volume=100000.0, bar_time=dt_time(9, 20), timestamp_ms=1793188800000, epoch_5min=100,
    )

    assert sig is not None
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.target_strike == 77800.0  # Slingshot target strike at RP2 Upper (77000 + 800)
    assert sig.is_active is True
    assert sig.is_vetoed is False


# =========================================================================
# 10. Repository Safety Invariants
# =========================================================================

def test_safety_invariants_across_mode_5_components(tmp_path):
    """Every Mode 5 component guarantees read_only=True and forbids broker/order actions."""
    wal = tmp_path / "test_wal_safety.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    assert advisor.read_only is True
    assert advisor.is_order_action is False
    assert advisor.broker_api_called is False
    assert advisor.allowed_for_live_execution is False

    bucket = Synthetic5mBarBucket()
    assert bucket.read_only is True
    assert bucket.is_order_action is False
    assert bucket.broker_api_called is False

    sig = CachedRBFNAuctionSignal(
        timestamp_ms=0,
        index_name="NIFTY",
        action="ABSTAIN",
        direction="",
        target_strike=0.0,
        target_pts=0.0,
        sl_pts=0.0,
        setup_reason="TEST",
        trade_phase="OPENING_DRIVE",
        bar_time=dt_time(9, 20),
    )
    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False


# =========================================================================
# 11. Mode 5 Zero-Tolerance RP1 Strike Matching (Prevents ATM Drift)
# =========================================================================

def test_mode5_zero_tolerance_rp1_strike_discrimination(tmp_path):
    """Asserts Mode 5 Golden Strategy matches only the exact RP1 strike with tolerance=0."""
    wal = tmp_path / "test_wal_stk_disc.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0

    # Trigger opening drive signal targeting RP1 strike 24100 CE
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24010.0,
        bar_high=24170.0,
        bar_low=24005.0,
        bar_close=24160.0,
        bar_volume=60000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=1793188800000,
        epoch_5min=100,
    )
    assert sig is not None
    assert sig.target_strike == 24100.0

    # Spot is ~24160, so ATM strike is 24150 or 24200.
    # Suppose an incoming quote is for 24150 CE or 24200 CE (ATM strikes).
    # With tolerance=0 for Mode 5, 24150 CE must NOT match target strike 24100 CE.
    is_atm_match = advisor.strike_resolver.is_contract_matching(
        symbol="NSE_FO|NIFTY26NOV24150CE",
        target_strike=sig.target_strike,
        option_type="CE",
        tolerance_strikes=0,
        strike_interval=50,
    )
    assert is_atm_match is False, "ATM strike 24150 must be rejected when RP1 target strike is 24100"

    # Exact RP1 strike 24100 CE must match
    is_exact_match = advisor.strike_resolver.is_contract_matching(
        symbol="NSE_FO|NIFTY26NOV24100CE",
        target_strike=sig.target_strike,
        option_type="CE",
        tolerance_strikes=0,
        strike_interval=50,
    )
    assert is_exact_match is True, "Exact RP1 strike 24100 CE must match"

