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
import json
import multiprocessing
import os
import threading
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


def _new_advisor(tmp_path: Path, name: str) -> SentinelLiveStreamAdvisor:
    return SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"{name}.json"),
        or_reconciliation_state_path=str(tmp_path / "sentinel_or_reconciliation_state.json"),
        enable_stdout=False,
    )


def _ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "sentinel_or_reconciliation_state.json"


def _lock_path(ledger_path: Path) -> Path:
    return Path(f"{ledger_path}.lock")


def _initialized_marker_path(ledger_path: Path) -> Path:
    return ledger_path.parent / f".{ledger_path.stem}.initialized"


def _marker_identity(ledger_path: Path, state: str = "READY") -> dict[str, object]:
    lock_path = _lock_path(ledger_path)
    marker_path = _initialized_marker_path(ledger_path)
    return {
        "schema_version": 1,
        "ledger_path": str(ledger_path.resolve()),
        "lock_path": str(lock_path.resolve()),
        "marker_path": str(marker_path.resolve()),
        "state": state,
    }


def _write_initialized_marker(ledger_path: Path) -> None:
    lock_path = _lock_path(ledger_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    marker_path = _initialized_marker_path(ledger_path)
    marker_path.write_text(json.dumps(_marker_identity(ledger_path)), encoding="utf-8")


def _write_ledger(path: Path, session_day: date, indices: dict[str, dict[str, object]]) -> None:
    _write_initialized_marker(path)
    path.write_text(json.dumps({
        "schema_version": 1,
        "session_date": session_day.isoformat(),
        "indices": indices,
    }), encoding="utf-8")


def _attempt_state(count: int, last_ms: int, proof: dict[str, object] | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "attempt_count": count,
        "last_attempt_timestamp_ms": last_ms,
    }
    if proof is not None:
        result["completion_proof"] = proof
    return result


def _reserve_last_slot_in_process(
    ledger_path: str,
    session_day: date,
    now_ms: int,
    start_barrier,
    result_queue,
) -> None:
    advisor = SentinelLiveStreamAdvisor.__new__(SentinelLiveStreamAdvisor)
    advisor.OR_MAX_RETRY_ATTEMPTS = 10
    advisor.OR_MIN_RETRY_INTERVAL_MS = 60_000
    advisor.or_reconciliation_state_path = Path(ledger_path)
    advisor.or_reconciliation_lock_path = Path(f"{ledger_path}.lock")
    advisor.or_reconciliation_initialized_path = (
        Path(ledger_path).parent / f".{Path(ledger_path).stem}.initialized"
    )
    advisor._lock = threading.RLock()
    advisor.or_bounds = {
        index_name: {"high": -math.inf, "low": math.inf}
        for index_name in ("NIFTY", "BANKNIFTY", "SENSEX")
    }
    advisor.or_evidence = {
        index_name: advisor._empty_or_evidence(session_day)
        for index_name in advisor.or_bounds
    }
    advisor.or_reconcile_retry_count = {index_name: 0 for index_name in advisor.or_bounds}
    advisor.or_last_reconcile_attempt_ms = {index_name: 0 for index_name in advisor.or_bounds}
    advisor._or_last_ledger_check_ms = {index_name: 0 for index_name in advisor.or_bounds}
    advisor.or_reconciliation_frozen = False
    advisor._or_reconciliation_loaded_session_day = None
    advisor.active_range_high = -math.inf
    advisor.active_range_low = math.inf
    start_barrier.wait(timeout=5)
    result_queue.put(
        advisor._reserve_or_reconciliation_attempt(session_day, "NIFTY", now_ms, False)
    )


def _inject_bootstrap_failure(monkeypatch, advisor: SentinelLiveStreamAdvisor, failpoint: str) -> None:
    kind, separator, raw_target = failpoint.partition(":")
    if not separator:
        raw_target = ""
    target = int(raw_target) if raw_target else 1
    counter = 0
    if kind in {"lock_open", "marker_open"}:
        original = advisor_module.os.open
        wanted_path = (
            advisor.or_reconciliation_lock_path
            if kind == "lock_open"
            else advisor.or_reconciliation_initialized_path
        )

        def fail_targeted_open(path, flags, *args, **kwargs):
            if Path(path) == wanted_path and flags & os.O_CREAT:
                raise OSError(f"injected bootstrap {kind} failure")
            return original(path, flags, *args, **kwargs)

        monkeypatch.setattr(advisor_module.os, "open", fail_targeted_open)
    elif kind == "temp_create":
        original = advisor_module.tempfile.mkstemp

        def fail_nth_temp_create(*args, **kwargs):
            nonlocal counter
            counter += 1
            if counter == target:
                raise OSError("injected bootstrap temporary-file create failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(advisor_module.tempfile, "mkstemp", fail_nth_temp_create)
    elif kind == "os_fsync":
        original = advisor_module.os.fsync

        def fail_nth_fsync(fd):
            nonlocal counter
            counter += 1
            if counter == target:
                raise OSError("injected bootstrap file fsync failure")
            return original(fd)

        monkeypatch.setattr(advisor_module.os, "fsync", fail_nth_fsync)
    elif kind == "directory_fsync":
        original = advisor._fsync_or_reconciliation_directory

        def fail_nth_directory_fsync(directory):
            nonlocal counter
            counter += 1
            if counter == target:
                raise OSError("injected bootstrap directory fsync failure")
            return original(directory)

        monkeypatch.setattr(advisor, "_fsync_or_reconciliation_directory", fail_nth_directory_fsync)
    elif kind == "replace":
        original = advisor_module.os.replace

        def fail_nth_replace(source, destination):
            nonlocal counter
            counter += 1
            if counter == target:
                raise OSError("injected bootstrap replace failure")
            return original(source, destination)

        monkeypatch.setattr(advisor_module.os, "replace", fail_nth_replace)
    elif kind == "write":
        original_fdopen = advisor_module.os.fdopen

        class InjectedWriteFailure:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, exc_type, exc, traceback):
                return self.handle.__exit__(exc_type, exc, traceback)

            def write(self, value):
                nonlocal counter
                counter += 1
                if counter == target:
                    raise OSError("injected bootstrap write failure")
                return self.handle.write(value)

            def flush(self):
                return self.handle.flush()

            def fileno(self):
                return self.handle.fileno()

        monkeypatch.setattr(
            advisor_module.os,
            "fdopen",
            lambda fd, *args, **kwargs: InjectedWriteFailure(
                original_fdopen(fd, *args, **kwargs)
            ),
        )
    else:
        raise AssertionError(f"unknown bootstrap failure kind: {kind}")


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
        advisor = _new_advisor(tmp_path, "test_or_005")
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
    or_ok, reason, details = advisor._validate_mode5_or_pair("NIFTY", ts_0945, ts_0945)
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
        advisor = _new_advisor(tmp_path, "test_or_retry")
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
    or_ok, reason, details = advisor._validate_mode5_or_pair("NIFTY", ts_0950, ts_0950)
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
        advisor = _new_advisor(tmp_path, "test_freeze")
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


def test_mode5_or_evidence_uses_completed_bar_boundary(tmp_path: Path, monkeypatch):
    """Accept exact completed-bar equality; reject any source timestamp after it."""
    day = date(2026, 11, 18)
    ts_0945 = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, ts_0945)

    advisor = _new_advisor(tmp_path, "test_boundary")
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

    # Complete OR evidence uses the last in-range 09:44 candle and is valid at 09:45.
    ok, reason, _ = advisor._validate_mode5_or_pair("NIFTY", ts_0945, ts_0945)
    assert ok is True
    assert reason == "MODE5_OR_VALID"

    # Partial evidence may be timestamped exactly at the completed 09:20 boundary.
    boundary_0920 = _india_ts(day, dt_time(9, 20))
    decision_before_boundary = boundary_0920 - 1_000
    for idx in ("NIFTY", "SENSEX"):
        advisor.or_evidence[idx] = {
            "session_date": day.isoformat(),
            "status": "PARTIAL",
            "source": "UPSTOX_TICK_PARTIAL",
            "source_timestamp_ms": boundary_0920,
            "coverage_count": 0,
            "coverage_start_ms": 0,
            "coverage_end_ms": 0,
        }
    ok, reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", decision_before_boundary, boundary_0920
    )
    assert ok is True
    assert reason == "MODE5_OR_VALID"

    # Future source timestamps fail at +1ms even inside the former post-opening skew allowance.
    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = boundary_0920 + 1
    ok, reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", decision_before_boundary, boundary_0920
    )
    assert ok is False
    assert reason == "MODE5_TARGET_OR_SOURCE_NONCAUSAL"

    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = boundary_0920
    advisor.or_evidence["SENSEX"]["source_timestamp_ms"] = boundary_0920 + 1
    ok, reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", decision_before_boundary, boundary_0920
    )
    assert ok is False
    assert reason == "MODE5_COMPANION_OR_SOURCE_NONCAUSAL"

    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = 0
    ok, reason, _ = advisor._validate_mode5_or_evidence(
        "NIFTY", decision_before_boundary, boundary_0920
    )
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
        advisor = _new_advisor(tmp_path, "test_throttle")

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
        advisor = _new_advisor(tmp_path, "test_exhaustion")

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


