"""
Unit Tests for OptionMate Sentinel Advisor Hardening 005
=========================================================
Specification: ARCH-SENTINEL-HARDENING-005
Gate: GATE-SENTINEL-15 (RETRY_OR_RECONCILIATION_UNTIL_COMPLETE)

Tests:
1. Incomplete first response at 09:45 does not permanently poison or latch INVALID.
   Maintains status as PENDING_RECONCILIATION, Mode 5 abstains fail-closed.
2. Bounded retry succeeds at subsequent check (e.g. 09:46+ or 09:50) when complete
   candles become available, transitioning status to COMPLETE and unblocking Mode 5 setups.
3. Once all indices verify exact 30-bar coverage (UPSTOX_V2_1M_EXACT_30), reconciliation
   freezes permanently (or_reconciliation_frozen = True, zero further network calls).
4. Sub-second companion arrival jitter within 1000ms does not trigger OR_SOURCE_NONCAUSAL,
   while timestamps exceeding +1000ms are properly rejected.
5. Zero API spamming: 60-second backoff throttle strictly enforced across repeated ticks.
6. Max retry limit (10 attempts) halts further polling without crashing or entering infinite loops.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
import pytest

import core.sentinel_live_stream_advisor as advisor_module
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    Synthetic5mBarBucket,
    PriorDayReferenceLevels,
)


def _india_ts(session_day: date, bar_time: dt_time = dt_time(10, 0)) -> int:
    return int(datetime.combine(session_day, bar_time, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)


def _completed_bar_clock(timestamp_ms: int) -> tuple[int, dt_time]:
    epoch_5min = timestamp_ms // 300000
    bar_time = datetime.fromtimestamp((epoch_5min + 1) * 300, tz=ZoneInfo("Asia/Kolkata")).time()
    return epoch_5min, bar_time


def _v2_or_candles(session_day: date, count: int = 30) -> list[list[object]]:
    ist = ZoneInfo("Asia/Kolkata")
    base = datetime.combine(session_day, dt_time(9, 15), tzinfo=ist)
    rows: list[list[object]] = []
    for minute in range(count):
        bar_dt = base + timedelta(minutes=minute)
        rows.append([
            bar_dt.isoformat(),
            100.0,
            101.0,
            99.0,
            100.0,
            1000,
        ])
    return rows


def _freeze_advisor_clock(monkeypatch, timestamp_ms: int):
    frozen_dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata"))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return frozen_dt.astimezone(tz)
            return frozen_dt

    monkeypatch.setattr(advisor_module, "datetime", FrozenDateTime)


def test_incomplete_first_response_at_0945_does_not_latch_invalid(tmp_path: Path, monkeypatch):
    """Test 1: Incomplete first response at 09:45 does not permanently latch INVALID.
    
    Status becomes PENDING_RECONCILIATION, not INVALID. Mode 5 continues to fail closed (abstain).
    """
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")

    # API returns only 29 candles (09:44 candle missing due to ingestion latency)
    incomplete_candles = _v2_or_candles(day, count=29)
    response_mock = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": incomplete_candles}},
    )

    with patch("requests.get", return_value=response_mock) as get_mock:
        advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "test_or_005.json"), enable_stdout=False)
        # Advance into 09:45 spot tick
        advisor._update_spot("NIFTY", 24000.0, ts_0945)

    assert get_mock.call_count == 3
    # Verify status is PENDING_RECONCILIATION, NOT INVALID
    for idx in ("NIFTY", "BANKNIFTY", "SENSEX"):
        evidence = advisor.or_evidence[idx]
        assert evidence["status"] == "PENDING_RECONCILIATION"
        assert evidence["source"] == "UPSTOX_V2_1M_RETRY"
        assert evidence["retry_count"] == 1

    # Verify reconciliation is NOT frozen
    assert advisor.or_reconciliation_frozen is False

    # Verify Mode 5 fails closed and abstains because OR is not yet COMPLETE
    or_ok, reason, details = advisor._validate_mode5_or_pair("NIFTY", ts_0945)
    assert or_ok is False
    assert "OR_BOUNDS_INVALID" in reason or "OR_COMPLETE_REQUIRED" in reason


def test_bounded_retry_succeeds_at_0950_unblocking_mode5(tmp_path: Path, monkeypatch):
    """Test 2: Bounded retry succeeds at 09:50 when complete candles become available.
    
    Transitions status to COMPLETE and unblocks Mode 5 setups.
    """
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")

    # First attempt at 09:45 returns incomplete (29 candles)
    incomplete_candles = _v2_or_candles(day, count=29)
    complete_candles = _v2_or_candles(day, count=30)

    # Use side_effect to return incomplete on first 3 calls, complete on subsequent calls
    call_count = 0
    def mock_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": incomplete_candles}})
        return SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": complete_candles}})

    with patch("requests.get", side_effect=mock_get):
        advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "test_or_retry.json"), enable_stdout=False)
        # 09:45 tick triggers first attempt
        advisor._update_spot("NIFTY", 24000.0, ts_0945)
        advisor._update_spot("SENSEX", 80000.0, ts_0945)
        advisor._update_spot("BANKNIFTY", 51000.0, ts_0945)

        assert advisor.or_reconciliation_frozen is False
        assert advisor.or_evidence["NIFTY"]["status"] == "PENDING_RECONCILIATION"

        # Advance to 09:50 (300 seconds later, well beyond the 60s throttle)
        # The 09:45-09:50 5-minute bar closes at 09:50:00 with source_ts at 09:49:59.999
        source_ts_0950 = int(datetime.combine(day, dt_time(9, 49, 59, 999000), tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
        epoch_0945 = source_ts_0950 // 300000
        bar_time_0950 = dt_time(9, 50)
        _freeze_advisor_clock(monkeypatch, source_ts_0950)

        # 5-minute bar close at 09:50
        signal = advisor._on_5m_bar_close(
            index_name="NIFTY",
            bar_open=24000.0,
            bar_high=24050.0,
            bar_low=23950.0,
            bar_close=24010.0,
            bar_volume=1000.0,
            bar_time=bar_time_0950,
            timestamp_ms=source_ts_0950,
            epoch_5min=epoch_0945,
        )

    # All indices should now be COMPLETE
    for idx in ("NIFTY", "BANKNIFTY", "SENSEX"):
        evidence = advisor.or_evidence[idx]
        assert evidence["status"] == "COMPLETE"
        assert evidence["source"] == "UPSTOX_V2_1M_EXACT_30"
        assert evidence["coverage_count"] == 30

    # Permanent freeze active
    assert advisor.or_reconciliation_frozen is True

    # Mode 5 pair validation succeeds at 09:50
    ts_0950 = _india_ts(day, dt_time(9, 50))
    or_ok, reason, details = advisor._validate_mode5_or_pair("NIFTY", ts_0950)
    assert or_ok is True
    assert reason == "MODE5_OR_VALID"


def test_permanent_freeze_once_all_indices_complete(tmp_path: Path, monkeypatch):
    """Test 3: Once all indices verify COMPLETE, reconciliation freezes permanently.
    
    Zero further network requests are dispatched for OR reconciliation.
    """
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")

    complete_candles = _v2_or_candles(day, count=30)
    response_mock = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": complete_candles}},
    )

    with patch("requests.get", return_value=response_mock) as get_mock:
        advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "test_freeze.json"), enable_stdout=False)
        advisor._update_spot("NIFTY", 24000.0, ts_0945)
        advisor._update_spot("SENSEX", 80000.0, ts_0945)
        advisor._update_spot("BANKNIFTY", 51000.0, ts_0945)

        # 3 calls made for NIFTY, BANKNIFTY, SENSEX
        assert get_mock.call_count == 3
        assert advisor.or_reconciliation_frozen is True

        # Now simulate further 5m bar closes and ticks throughout the day
        ts_0955 = _india_ts(day, dt_time(9, 55))
        _freeze_advisor_clock(monkeypatch, ts_0955)
        advisor._update_spot("NIFTY", 24020.0, ts_0955)

        epoch_0950 = ts_0950 = _india_ts(day, dt_time(9, 50))
        _, bar_time_0955 = _completed_bar_clock(ts_0950)
        advisor._on_5m_bar_close(
            index_name="NIFTY",
            bar_open=24010.0,
            bar_high=24030.0,
            bar_low=24000.0,
            bar_close=24020.0,
            bar_volume=1000.0,
            bar_time=bar_time_0955,
            timestamp_ms=ts_0955,
            epoch_5min=ts_0955 // 300000,
        )

        ts_1000 = _india_ts(day, dt_time(10, 0))
        _freeze_advisor_clock(monkeypatch, ts_1000)
        advisor._update_spot("NIFTY", 24030.0, ts_1000)

        # Call count must strictly remain 3 - zero additional network requests
        assert get_mock.call_count == 3


def test_subsecond_causal_skew_tolerance_boundary(tmp_path: Path, monkeypatch):
    """Test 4: Sub-second arrival jitter within 1000ms does not trigger OR_SOURCE_NONCAUSAL.
    
    Timestamps with arrival jitter <= 1000ms pass causal check; timestamps > 1000ms are rejected.
    """
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)

    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "test_skew.json"), enable_stdout=False)
    # Manually seed COMPLETE OR evidence
    expected_start = int(datetime.combine(day, dt_time(9, 15), tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    expected_end = int(datetime.combine(day, dt_time(9, 44), tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)

    for idx in ("NIFTY", "SENSEX"):
        advisor.or_bounds[idx] = {"high": 24000.0, "low": 23900.0}
        advisor.or_evidence[idx] = {
            "session_date": day.isoformat(),
            "status": "COMPLETE",
            "source": "UPSTOX_V2_1M_EXACT_30",
            "source_timestamp_ms": expected_end,
            "coverage_count": 30,
            "coverage_start_ms": expected_start,
            "coverage_end_ms": expected_end,
        }

    # At decision time exactly 09:45:00.000, source timestamp is 09:44:00.000 (diff is 60s, completely causal)
    ok, reason, details = advisor._validate_mode5_or_evidence("NIFTY", ts_0945)
    assert ok is True
    assert reason == "OR_COMPLETE_VERIFIED"

    # Now test artificial skew: decision time at 09:45:00.000, but source timestamp set to 09:45:00.500 (+500ms jitter)
    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = ts_0945 + 500
    advisor.or_evidence["NIFTY"]["coverage_end_ms"] = ts_0945 + 500
    ok, reason, _ = advisor._validate_mode5_or_evidence("NIFTY", ts_0945)
    # Within 1000ms tolerance, it is NOT rejected as OR_SOURCE_NONCAUSAL
    assert reason != "OR_SOURCE_NONCAUSAL"

    # Now set source timestamp to ts_0945 + 1001ms (exceeds 1000ms tolerance)
    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = ts_0945 + 1001
    ok, reason, _ = advisor._validate_mode5_or_evidence("NIFTY", ts_0945)
    assert ok is False
    assert reason == "OR_SOURCE_NONCAUSAL"

    # Negative or 0 source timestamp also rejected
    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = 0
    ok, reason, _ = advisor._validate_mode5_or_evidence("NIFTY", ts_0945)
    assert ok is False
    assert reason == "OR_SOURCE_NONCAUSAL"


def test_zero_api_spamming_rate_limited_throttle(tmp_path: Path, monkeypatch):
    """Test 5: Zero API spamming: 60-second backoff throttle strictly enforced.
    
    100 spot ticks between 09:45:01 and 09:45:30 while API returns incomplete response
    must dispatch exactly 1 round of REST calls.
    """
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")

    incomplete_candles = _v2_or_candles(day, count=28)
    response_mock = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": incomplete_candles}},
    )

    with patch("requests.get", return_value=response_mock) as get_mock:
        advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "test_throttle.json"), enable_stdout=False)

        # Fire 100 ticks within 30 seconds (09:45:01 to 09:45:30)
        for second in range(1, 31):
            tick_ts = ts_0945 + (second * 1000)
            _freeze_advisor_clock(monkeypatch, tick_ts)
            advisor._update_spot("NIFTY", 24000.0 + second, tick_ts)

        # 3 initial calls for NIFTY, BANKNIFTY, SENSEX at 09:45:01; subsequent ticks within 60s are throttled
        assert get_mock.call_count == 3


def test_max_retry_exhaustion_fails_closed(tmp_path: Path, monkeypatch):
    """Test 6: Max retry limit (10 attempts) halts further polling without infinite loops.
    
    Fails closed and abstains from trading.
    """
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")

    incomplete_candles = _v2_or_candles(day, count=25)
    response_mock = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": incomplete_candles}},
    )

    with patch("requests.get", return_value=response_mock) as get_mock:
        advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "test_exhaustion.json"), enable_stdout=False)

        # Simulate 12 retry intervals spaced 65 seconds apart
        for cycle in range(12):
            cycle_ts = ts_0945 + (cycle * 65 * 1000)
            _freeze_advisor_clock(monkeypatch, cycle_ts)
            advisor._seed_or_bounds_from_api_if_late_boot(session_day=day, current_time_ms=cycle_ts)

        # Max 10 attempts per index (3 indices * 10 = 30 calls)
        assert get_mock.call_count == 30
        for idx in ("NIFTY", "BANKNIFTY", "SENSEX"):
            assert advisor.or_reconcile_retry_count[idx] == 10
            assert advisor.or_evidence[idx]["status"] == "PENDING_RECONCILIATION"

        # Advancing further in time does NOT trigger more calls
        cycle_ts = ts_0945 + (15 * 65 * 1000)
        _freeze_advisor_clock(monkeypatch, cycle_ts)
        advisor._seed_or_bounds_from_api_if_late_boot(session_day=day, current_time_ms=cycle_ts)
        assert get_mock.call_count == 30
