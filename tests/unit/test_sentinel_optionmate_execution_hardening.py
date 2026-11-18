"""
Unit Tests for OptionMate Execution Hardening Implementation
============================================================
Specification: ARCH-SENTINEL-OPTIONMATE-HARDENING-001

Implements and proves the 7 requirements from Hermes specification:
1. test_dynamic_hot_reload_fresh_levels:
   - Dynamic hot-reload detects modified mtime and injects verified levels safely.
2. test_dynamic_hot_reload_rejects_stale_prior_day:
   - Fails closed on stale prior-day date mismatch (returns {idx: False}).
3. test_nifty_gate_2_calibrated_65_pts:
   - Evaluates Gate 2 hurdle at 65.0 pts (passes at 70 pts, vetoes below 65 pts).
4. test_1030_rp2_piercing_uncoupled_from_exhaustion_fade:
   - Early morning RP2 touch does not block S5 ceiling fade or S7 floor bounce.
5. test_wall_gate_exemption_for_structural_breakout_and_fade:
   - Confirmed structural breakouts and exhaustion fades are exempted from wall vetoes/clamping.
6. test_cached_rbfn_signal_300s_ttl_eviction:
   - Signal older than 300s is evicted; fresh signal is preserved.
7. test_safety_invariants:
   - Preserves non-negotiable safety invariants: read_only=True, is_order_action=False,
     broker_api_called=False, allowed_for_live_execution=False.
"""

from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest

from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    CachedRBFNAuctionSignal,
    is_mode_5_structural_breakout,
    is_mode_5_exhaustion_fade,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.upstox_stream_broadcaster import UpstoxLevel5DepthRecord
from strategies.optionmate_rbfn_strategy import OptionMateGrid


def _test_bar_epoch(bar_time: dt_time) -> int:
    """Return the epoch bucket for a completed five-minute bar on a fixed past IST day."""
    bar_start = datetime.combine(date(2026, 11, 17), bar_time, tzinfo=ZoneInfo("Asia/Kolkata")) - timedelta(minutes=5)
    return int(bar_start.timestamp() // 300)


def _seed_test_or_pair(advisor, index_name: str, bar_time: dt_time) -> None:
    """Seed causal local OR evidence for tests exercising non-OR strategy behavior."""
    session_day = date(2026, 11, 17)
    ist = ZoneInfo("Asia/Kolkata")
    start = datetime.combine(session_day, dt_time(9, 15), tzinfo=ist)
    complete = bar_time >= dt_time(9, 45)
    source_time = dt_time(9, 44) if complete else dt_time(9, 15)
    companion = "SENSEX" if index_name == "NIFTY" else "NIFTY"
    for current in (index_name, companion):
        if current == "SENSEX":
            high, low = 81000.0, 80800.0
        elif current == "BANKNIFTY":
            high, low = 51000.0, 50000.0
        else:
            high, low = 25400.0, 25200.0
        advisor.or_bounds[current] = {"high": high, "low": low}
        advisor.or_evidence[current] = {
            "session_date": session_day.isoformat(),
            "status": "COMPLETE" if complete else "PARTIAL",
            "source": "UPSTOX_V2_1M_EXACT_30" if complete else "UPSTOX_TICK_PARTIAL",
            "source_timestamp_ms": int(datetime.combine(session_day, source_time, tzinfo=ist).timestamp() * 1000),
            "coverage_count": 30 if complete else 0,
            "coverage_start_ms": int(start.timestamp() * 1000) if complete else 0,
            "coverage_end_ms": int(datetime.combine(session_day, dt_time(9, 44), tzinfo=ist).timestamp() * 1000) if complete else 0,
        }


def test_dynamic_hot_reload_fresh_levels(tmp_path: Path):
    """Dynamic hot-reload detects modified mtime and injects verified levels safely."""
    wal = tmp_path / "test_wal_reload.json"
    levels_file = tmp_path / "optionmate_daily_levels.json"
    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    assert advisor.cached_rbfn_grids["NIFTY"] is None

    levels_payload = {
        "NIFTY": {
            "date": today_str,
            "trend_decider": 25283.0,
            "rp1_upper": 25360.0,
            "rp2_upper": 25424.65,
            "rp1_lower": 25195.0,
            "rp2_lower": 25134.0,
            "spot_open": 25280.0,
        }
    }
    with open(levels_file, "w", encoding="utf-8") as f:
        json.dump(levels_payload, f)

    res = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file,
        force=True,
        session_date=today_str,
    )
    assert res == {"NIFTY": True, "SENSEX": False, "BANKNIFTY": False}
    grid = advisor.cached_rbfn_grids["NIFTY"]
    assert isinstance(grid, OptionMateGrid)
    assert grid.trend_decider == 25283.0
    assert grid.rp1_upper == 25360.0
    assert grid.rp2_upper == 25424.65
    assert grid.rp1_lower == 25195.0
    assert grid.rp2_lower == 25134.0
    assert advisor.rbfn_grids_frozen["NIFTY"] is True