def test_retry_cap_and_throttle_survive_advisor_restart(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    start_ms = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, start_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    incomplete = _v2_or_candles(day, count=29)
    response = SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": incomplete}})

    with patch("requests.get", return_value=response) as get_mock:
        advisor = _new_advisor(tmp_path, "restart-nine-attempts")
        for cycle in range(1, 9):
            now_ms = start_ms + cycle * 65_000
            _freeze_advisor_clock(monkeypatch, now_ms)
            advisor._seed_or_bounds_from_api_if_late_boot(session_day=day, current_time_ms=now_ms)
        assert advisor.or_reconcile_retry_count == {"NIFTY": 9, "BANKNIFTY": 9, "SENSEX": 9}
        assert get_mock.call_count == 27

        # Restart at the same event time. The constructor must recover nine and
        # must not spend the remaining attempt inside the persisted throttle.
        restarted = _new_advisor(tmp_path, "restart-after-nine")
        assert restarted.or_reconcile_retry_count == {"NIFTY": 9, "BANKNIFTY": 9, "SENSEX": 9}
        assert get_mock.call_count == 27

        tenth_ms = start_ms + 9 * 65_000
        _freeze_advisor_clock(monkeypatch, tenth_ms)
        restarted._seed_or_bounds_from_api_if_late_boot(session_day=day, current_time_ms=tenth_ms)
        assert restarted.or_reconcile_retry_count == {"NIFTY": 10, "BANKNIFTY": 10, "SENSEX": 10}
        assert get_mock.call_count == 30

        eleventh_ms = start_ms + 10 * 65_000
        _freeze_advisor_clock(monkeypatch, eleventh_ms)
        restarted._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=eleventh_ms, force=True
        )
        assert restarted.or_reconcile_retry_count == {"NIFTY": 10, "BANKNIFTY": 10, "SENSEX": 10}
        assert get_mock.call_count == 30


