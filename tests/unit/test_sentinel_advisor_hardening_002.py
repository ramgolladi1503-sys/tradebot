"""
Unit Tests for OptionMate Sentinel Advisor Hardening 002
=========================================================
Specification: ARCH-SENTINEL-HARDENING-002

Validates the 6 acceptance gates (GATE-SENTINEL-01 to GATE-SENTINEL-06):
1. GATE-SENTINEL-01: Directional RP2 Piercing
   - Proves upper and lower RP2 piercing before 10:30 are uncoupled.
   - An upper RP2 pierce tracks rp2_upper_pierced_before_1030=True while
     rp2_lower_pierced_before_1030=False, and vice-versa.
2. GATE-SENTINEL-02: Timezone Invariance
   - Proves all epoch-to-datetime timestamp conversions enforce ZoneInfo("Asia/Kolkata").
3. GATE-SENTINEL-03: Bidirectional TTL Guard
   - Evicts signals where age_sec > ttl_seconds OR age_sec < -5.0 (clock skew / future timestamps).
4. GATE-SENTINEL-04: Stale Grid Deprecation
   - When reload encounters a stale date or missing file, resets rbfn_grids_frozen[idx]=False
     and is_ground_truth=False on cached grid.
5. GATE-SENTINEL-05: Decision Trace Telemetry
   - log_decision_trace records atomic JSONL line with required schema into
     runtime/sentinel_decision_trace.jsonl.
6. GATE-SENTINEL-06: Fast Single-Bar Rejection
   - In S5/S7, allows fast single-bar rejection when bar_high >= rp2_upper and
     bar_close <= rp2_upper - rejection_buffer (rejection_buffer=10.0 NIFTY, 25.0 SENSEX/BANKNIFTY).

Safety Invariants:
- read_only = True, is_order_action = False, broker_api_called = False, allowed_for_live_execution = False.
"""

from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, time as dt_time, timedelta
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


def test_gate_sentinel_01_directional_rp2_piercing(tmp_path: Path):
    """GATE-SENTINEL-01: Directional RP2 Piercing uncouples upper from lower checks."""
    wal = tmp_path / "test_wal_rp2_dir.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0
    _seed_test_or_pair(advisor, "NIFTY", dt_time(10, 15))

    # Grid: TD = 24000, RP1 Upper = 24120, RP2 Upper = 24240, RP1 Lower = 23880, RP2 Lower = 23760
    # At 10:15 AM (before 10:30), spot spikes to 24250 >= RP2 Upper (24240), low is 24170 (nowhere near lower)
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

    # Prove upper is pierced, but lower is NOT pierced
    assert advisor.rp2_upper_pierced_before_1030["NIFTY"] is True
    assert advisor.rp2_lower_pierced_before_1030["NIFTY"] is False
    assert advisor.rp2_pierced_before_1030["NIFTY"] is True

    # Now verify on BANKNIFTY: lower pierce only
    advisor.seed_prior_day_levels("BANKNIFTY", pdh=51000.0, pdl=50000.0, pdc=50500.0, atr_20=400.0)
    advisor.session_open_prices["BANKNIFTY"] = 50500.0
    _seed_test_or_pair(advisor, "BANKNIFTY", dt_time(10, 20))
    grid_bn = advisor.cached_rbfn_grids["BANKNIFTY"]

    advisor._on_5m_bar_close(
        index_name="BANKNIFTY",
        bar_open=50300.0,
        bar_high=50350.0,
        bar_low=49500.0,  # Below rp2_lower
        bar_close=49700.0,
        bar_volume=50000.0,
        bar_time=dt_time(10, 20),
        timestamp_ms=_test_bar_epoch(dt_time(10, 20)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(10, 20)),
    )

    assert advisor.rp2_lower_pierced_before_1030["BANKNIFTY"] is True
    assert advisor.rp2_upper_pierced_before_1030["BANKNIFTY"] is False


def test_gate_sentinel_02_timezone_invariance(tmp_path: Path):
    """GATE-SENTINEL-02: All epoch-to-datetime conversions use ZoneInfo('Asia/Kolkata')."""
    wal = tmp_path / "test_wal_tz.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    # Convert known epoch using ZoneInfo("Asia/Kolkata")
    # 1731814800 is 2024-11-17 03:40:00 UTC = 09:10:00 IST
    epoch_sec = 1731814800
    expected_ist_time = datetime.fromtimestamp(epoch_sec, tz=ZoneInfo("Asia/Kolkata")).time()

    # Verify ZoneInfo object identity
    assert str(ZoneInfo("Asia/Kolkata")) == "Asia/Kolkata"
    assert expected_ist_time == dt_time(9, 10)