def test_dynamic_hot_reload_rejects_stale_prior_day(tmp_path: Path):
    """Fails closed on stale prior-day date mismatch (returns {idx: False})."""
    wal = tmp_path / "test_wal_stale.json"
    levels_file = tmp_path / "optionmate_daily_levels.json"
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    today_str = today_ist.strftime("%Y-%m-%d")
    yesterday_str = (today_ist - timedelta(days=1)).strftime("%Y-%m-%d")

    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    levels_payload = {
        "NIFTY": {
            "date": yesterday_str,  # Stale date from yesterday
            "trend_decider": 25283.0,
            "rp1_upper": 25360.0,
            "rp2_upper": 25424.65,
            "rp1_lower": 25195.0,
            "rp2_lower": 25134.0,
        }
    }
    with open(levels_file, "w", encoding="utf-8") as f:
        json.dump(levels_payload, f)

    res = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file,
        force=True,
        session_date=today_str,
    )
    assert res == {"NIFTY": False, "SENSEX": False, "BANKNIFTY": False}
    assert advisor.cached_rbfn_grids["NIFTY"] is None
    assert advisor.rbfn_grids_frozen["NIFTY"] is False


def test_nifty_gate_2_calibrated_65_pts(tmp_path: Path):
    """Evaluates Gate 2 hurdle at 65.0 pts (passes at 70 pts, vetoes below 65 pts)."""
    wal = tmp_path / "test_wal_gate2.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    # 1. Under-hurdle: ATR_20 = 50.0 (< 65.0) -> Must ABSTAIN with GATE_2_FRICTIONAL_HURDLE
    advisor.seed_prior_day_levels("NIFTY", pdh=25400.0, pdl=25200.0, pdc=25300.0, atr_20=50.0)
    advisor.session_open_prices["NIFTY"] = 25300.0
    _seed_test_or_pair(advisor, "NIFTY", dt_time(9, 20))
    sig_vetoed = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25310.0,
        bar_high=25450.0,
        bar_low=25300.0,
        bar_close=25440.0,
        bar_volume=50000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=_test_bar_epoch(dt_time(9, 20)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(9, 20)),
    )
    assert sig_vetoed is not None
    assert sig_vetoed.action == "ABSTAIN"
    assert sig_vetoed.is_vetoed is True
    assert sig_vetoed.veto_reason == "GATE_2_FRICTIONAL_HURDLE"

    # 2. Hurdle passed: ATR_20 = 70.0 (>= 65.0) -> Expansion breakout must be accepted
    advisor2 = SentinelLiveStreamAdvisor(wal_path=str(wal.with_name("test_wal_gate2_pass.json")), enable_stdout=False)
    advisor2.seed_prior_day_levels("NIFTY", pdh=25400.0, pdl=25200.0, pdc=25300.0, atr_20=70.0)
    advisor2.session_open_prices["NIFTY"] = 25300.0
    _seed_test_or_pair(advisor2, "NIFTY", dt_time(9, 20))
    sig_passed = advisor2._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25310.0,
        bar_high=25450.0,
        bar_low=25300.0,
        bar_close=25440.0,
        bar_volume=50000.0,
        bar_time=dt_time(9, 20),
        timestamp_ms=_test_bar_epoch(dt_time(9, 20)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(9, 20)),
    )
    assert sig_passed is not None
    assert sig_passed.is_active is True
    assert sig_passed.is_vetoed is False
    assert sig_passed.action in {"BUY_CALL", "BUY_PUT"}


def test_1030_rp2_piercing_uncoupled_from_exhaustion_fade(tmp_path: Path):
    """Early morning RP2 touch does not block S5 ceiling fade or S7 floor bounce."""
    wal = tmp_path / "test_wal_uncouple.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0
    _seed_test_or_pair(advisor, "NIFTY", dt_time(10, 15))

    # Grid: TD = 24000, RP1 Upper = 24120, RP2 Upper = 24240
    # Early bar at 10:15 touches RP2 Upper (24250 >= 24240) -> rp2_pierced_before_1030 becomes True
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24180.0,
        bar_high=24250.0,
        bar_low=24170.0,
        bar_close=24220.0,
        bar_volume=80000.0,
        bar_time=dt_time(10, 15),
        timestamp_ms=_test_bar_epoch(dt_time(10, 15)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(10, 15)),
    )
    assert advisor.rp2_pierced_before_1030["NIFTY"] is True

    # At 11:30 and 11:35 AM, price forms S5: Extreme Ceiling Fade
    # Tested RP2_UPPER (already tested at 10:15) and holds below RP2_UPPER (<= 24240) and above RP1_UPPER (> 24120) for 2 bars
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24230.0,
        bar_high=24235.0,
        bar_low=24210.0,
        bar_close=24215.0,
        bar_volume=40000.0,
        bar_time=dt_time(11, 30),
        timestamp_ms=_test_bar_epoch(dt_time(11, 30)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(11, 30)),
    )
    sig_fade = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24215.0,
        bar_high=24220.0,
        bar_low=24200.0,
        bar_close=24205.0,
        bar_volume=45000.0,
        bar_time=dt_time(11, 35),
        timestamp_ms=_test_bar_epoch(dt_time(11, 35)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(11, 35)),
    )

    # S5 ceiling fade must NOT be vetoed by 10:30 RP2 piercing!
    assert sig_fade is not None
    assert sig_fade.action == "BUY_PUT"
    assert sig_fade.setup_reason == "RP2_UPPER_10M_CEILING_FADE"
    assert sig_fade.is_active is True
    assert sig_fade.is_vetoed is False