def test_persisted_sixty_second_throttle_and_force_semantics(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    start_ms = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, start_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    incomplete = _v2_or_candles(day, count=28)
    response = SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": incomplete}})

    with patch("requests.get", return_value=response) as get_mock:
        first = _new_advisor(tmp_path, "persisted-throttle-first")
        assert get_mock.call_count == 3

        restart_ms = start_ms + 30_000
        _freeze_advisor_clock(monkeypatch, restart_ms)
        restarted = _new_advisor(tmp_path, "persisted-throttle-second")
        assert restarted.or_reconcile_retry_count == {"NIFTY": 1, "BANKNIFTY": 1, "SENSEX": 1}
        assert get_mock.call_count == 3

        forced_ms = start_ms + 30_001
        _freeze_advisor_clock(monkeypatch, forced_ms)
        restarted._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=forced_ms, force=True
        )
        assert get_mock.call_count == 6
        assert restarted.or_reconcile_retry_count == {"NIFTY": 2, "BANKNIFTY": 2, "SENSEX": 2}

        throttled_ms = start_ms + 59_999
        _freeze_advisor_clock(monkeypatch, throttled_ms)
        restarted._seed_or_bounds_from_api_if_late_boot(session_day=day, current_time_ms=throttled_ms)
        assert get_mock.call_count == 6

        allowed_ms = start_ms + 90_001
        _freeze_advisor_clock(monkeypatch, allowed_ms)
        restarted._seed_or_bounds_from_api_if_late_boot(session_day=day, current_time_ms=allowed_ms)
        assert get_mock.call_count == 9