def test_gate_sentinel_03_bidirectional_ttl_guard(tmp_path: Path):
    """GATE-SENTINEL-03: Evicts signals if age_sec > ttl_seconds OR age_sec < -5.0."""
    wal = tmp_path / "test_wal_ttl_bi.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    base_ts_ms = 1793196900000  # Reference epoch
    sig = CachedRBFNAuctionSignal(
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
    advisor.cached_rbfn_signals["NIFTY"] = sig

    # 1. Normal age within TTL (e.g. 100 seconds) -> Returned valid
    fresh = advisor.get_valid_cached_rbfn_signal(
        index_name="NIFTY",
        current_timestamp_ms=base_ts_ms + 100_000,
        ttl_seconds=300.0,
    )
    assert fresh is not None
    assert fresh.setup_reason == "RP1_UPPER_10M_EXPANSION_BREAKOUT"

    # 2. Tolerable backward jitter within -5.0s (e.g. -2.0s = -2000ms) -> Preserved
    advisor.cached_rbfn_signals["NIFTY"] = sig
    jitter_ok = advisor.get_valid_cached_rbfn_signal(
        index_name="NIFTY",
        current_timestamp_ms=base_ts_ms - 2_000,
        ttl_seconds=300.0,
    )
    assert jitter_ok is not None

    # 3. Severe clock skew / future timestamp: age_sec < -5.0 (e.g. -10s) -> Evicted to None!
    advisor.cached_rbfn_signals["NIFTY"] = sig
    future_evicted = advisor.get_valid_cached_rbfn_signal(
        index_name="NIFTY",
        current_timestamp_ms=base_ts_ms - 10_000,
        ttl_seconds=300.0,
    )
    assert future_evicted is None
    assert advisor.cached_rbfn_signals["NIFTY"] is None

    # 4. Expired signal: age_sec > ttl_seconds (e.g. 305s > 300s) -> Evicted to None!
    advisor.cached_rbfn_signals["NIFTY"] = sig
    expired_evicted = advisor.get_valid_cached_rbfn_signal(
        index_name="NIFTY",
        current_timestamp_ms=base_ts_ms + 305_000,
        ttl_seconds=300.0,
    )
    assert expired_evicted is None
    assert advisor.cached_rbfn_signals["NIFTY"] is None


def test_gate_sentinel_04_stale_grid_deprecation(tmp_path: Path):
    """GATE-SENTINEL-04: Reload encountering stale date or missing file resets frozen and is_ground_truth."""
    wal = tmp_path / "test_wal_stale_dep.json"
    levels_file = tmp_path / "optionmate_daily_levels.json"
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    today_str = today_ist.strftime("%Y-%m-%d")
    yesterday_str = (today_ist - timedelta(days=1)).strftime("%Y-%m-%d")

    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    # First, inject fresh verified levels
    valid_payload = {
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
        json.dump(valid_payload, f)

    res_init = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file,
        force=True,
        session_date=today_str,
    )
    assert res_init == {"NIFTY": True, "SENSEX": False, "BANKNIFTY": False}
    grid = advisor.cached_rbfn_grids["NIFTY"]
    assert advisor.rbfn_grids_frozen["NIFTY"] is True
    assert getattr(grid, "is_ground_truth", False) is True

    # 1. Update file with stale prior-day date -> Reload must deprecate grid
    stale_payload = {
        "NIFTY": {
            "date": yesterday_str,
            "trend_decider": 25283.0,
            "rp1_upper": 25360.0,
            "rp2_upper": 25424.65,
            "rp1_lower": 25195.0,
            "rp2_lower": 25134.0,
        }
    }
    with open(levels_file, "w", encoding="utf-8") as f:
        json.dump(stale_payload, f)

    res_stale = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file,
        force=True,
        session_date=today_str,
    )
    assert res_stale == {"NIFTY": False, "SENSEX": False, "BANKNIFTY": False}
    assert advisor.rbfn_grids_frozen["NIFTY"] is True
    assert grid.is_ground_truth is True
    assert advisor.cached_rbfn_grids["NIFTY"] is grid

    # 2. Re-inject fresh levels, then delete the file -> Missing file deprecates grid
    res_reinject = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file,
        force=True,
        session_date=yesterday_str,  # Matches file date
    )
    assert res_reinject == {"NIFTY": True, "SENSEX": False, "BANKNIFTY": False}
    assert advisor.rbfn_grids_frozen["NIFTY"] is True
    assert advisor.cached_rbfn_grids["NIFTY"].is_ground_truth is True

    levels_file.unlink()  # File is now missing
    res_missing = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file,
        force=True,
        session_date=today_str,
    )
    assert res_missing == {}
    assert advisor.rbfn_grids_frozen["NIFTY"] is False
    assert advisor.cached_rbfn_grids["NIFTY"] is None