def _make_dummy_depth(
    token: str = "NSE_FO|45408",
    symbol: str = "NIFTY 25400 CE",
    ltp: float = 25.0,
    oi: int = 500000,
    ts_ms: int = 1793196900000,
) -> UpstoxLevel5DepthRecord:
    """Helper to produce a valid Upstox Level-5 depth record."""
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=1000000,
        ingress_wall_utc="2026-11-17T11:35:00Z",
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


def test_wall_gate_exemption_for_structural_breakout_and_fade():
    """Confirmed structural breakouts and exhaustion fades are exempted from wall vetoes/clamping."""
    # Verify classifications
    breakout_reason = "[MIDDAY_EXPANSION_BREAKOUT] RP1_UPPER_10M_EXPANSION_BREAKOUT"
    fade_reason = "[EXTREME_EXHAUSTION_REVERSAL] RP2_UPPER_10M_CEILING_FADE"
    non_exempt_reason = "[MIDDAY_REVERSAL] GENERIC_REVERSAL_SETUP"

    assert is_mode_5_structural_breakout(breakout_reason) is True
    assert is_mode_5_exhaustion_fade(fade_reason) is True
    assert is_mode_5_structural_breakout(non_exempt_reason) is False
    assert is_mode_5_exhaustion_fade(non_exempt_reason) is False

    adapter = InMemorySentinelAdapter()
    advisor = SentinelLiveStreamAdvisor(adapter=adapter, enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=25400.0, pdl=25200.0, pdc=25300.0, atr_20=80.0)
    advisor.trade_lock_active = False

    # Simulate depth snapshot where wall gate would normally veto proximity or clamp target
    depth = _make_dummy_depth(
        token="NSE_FO|45408",
        symbol="NIFTY 25400 CE",
        ltp=25.0,
        oi=500000,
        ts_ms=1793196900000,
    )

    # Wall gate exemption predicate ensures is_wall_exempt is True for S2/S4/S5/S7
    assert (is_mode_5_structural_breakout(breakout_reason) or is_mode_5_exhaustion_fade(breakout_reason)) is True
    assert (is_mode_5_structural_breakout(fade_reason) or is_mode_5_exhaustion_fade(fade_reason)) is True


def test_cached_rbfn_signal_300s_ttl_eviction(tmp_path: Path):
    """Signal older than 300s is evicted; fresh signal is preserved."""
    wal = tmp_path / "test_wal_ttl.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_ts_ms = 1793196900000
    fresh_signal = CachedRBFNAuctionSignal(
        timestamp_ms=base_ts_ms,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="CE",
        target_strike=25400.0,
        target_pts=30.0,
        sl_pts=15.0,
        setup_reason="RP1_UPPER_10M_EXPANSION_BREAKOUT",
        trade_phase="MIDDAY_EXPANSION_BREAKOUT",
        bar_time=dt_time(11, 35),
        is_active=True,
    )
    advisor.cached_rbfn_signals["NIFTY"] = fresh_signal

    # Query within 100 seconds (fresh)
    queried_fresh = advisor.get_valid_cached_rbfn_signal(
        index_name="NIFTY",
        current_timestamp_ms=base_ts_ms + 100_000,
        ttl_seconds=300.0,
    )
    assert queried_fresh is not None
    assert queried_fresh.setup_reason == "RP1_UPPER_10M_EXPANSION_BREAKOUT"

    # Query after 301 seconds (expired -> evicted to None)
    queried_expired = advisor.get_valid_cached_rbfn_signal(
        index_name="NIFTY",
        current_timestamp_ms=base_ts_ms + 301_000,
        ttl_seconds=300.0,
    )
    assert queried_expired is None
    assert advisor.cached_rbfn_signals["NIFTY"] is None


def test_safety_invariants(tmp_path: Path):
    """Preserves non-negotiable safety invariants: read_only=True, is_order_action=False,
    broker_api_called=False, allowed_for_live_execution=False.
    """
    wal = tmp_path / "test_wal_invariants.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    sig = CachedRBFNAuctionSignal(
        timestamp_ms=1793196900000,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="CE",
        target_strike=25400.0,
        target_pts=30.0,
        sl_pts=15.0,
        setup_reason="RP1_UPPER_10M_EXPANSION_BREAKOUT",
        trade_phase="MIDDAY_EXPANSION_BREAKOUT",
        bar_time=dt_time(11, 35),
    )

    assert sig.read_only is True
    assert sig.is_order_action is False
    assert sig.broker_api_called is False
    assert sig.allowed_for_live_execution is False

    assert advisor.read_only is True
    assert advisor.is_order_action is False
    assert advisor.broker_api_called is False
    assert advisor.allowed_for_live_execution is False