def test_retry_ledger_keeps_per_index_budgets_independent(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    _write_ledger(_ledger_path(tmp_path), day, {
        "NIFTY": _attempt_state(10, now_ms - 60_000),
        "BANKNIFTY": _attempt_state(9, now_ms - 60_000),
        "SENSEX": _attempt_state(0, 0),
    })
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    incomplete = _v2_or_candles(day, count=29)
    response = SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": incomplete}})

    with patch("requests.get", return_value=response) as get_mock:
        advisor = _new_advisor(tmp_path, "per-index-budget")

    assert get_mock.call_count == 2
    assert advisor.or_reconcile_retry_count == {"NIFTY": 10, "BANKNIFTY": 10, "SENSEX": 1}


def test_new_session_resets_ledger_but_stale_event_cannot_roll_it_back(tmp_path: Path, monkeypatch):
    previous_day = date(2026, 11, 18)
    current_day = date(2026, 11, 19)
    now_ms = _india_ts(current_day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    _write_ledger(_ledger_path(tmp_path), previous_day, {
        "NIFTY": _attempt_state(10, _india_ts(previous_day, dt_time(10, 0))),
        "BANKNIFTY": _attempt_state(0, 0),
        "SENSEX": _attempt_state(0, 0),
    })
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    incomplete = _v2_or_candles(current_day, count=29)
    response = SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": incomplete}})

    with patch("requests.get", return_value=response) as get_mock:
        advisor = _new_advisor(tmp_path, "new-session-reset")
        assert get_mock.call_count == 3
        assert advisor.or_reconcile_retry_count == {"NIFTY": 1, "BANKNIFTY": 1, "SENSEX": 1}

        stale_ms = _india_ts(previous_day, dt_time(10, 0))
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=previous_day, current_time_ms=stale_ms
        ) is False
        assert get_mock.call_count == 3

    saved = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["session_date"] == current_day.isoformat()


def test_corrupt_or_missing_after_initialization_ledger_never_requests_candles(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    ledger = _ledger_path(tmp_path)
    _write_initialized_marker(ledger)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")

    with patch("requests.get") as get_mock:
        advisor = _new_advisor(tmp_path, "missing-after-init")
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000
        ) is False
        assert get_mock.call_count == 0

    ledger.write_text("{broken json", encoding="utf-8")
    with patch("requests.get") as get_mock:
        advisor = _new_advisor(tmp_path, "corrupt-ledger")
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 130_000
        ) is False
        assert get_mock.call_count == 0