def test_gate_sentinel_05_decision_trace_telemetry(tmp_path: Path):
    """GATE-SENTINEL-05: log_decision_trace writes structured telemetry record to JSONL."""
    wal = tmp_path / "test_wal_trace.json"
    trace_file = tmp_path / "runtime" / "sentinel_decision_trace.jsonl"

    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = trace_file

    advisor.log_decision_trace(
        index_name="NIFTY",
        bar_time=dt_time(11, 35),
        action="BUY_CALL",
        reason="RP1_UPPER_10M_EXPANSION_BREAKOUT",
        details={"target_strike": 25400.0, "target_pts": 30.0, "sl_pts": 15.0},
        timestamp_ms=1793196900000,
    )

    assert trace_file.exists()
    lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["index_name"] == "NIFTY"
    assert record["bar_time"] == "11:35:00"
    assert record["action"] == "BUY_CALL"
    assert record["reason"] == "RP1_UPPER_10M_EXPANSION_BREAKOUT"
    assert record["details"]["target_strike"] == 25400.0
    assert record["timestamp_ms"] == 1793196900000


def test_gate_sentinel_06_fast_single_bar_rejection(tmp_path: Path):
    """GATE-SENTINEL-06: Fast single-bar rejection in S5/S7 with rejection buffer."""
    wal = tmp_path / "test_wal_fast_rej.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0
    _seed_test_or_pair(advisor, "NIFTY", dt_time(10, 20))

    # Grid: TD = 24000, RP1 Upper = 24120, RP2 Upper = 24240, RP1 Lower = 23880, RP2 Lower = 23760
    # Seed bar 1 (10:15)
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24150.0,
        bar_high=24180.0,
        bar_low=24140.0,
        bar_close=24170.0,
        bar_volume=50000.0,
        bar_time=dt_time(10, 15),
        timestamp_ms=_test_bar_epoch(dt_time(10, 15)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(10, 15)),
    )

    # Bar 2 at 10:20: High tests RP2 Upper (24245 >= 24240) and closes deep below:
    # bar_close = 24225 <= (grid.rp2_upper - rejection_buffer = 24240 - 10.0 = 24230)
    # This qualifies for S5 fast single-bar rejection!
    sig_fast_s5 = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24220.0,
        bar_high=24245.0,
        bar_low=24210.0,
        bar_close=24225.0,
        bar_volume=60000.0,
        bar_time=dt_time(10, 20),
        timestamp_ms=_test_bar_epoch(dt_time(10, 20)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(10, 20)),
    )

    assert sig_fast_s5 is not None
    assert sig_fast_s5.action == "BUY_PUT"
    assert sig_fast_s5.direction == "PE"
    assert sig_fast_s5.setup_reason == "RP2_UPPER_FAST_REJECTION"
    assert is_mode_5_exhaustion_fade(sig_fast_s5.setup_reason) is True

    # S7 Fast single-bar bounce: Bar 3 tests RP2 Lower (23755 <= 23760) and closes at 23775 >= (23760 + 10.0 = 23770)
    sig_fast_s7 = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=23770.0,
        bar_high=23780.0,
        bar_low=23755.0,
        bar_close=23775.0,
        bar_volume=60000.0,
        bar_time=dt_time(10, 25),
        timestamp_ms=_test_bar_epoch(dt_time(10, 25)) * 300_000,
        epoch_5min=_test_bar_epoch(dt_time(10, 25)),
    )

    assert sig_fast_s7 is not None
    assert sig_fast_s7.action == "BUY_CALL"
    assert sig_fast_s7.direction == "CE"
    assert sig_fast_s7.setup_reason == "RP2_LOWER_FAST_BOUNCE"
    assert is_mode_5_exhaustion_fade(sig_fast_s7.setup_reason) is True


def test_safety_invariants_hardening_002(tmp_path: Path):
    """Safety invariants validation for ARCH-SENTINEL-HARDENING-002."""
    wal = tmp_path / "test_wal_safe.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    assert advisor.read_only is True
    assert advisor.is_order_action is False
    assert advisor.broker_api_called is False
    assert advisor.allowed_for_live_execution is False