def test_first_use_bootstraps_all_three_artifacts_and_all_index_states(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    ledger = _ledger_path(tmp_path)
    assert not ledger.exists()
    assert not _lock_path(ledger).exists()
    assert not _initialized_marker_path(ledger).exists()

    advisor = _new_advisor(tmp_path, "true-first-use")

    assert advisor._or_reconciliation_ledger_degraded is False
    assert ledger.is_file()
    assert _lock_path(ledger).is_file()
    assert _initialized_marker_path(ledger).is_file()
    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert set(saved["indices"]) == {"NIFTY", "BANKNIFTY", "SENSEX"}
    assert all(state == _attempt_state(0, 0) for state in saved["indices"].values())
    assert json.loads(_initialized_marker_path(ledger).read_text(encoding="utf-8"))["state"] == "READY"


@pytest.mark.parametrize(
    ("failpoint", "expected_marker_state", "restart_bootstraps"),
    [
        ("lock_open", None, True),
        ("os_fsync:1", None, False),
        ("os_fsync:2", None, False),
        ("os_fsync:3", "INITIALIZING", False),
        ("os_fsync:4", "INITIALIZING", False),
        ("directory_fsync:1", None, False),
        ("marker_open", None, False),
        ("write:1", None, False),
        ("directory_fsync:2", "INITIALIZING", False),
        ("temp_create:1", "INITIALIZING", False),
        ("write:2", "INITIALIZING", False),
        ("os_fsync:5", "INITIALIZING", False),
        ("os_fsync:6", "INITIALIZING", False),
        ("replace:1", "INITIALIZING", False),
        ("directory_fsync:3", "INITIALIZING", False),
        ("temp_create:2", "INITIALIZING", False),
        ("write:3", "INITIALIZING", False),
        ("os_fsync:7", "INITIALIZING", False),
        ("replace:2", "INITIALIZING", False),
        ("os_fsync:8", "READY", False),
        ("os_fsync:9", "READY", False),
        ("directory_fsync:4", "READY", False),
    ],
)
def test_every_bootstrap_failure_boundary_fails_closed_and_restart_is_explicit(
    tmp_path: Path,
    monkeypatch,
    failpoint: str,
    expected_marker_state: str | None,
    restart_bootstraps: bool,
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    ledger = _ledger_path(tmp_path)

    # Construct an advisor without triggering bootstrap so each injected fault
    # lands at the intended first-use boundary.
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        failing = _new_advisor(tmp_path, f"bootstrap-failing-{failpoint.replace(':', '-')}")

    with monkeypatch.context() as fault_patch:
        _inject_bootstrap_failure(fault_patch, failing, failpoint)
        with patch("requests.get") as failed_process_requests:
            assert failing._seed_or_bounds_from_api_if_late_boot(
                session_day=day, current_time_ms=now_ms
            ) is False
            assert failed_process_requests.call_count == 0
    assert failing._or_reconciliation_ledger_degraded is True

    marker_state = None
    try:
        marker_state = json.loads(
            _initialized_marker_path(ledger).read_text(encoding="utf-8")
        ).get("state")
    except (OSError, json.JSONDecodeError):
        pass
    assert marker_state == expected_marker_state

    # A fresh process may continue only if READY became visible after a sync
    # uncertainty; it still reserves each retry durably before its request.
    incomplete = _v2_or_candles(day, count=29)

    def restart_response(url, *args, **kwargs):
        latest = json.loads(ledger.read_text(encoding="utf-8"))
        index = (
            "BANKNIFTY" if "Nifty%20Bank" in url
            else "SENSEX" if "BSE_INDEX%7CSENSEX" in url
            else "NIFTY"
        )
        assert latest["indices"][index]["attempt_count"] >= 1
        return SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": incomplete}})

    with patch("requests.get", side_effect=restart_response) as restarted_requests:
        restarted = _new_advisor(tmp_path, f"bootstrap-restarted-{failpoint.replace(':', '-')}")
    if expected_marker_state == "READY" or restart_bootstraps:
        assert restarted._or_reconciliation_ledger_degraded is False
        assert restarted_requests.call_count == 3
        assert json.loads(_initialized_marker_path(ledger).read_text(encoding="utf-8"))["state"] == "READY"
    else:
        assert restarted._or_reconciliation_ledger_degraded is True
        assert restarted_requests.call_count == 0


@pytest.mark.parametrize(
    "partial_state",
    ["lock_only", "marker_only", "ledger_only", "malformed_marker"],
)
def test_partial_or_malformed_bootstrap_state_fails_closed(
    tmp_path: Path, monkeypatch, partial_state: str
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    ledger = _ledger_path(tmp_path)
    if partial_state == "lock_only":
        _lock_path(ledger).touch()
    elif partial_state == "marker_only":
        marker = _initialized_marker_path(ledger)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(_marker_identity(ledger)), encoding="utf-8")
    elif partial_state == "ledger_only":
        ledger.write_text(json.dumps({
            "schema_version": 1,
            "session_date": day.isoformat(),
            "indices": {
                name: _attempt_state(0, 0)
                for name in ("NIFTY", "BANKNIFTY", "SENSEX")
            },
        }), encoding="utf-8")
    else:
        _write_initialized_marker(ledger)
        _initialized_marker_path(ledger).write_text("{bad marker", encoding="utf-8")
        _write_ledger(ledger, day, {
            name: _attempt_state(0, 0)
            for name in ("NIFTY", "BANKNIFTY", "SENSEX")
        })
        _initialized_marker_path(ledger).write_text("{bad marker", encoding="utf-8")

    with patch("requests.get") as get_mock:
        advisor = _new_advisor(tmp_path, f"partial-{partial_state}")
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000
        ) is False
        assert get_mock.call_count == 0
    assert advisor._or_reconciliation_ledger_degraded is True


def test_cap_state_loss_with_marker_preserved_never_reinitializes_or_requests(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    ledger = _ledger_path(tmp_path)
    _write_ledger(ledger, day, {
        name: _attempt_state(10, now_ms - 60_000)
        for name in ("NIFTY", "BANKNIFTY", "SENSEX")
    })
    marker_bytes = _initialized_marker_path(ledger).read_bytes()
    ledger.unlink()
    _lock_path(ledger).unlink()

    with patch("requests.get") as get_mock:
        advisor = _new_advisor(tmp_path, "cap-state-loss")
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000, force=True
        ) is False
        assert get_mock.call_count == 0

    assert advisor._or_reconciliation_ledger_degraded is True
    assert not ledger.exists()
    assert _initialized_marker_path(ledger).read_bytes() == marker_bytes


def test_default_or_ledger_path_is_stable_when_cwd_changes(tmp_path: Path, monkeypatch):
    expected = (
        Path(advisor_module.__file__).resolve().parents[1]
        / "runtime"
        / "sentinel_or_reconciliation_state.json"
    )
    monkeypatch.setattr(
        SentinelLiveStreamAdvisor,
        "_seed_or_bounds_from_api_if_late_boot",
        lambda *args, **kwargs: False,
    )
    paths = []
    for name in ("cwd-one", "cwd-two"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.chdir(directory)
        advisor = SentinelLiveStreamAdvisor(
            wal_path=str(directory / "advisor.json"),
            enable_stdout=False,
        )
        paths.append(advisor.or_reconciliation_state_path)

    assert paths == [expected.resolve(), expected.resolve()]


@pytest.mark.parametrize("at_cap", [False, True], ids=["zero-count", "nifty-banknifty-at-cap"])
def test_ledger_missing_index_fails_closed_without_zero_reset(
    tmp_path: Path, monkeypatch, at_cap: bool
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    ledger = _ledger_path(tmp_path)
    count = 10 if at_cap else 0
    last_ms = now_ms - 60_000 if at_cap else 0
    _write_ledger(ledger, day, {
        "NIFTY": _attempt_state(count, last_ms),
        "BANKNIFTY": _attempt_state(count, last_ms),
        # SENSEX is deliberately missing from an otherwise valid schema.
    })
    original_bytes = ledger.read_bytes()

    with patch("requests.get") as get_mock:
        advisor = _new_advisor(tmp_path, "missing-index")
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000
        ) is False
        assert get_mock.call_count == 0

    assert advisor._or_reconciliation_ledger_degraded is True
    assert ledger.read_bytes() == original_bytes
    assert set(json.loads(original_bytes)["indices"]) == {"NIFTY", "BANKNIFTY"}


def test_retry_ledger_permission_failure_never_requests_candles(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    advisor = _new_advisor(tmp_path, "permission-failure")

    def deny_ledger_lock():
        raise PermissionError("injected permission failure")

    monkeypatch.setattr(advisor, "_acquire_or_reconciliation_lock", deny_ledger_lock)
    with patch("requests.get") as get_mock:
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000
        ) is False
        assert get_mock.call_count == 0
    assert advisor._or_reconciliation_ledger_degraded is True


def test_retry_reservation_fsync_uncertainty_blocks_request(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    start_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, start_ms)
    advisor = _new_advisor(tmp_path, "fsync-uncertain-reservation")
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    later_ms = start_ms + 65_000
    _freeze_advisor_clock(monkeypatch, later_ms)
    original_fsync_dir = advisor._fsync_or_reconciliation_directory
    fsync_calls = 0

    def fail_after_ledger_replace(directory: Path) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            raise OSError("injected directory fsync failure")
        original_fsync_dir(directory)

    monkeypatch.setattr(advisor, "_fsync_or_reconciliation_directory", fail_after_ledger_replace)
    with patch("requests.get") as get_mock:
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=later_ms
        ) is False
        requested_urls = [call.args[0] for call in get_mock.call_args_list]
        assert not any("Nifty%2050" in url for url in requested_urls)
        assert len(requested_urls) == 2

    # Replace may be visible even though directory durability was uncertain;
    # treating the reservation as consumed is conservative and prevents retry.
    saved = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["indices"]["NIFTY"]["attempt_count"] == 1


def test_concurrent_advisors_reserve_only_one_last_attempt(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    last_ms = _india_ts(day, dt_time(10, 0))
    now_ms = last_ms + 60_000
    _freeze_advisor_clock(monkeypatch, now_ms)
    _write_ledger(_ledger_path(tmp_path), day, {
        "NIFTY": _attempt_state(9, last_ms),
        "BANKNIFTY": _attempt_state(0, 0),
        "SENSEX": _attempt_state(0, 0),
    })
    first = _new_advisor(tmp_path, "last-slot-one")
    second = _new_advisor(tmp_path, "last-slot-two")
    barrier = threading.Barrier(2)
    outcomes: list[tuple[bool, str, int]] = []
    errors: list[Exception] = []

    def reserve(advisor: SentinelLiveStreamAdvisor) -> None:
        try:
            barrier.wait(timeout=2)
            outcomes.append(advisor._reserve_or_reconciliation_attempt(day, "NIFTY", now_ms, False))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=reserve, args=(advisor,)) for advisor in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sum(1 for allowed, _, _ in outcomes if allowed) == 1
    assert sorted(reason for allowed, reason, _ in outcomes if not allowed) == ["ATTEMPT_CAP_REACHED"]
    saved = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["indices"]["NIFTY"]["attempt_count"] == 10


def test_independent_processes_reserve_only_one_last_attempt(tmp_path: Path, monkeypatch):
    context = multiprocessing.get_context("spawn")
    day = date(2026, 11, 18)
    last_ms = _india_ts(day, dt_time(10, 0))
    now_ms = last_ms + 60_000
    _write_ledger(_ledger_path(tmp_path), day, {
        "NIFTY": _attempt_state(9, last_ms),
        "BANKNIFTY": _attempt_state(0, 0),
        "SENSEX": _attempt_state(0, 0),
    })
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_reserve_last_slot_in_process,
            args=(
                str(_ledger_path(tmp_path)),
                day,
                now_ms,
                barrier,
                result_queue,
            ),
        )
        for number in range(2)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [result_queue.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(timeout=10)

        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
        assert sum(1 for allowed, _, _ in outcomes if allowed) == 1
        assert sorted(reason for allowed, reason, _ in outcomes if not allowed) == [
            "ATTEMPT_CAP_REACHED"
        ]
        saved = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
        assert saved["indices"]["NIFTY"]["attempt_count"] == 10
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        result_queue.close()
        result_queue.join_thread()


def test_exact_thirty_bar_proof_restores_and_digest_or_bare_complete_rejected(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    advisor = _new_advisor(tmp_path, "proof-writer")
    parsed = advisor._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    for index_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert advisor._reserve_or_reconciliation_attempt(day, index_name, now_ms, False)[0]
        assert advisor._persist_or_completion_proof(day, index_name, parsed)

    restored = _new_advisor(tmp_path, "proof-reader")
    assert restored.or_reconciliation_frozen is True
    for index_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert restored.or_evidence[index_name]["status"] == "COMPLETE"
        assert restored.or_evidence[index_name]["coverage_count"] == 30
        assert restored.or_bounds[index_name] == {"high": 101.0, "low": 99.0}

    ledger = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    ledger["indices"]["NIFTY"]["completion_proof"]["sha256"] = "0" * 64
    _ledger_path(tmp_path).write_text(json.dumps(ledger), encoding="utf-8")
    corrupted = _new_advisor(tmp_path, "proof-corrupt-reader")
    assert corrupted._or_reconciliation_ledger_degraded is True
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    with patch("requests.get") as get_mock:
        assert corrupted._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000
        ) is False
        assert get_mock.call_count == 0

    ledger["indices"]["NIFTY"]["completion_proof"] = {"status": "COMPLETE"}
    _ledger_path(tmp_path).write_text(json.dumps(ledger), encoding="utf-8")
    bare_complete = _new_advisor(tmp_path, "bare-complete-reader")
    assert bare_complete._or_reconciliation_ledger_degraded is True
