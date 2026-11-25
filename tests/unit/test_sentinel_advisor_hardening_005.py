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
import time as wall_clock
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


def _wait_for_queue_tasks_bounded(task_queue, timeout: float = 3.0) -> None:
    deadline = wall_clock.monotonic() + timeout
    while task_queue.unfinished_tasks:
        if wall_clock.monotonic() >= deadline:
            raise AssertionError(f"queue did not drain within {timeout}s")
        wall_clock.sleep(0.01)


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
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: timestamp_ms / 1000.0)


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


def _write_valid_proof_ledger(
    tmp_path: Path, monkeypatch, session_day: date, available_at_ms: int
) -> tuple[Path, SentinelLiveStreamAdvisor]:
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        writer = _new_advisor(tmp_path, "integrity-proof-writer")
    parsed = writer._parse_complete_v2_or_candles(
        _v2_or_candles(session_day), session_day
    )
    assert parsed is not None
    reservation_ms = available_at_ms - 60_000
    with monkeypatch.context() as clock_patch:
        clock_patch.setattr(advisor_module, "_wall_clock_seconds", lambda: reservation_ms / 1000.0)
        for index_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
            assert writer._reserve_or_reconciliation_attempt(
                session_day, index_name, reservation_ms, False
            )[0]
            assert writer._persist_or_completion_proof(
                session_day, index_name, parsed, available_at_ms=available_at_ms
            )
    return _ledger_path(tmp_path), writer


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
    advisor._trusted_or_proofs = {}
    advisor._provider_verified_or_proofs = {}
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
    response_receipt_ms = [ts_0945]
    monkeypatch.setattr(
        advisor_module,
        "_wall_clock_seconds",
        lambda: response_receipt_ms[0] / 1000.0,
    )
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
        decision_available_0950 = (epoch_0945 + 1) * 300_000 + 1
        _freeze_advisor_clock(monkeypatch, decision_available_0950)
        response_receipt_ms[0] = decision_available_0950

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
            decision_available_at_ms=decision_available_0950,
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
    or_ok, reason, details = advisor._validate_mode5_or_pair(
        "NIFTY", ts_0950 + 2, ts_0950, ts_0950 + 2
    )
    assert or_ok is True
    assert reason == "MODE5_TARGET_OR_VALID:OR_COMPLETE_VERIFIED"


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

        # Process the valid 09:50-09:55 bucket. Bar receipt is one millisecond
        # after the boundary and evaluation follows one millisecond later.
        ts_0950 = _india_ts(day, dt_time(9, 50))
        ts_0955 = ts_0950 + 300_000
        decision_available_0955 = ts_0955 + 1
        _freeze_advisor_clock(monkeypatch, decision_available_0955 + 1)
        advisor._update_spot("NIFTY", 24020.0, ts_0955)

        epoch_0950, bar_time_0955 = _completed_bar_clock(ts_0950)
        advisor._on_5m_bar_close(
            index_name="NIFTY",
            bar_open=24010.0,
            bar_high=24030.0,
            bar_low=24000.0,
            bar_close=24020.0,
            bar_volume=1000.0,
            bar_time=bar_time_0955,
            timestamp_ms=ts_0950,
            epoch_5min=epoch_0950,
            decision_available_at_ms=decision_available_0955,
        )

        assert advisor._last_completed_5m_epoch["NIFTY"] == epoch_0950
        assert advisor.bars_5m_history["NIFTY"][-1]["timestamp_ms"] == ts_0950
        assert advisor._mode5_last_eval_rejection.get("NIFTY") is None
        assert get_mock.call_count == 3

        ts_1000 = _india_ts(day, dt_time(10, 0))
        _freeze_advisor_clock(monkeypatch, ts_1000)
        advisor._update_spot("NIFTY", 24030.0, ts_1000)

        # Call count must strictly remain 3 - zero additional network requests
        assert get_mock.call_count == 3


def test_mode5_or_evidence_uses_completed_bar_boundary(tmp_path: Path, monkeypatch):
    """Preserve event-boundary rules while requiring strict receipt-time precedence."""
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
            "available_at_ms": ts_0945 - 1,
            "coverage_count": 30,
            "coverage_start_ms": expected_start,
            "coverage_end_ms": expected_end,
        }

    # Complete OR evidence uses the last in-range 09:44 candle and is valid at 09:45.
    ok, reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", ts_0945, ts_0945, ts_0945
    )
    assert ok is True
    assert reason == "MODE5_TARGET_OR_VALID:OR_COMPLETE_VERIFIED"

    ambiguous, ambiguous_reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", ts_0945, ts_0945, ts_0945 - 1
    )
    assert ambiguous is False
    assert ambiguous_reason == "MODE5_TARGET_OR_AVAILABILITY_AMBIGUOUS"

    # A tick exactly on the 09:20 boundary belongs to the next bucket and
    # cannot support a decision at that same boundary.
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
    assert ok is False
    assert reason == "MODE5_TARGET_OR_SOURCE_NONCAUSAL"

    # Future source timestamps fail at +1ms even inside the former post-opening skew allowance.
    advisor.or_evidence["NIFTY"]["source_timestamp_ms"] = boundary_0920 + 1
    ok, reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", decision_before_boundary, boundary_0920
    )
    assert ok is False
    assert reason == "MODE5_TARGET_OR_SOURCE_NONCAUSAL"

    advisor.or_evidence["NIFTY"].update({
        "source_timestamp_ms": decision_before_boundary - 1,
        "available_at_ms": decision_before_boundary - 1,
    })
    advisor.or_evidence["SENSEX"]["available_at_ms"] = decision_before_boundary - 1
    advisor.or_evidence["SENSEX"]["source_timestamp_ms"] = boundary_0920 + 1
    ok, reason, details = advisor._validate_mode5_or_pair(
        "NIFTY", decision_before_boundary, boundary_0920, decision_before_boundary
    )
    assert ok is True
    assert reason == "MODE5_TARGET_OR_VALID:OR_PARTIAL_CAUSAL"
    assert details["companion_validation"] == "OR_SOURCE_NONCAUSAL"

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
    assert all(
        state == {**_attempt_state(0, 0), "request_id": None}
        for state in saved["indices"].values()
    )
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
    advisor = _new_advisor(tmp_path, "permission-failure")
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    denied_client = SimpleNamespace(get=Mock())
    advisor._http_client = denied_client

    def deny_ledger_lock():
        raise PermissionError("injected permission failure")

    monkeypatch.setattr(advisor, "_acquire_or_reconciliation_lock", deny_ledger_lock)
    with patch("requests.get") as get_mock:
        _freeze_advisor_clock(monkeypatch, now_ms + 65_000)
        assert advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day, current_time_ms=now_ms + 65_000
        ) is False
        assert get_mock.call_count == 0
        denied_client.get.assert_not_called()
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
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, "proof-writer")
    parsed = advisor._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    for index_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert advisor._reserve_or_reconciliation_attempt(day, index_name, now_ms, False)[0]
        assert advisor._persist_or_completion_proof(
            day, index_name, parsed, available_at_ms=now_ms
        )

    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        restored = _new_advisor(tmp_path, "proof-reader")
    restored._read_or_ledger_snapshot(day)
    assert restored.or_reconciliation_frozen is True
    for index_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert restored.or_evidence[index_name]["status"] == "COMPLETE"
        assert restored.or_evidence[index_name]["coverage_count"] == 30
        assert restored.or_bounds[index_name] == {"high": 101.0, "low": 99.0}
        assert index_name not in restored._provider_verified_or_proofs
    stored_proof = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))[
        "indices"]["NIFTY"]["completion_proof"]
    assert stored_proof["metadata_sha256"] == advisor._or_completion_metadata_digest(
        stored_proof
    )
    stored_index_state = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))["indices"]["NIFTY"]
    assert stored_index_state["request_id"] == stored_proof["request_id"]

    ledger_path = _ledger_path(tmp_path)
    valid_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    corrupt_ledger = json.loads(json.dumps(valid_ledger))
    corrupt_ledger["indices"]["NIFTY"]["completion_proof"]["sha256"] = "0" * 64
    ledger_path.write_text(json.dumps(corrupt_ledger), encoding="utf-8")
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        corrupt_reader = _new_advisor(tmp_path, "corrupt-proof-reader")
    with pytest.raises(ValueError, match="digest mismatch"):
        corrupt_reader._read_or_ledger_snapshot(day)
    assert corrupt_reader.or_evidence["NIFTY"]["status"] != "COMPLETE"
    assert corrupt_reader.or_bounds["NIFTY"] == {"high": -math.inf, "low": math.inf}

    bare_ledger = json.loads(json.dumps(valid_ledger))
    bare_ledger["indices"]["NIFTY"].pop("completion_proof")
    ledger_path.write_text(json.dumps(bare_ledger), encoding="utf-8")
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        bare_reader = _new_advisor(tmp_path, "bare-complete-reader")
    bare_reader._read_or_ledger_snapshot(day)
    assert bare_reader.or_evidence["NIFTY"]["status"] != "COMPLETE"
    assert bare_reader.or_bounds["NIFTY"] == {"high": -math.inf, "low": math.inf}
    for manager in (advisor, restored, corrupt_reader, bare_reader):
        manager.shutdown_or_reconciliation_worker()


def test_complete_reservation_reloads_validated_proof_without_provider_refetch(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "test-only-token")
    _ledger, writer = _write_valid_proof_ledger(tmp_path, monkeypatch, day, now_ms)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, "complete-proof-reload")

    class FailFastHTTP:
        def __init__(self):
            self.get_calls = 0

        def get(self, *args, **kwargs):
            self.get_calls += 1
            raise AssertionError("validated COMPLETE proof must not trigger another provider request")

    fail_fast_client = FailFastHTTP()
    advisor._http_client = fail_fast_client
    advisor._or_reconciliation_loaded_session_day = day
    advisor.or_reconciliation_frozen = False
    advisor._provider_verified_or_proofs.clear()
    for index_name in advisor.or_bounds:
        advisor.or_evidence[index_name] = {
            **advisor._empty_or_evidence(day),
            "status": "PENDING_RECONCILIATION",
            "source": "TEST_TRANSIENT_PROOF_REREAD_FAILURE",
        }
        advisor.or_bounds[index_name] = {"high": -math.inf, "low": math.inf}

    try:
        assert advisor._seed_or_bounds_from_api_serialized(
            session_day=day, current_time_ms=now_ms, force=True
        ) is True
        assert advisor.or_reconciliation_frozen is True
        for index_name in advisor.or_bounds:
            evidence = advisor.or_evidence[index_name]
            assert evidence["status"] == "COMPLETE"
            proof_identity = (day.isoformat(), evidence["proof_sha256"])
            assert advisor._trusted_or_proofs[index_name] == proof_identity
            assert index_name not in advisor._provider_verified_or_proofs
        assert fail_fast_client.get_calls == 0
    finally:
        advisor.shutdown_or_reconciliation_worker()
        writer.shutdown_or_reconciliation_worker()

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


def test_unbound_legacy_proof_is_untrusted_and_uses_one_bounded_refetch(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    available_at_ms = _india_ts(day, dt_time(10, 0))
    ledger_path, _writer = _write_valid_proof_ledger(
        tmp_path, monkeypatch, day, available_at_ms
    )
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    state = raw["indices"]["NIFTY"]
    state["attempt_count"] = _writer.OR_MAX_RETRY_ATTEMPTS
    state["last_attempt_timestamp_ms"] = available_at_ms
    state.pop("request_id", None)
    state["completion_proof"].pop("request_id", None)
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    restored = _new_advisor(tmp_path, "unbound-legacy-proof-reader")
    _, indices = restored._read_or_ledger_snapshot(day, apply_snapshot=False)
    assert indices["NIFTY"].get("completion_proof") is None
    assert indices["NIFTY"]["request_id"] is None
    assert indices["NIFTY"]["legacy_availability_refetch_required"] is True

    allowed, reason, attempts = restored._reserve_or_reconciliation_attempt(
        day, "NIFTY", available_at_ms + restored.OR_MIN_RETRY_INTERVAL_MS, False
    )
    assert (allowed, reason, attempts) == (
        True, "LEGACY_AVAILABILITY_REFETCH_RESERVED",
        restored.OR_MAX_RETRY_ATTEMPTS,
    )
    migrated = json.loads(ledger_path.read_text(encoding="utf-8"))["indices"]["NIFTY"]
    assert migrated["request_id"]
    assert migrated["legacy_availability_refetch_count"] == 1
    assert migrated["legacy_availability_refetch_required"] is False
    assert migrated["attempt_count"] == restored.OR_MAX_RETRY_ATTEMPTS


def test_replay_or_reconciliation_uses_event_time_only_and_never_calls_http(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    event_ms = _india_ts(day, dt_time(10, 0))
    client = SimpleNamespace(get=Mock(side_effect=AssertionError("HTTP forbidden in replay")))
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = SentinelLiveStreamAdvisor(
            wal_path=str(tmp_path / "replay-clock.json"),
            or_reconciliation_state_path=str(tmp_path / "replay-or-ledger.json"),
            enable_stdout=False,
            replay_mode=True,
            session_clock=lambda: (_ for _ in ()).throw(AssertionError("host/session clock forbidden")),
            http_client=client,
        )
    monkeypatch.setattr(
        advisor_module, "_wall_clock_seconds",
        lambda: (_ for _ in ()).throw(AssertionError("host clock forbidden in replay")),
    )
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "offline-test-token")

    assert advisor._seed_or_bounds_from_api_if_late_boot(
        session_day=day, current_time_ms=event_ms, force=True
    ) is False
    client.get.assert_not_called()
    assert not (tmp_path / "replay-or-ledger.json").exists()


def test_replay_completed_bar_runs_real_or_queue_path_without_host_clock_or_http(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    # This is the completed 09:45-09:50 bucket, immediately after the freeze.
    bar_start_ms = _india_ts(day, dt_time(9, 45))
    epoch = bar_start_ms // 300_000
    boundary_ms = (epoch + 1) * 300_000
    ledger = tmp_path / "replay-bar-or-ledger.json"

    class ForbiddenHTTP:
        def __init__(self):
            self.get_calls = 0

        def get(self, *args, **kwargs):
            self.get_calls += 1
            raise AssertionError("replay bar attempted provider HTTP")

    client = ForbiddenHTTP()
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    class ReplayDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return replay_now.astimezone(tz) if tz is not None else replay_now

    replay_now = ReplayDateTime.fromtimestamp(
        (boundary_ms + 2_000) / 1000.0, tz=ZoneInfo("Asia/Kolkata")
    )
    monkeypatch.setattr(advisor_module, "datetime", ReplayDateTime)
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "replay-bar-apm.json"),
        or_reconciliation_state_path=str(ledger),
        enable_stdout=False,
        replay_mode=True,
        session_clock=lambda: replay_now,
        http_client=client,
    )
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "offline-test-token")
    enqueue_calls = Mock(wraps=advisor._enqueue_or_reconciliation)
    monkeypatch.setattr(advisor, "_enqueue_or_reconciliation", enqueue_calls)
    class HostClockForbidden:
        def __init__(self, real_time_module):
            self._real_time_module = real_time_module

        def time(self):
            raise AssertionError("host clock used during replay")

        def __getattr__(self, name):
            return getattr(self._real_time_module, name)

    real_time_module = advisor_module.time
    monkeypatch.setattr(
        advisor_module,
        "time",
        HostClockForbidden(real_time_module),
    )

    try:
        advisor._on_5m_bar_close(
            "NIFTY", 25_000.0, 25_020.0, 24_990.0, 25_010.0, 100.0,
            datetime.fromtimestamp(boundary_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")).time(),
            bar_start_ms, epoch, decision_available_at_ms=boundary_ms + 1,
        )
        assert advisor.replay_mode is True
        assert advisor._mode5_last_eval_rejection.get("NIFTY") is None
        assert advisor._last_completed_5m_epoch["NIFTY"] == epoch
        assert advisor.bars_5m_history["NIFTY"][-1]["epoch_5min"] == epoch
        assert advisor.bars_5m_history["NIFTY"][-1]["completeness"] == "CALLER_COMPLETED_BAR"
        enqueue_calls.assert_not_called()
        assert client.get_calls == 0
        assert not ledger.exists()
        assert client is advisor._http_client
    finally:
        advisor.shutdown_or_reconciliation_worker()
        _wait_for_queue_tasks_bounded(advisor._or_request_queue)
        advisor._or_worker_thread.join(timeout=3.0)
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


def test_replay_option_quote_uses_event_clock_and_rejects_unmapped_ingress_domain(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    event_time = datetime.combine(day, dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    event_ms = int(event_time.timestamp() * 1000)

    class ForbiddenHTTP:
        def get(self, *args, **kwargs):
            raise AssertionError("replay quote attempted HTTP")

    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "replay-quote-apm.json"),
        or_reconciliation_state_path=str(tmp_path / "replay-quote-ledger.json"),
        enable_stdout=False,
        replay_mode=True,
        session_clock=lambda: event_time,
        http_client=ForbiddenHTTP(),
    )
    monkeypatch.setattr(
        advisor_module, "_wall_clock_seconds",
        lambda: (_ for _ in ()).throw(AssertionError("replay quote consulted host wall clock")),
    )
    depth = SimpleNamespace(
        symbol="NIFTY 25000 CE",
        token="NSE_FO|NIFTY_TEST_TOKEN",
        exchange_timestamp_ms=event_ms,
        ingress_monotonic_ns=987_654_321,
        ingress_wall_utc="2026-11-18T04:30:00Z",
        sequence_id=1,
    )
    try:
        advisor._evaluate_option_depth(depth)
        assert advisor.veto_counters.get("OPTION_DEPTH_TIMESTAMP") == 1
        assert advisor._option_depth_watermarks["NIFTY"] == {}
        assert advisor.apms["NIFTY"].state == advisor_module.STATE_STANDBY
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


@pytest.mark.parametrize(
    ("availability_offset", "expected_reason"),
    [
        (None, "MODE5_BAR_AVAILABILITY_UNPROVEN"),
        (-1, "MODE5_BAR_NOT_AVAILABLE_AT_DECISION"),
        (0, "MODE5_BAR_AVAILABILITY_AMBIGUOUS"),
    ],
)
def test_mode5_bar_availability_rejection_preserves_session_grid_history_and_candidate_state(
    tmp_path: Path, monkeypatch, availability_offset: int | None, expected_reason: str
):
    day = date(2026, 11, 18)
    timestamp_ms = _india_ts(day, dt_time(10, 0))
    epoch = timestamp_ms // 300_000
    boundary_ms = (epoch + 1) * 300_000
    _freeze_advisor_clock(monkeypatch, boundary_ms + 2_000)
    advisor = _new_advisor(tmp_path, f"availability-preflight-{availability_offset}")

    old_day = date(2026, 11, 17)
    signal = object()
    metadata = object()
    grid = object()
    advisor._rp2_session_dates["NIFTY"] = old_day
    advisor._last_5m_timestamp_ms["NIFTY"] = timestamp_ms - 300_000
    advisor._last_completed_5m_epoch["NIFTY"] = epoch - 1
    advisor.bars_5m_history["NIFTY"] = [{"sentinel": "raw-history"}]
    advisor.bars_5m_strategy_history["NIFTY"] = [{"sentinel": "strategy-history"}]
    advisor.session_open_prices["NIFTY"] = 24_321.0
    advisor.rp2_upper_pierced_before_1030["NIFTY"] = True
    advisor.rp2_lower_pierced_before_1030["NIFTY"] = True
    advisor.rp2_pierced_before_1030["NIFTY"] = True
    advisor.evaluated_5m_epochs["NIFTY"] = {epoch - 1}
    advisor.rbfn_grids_frozen["NIFTY"] = True
    advisor.cached_rbfn_grids["NIFTY"] = grid
    advisor.cached_rbfn_signals["NIFTY"] = signal
    advisor._cached_rbfn_candidate_meta["NIFTY"] = metadata
    advisor._mode5_last_eval_rejection["NIFTY"] = "PREEXISTING_REASON"
    before = {
        "rp2_session": advisor._rp2_session_dates["NIFTY"],
        "last_ts": advisor._last_5m_timestamp_ms["NIFTY"],
        "last_epoch": advisor._last_completed_5m_epoch["NIFTY"],
        "raw_history": list(advisor.bars_5m_history["NIFTY"]),
        "strategy_history": list(advisor.bars_5m_strategy_history["NIFTY"]),
        "session_open": advisor.session_open_prices["NIFTY"],
        "latches": (
            advisor.rp2_upper_pierced_before_1030["NIFTY"],
            advisor.rp2_lower_pierced_before_1030["NIFTY"],
            advisor.rp2_pierced_before_1030["NIFTY"],
        ),
        "epochs": set(advisor.evaluated_5m_epochs["NIFTY"]),
        "grid_frozen": advisor.rbfn_grids_frozen["NIFTY"],
        "grid": advisor.cached_rbfn_grids["NIFTY"],
        "signal": advisor.cached_rbfn_signals["NIFTY"],
        "metadata": advisor._cached_rbfn_candidate_meta["NIFTY"],
        "or_bounds": dict(advisor.or_bounds["NIFTY"]),
        "or_evidence": dict(advisor.or_evidence["NIFTY"]),
        "or_generation": dict(advisor._or_generation),
        "queue_depth": advisor._or_request_queue.qsize(),
        "ledger": _ledger_path(tmp_path).read_bytes(),
    }
    enqueue = Mock(wraps=advisor._enqueue_or_reconciliation)
    advisor._enqueue_or_reconciliation = enqueue

    available_at = None if availability_offset is None else boundary_ms + availability_offset
    result = advisor._on_5m_bar_close_locked(
        "NIFTY", 25_100.0, 25_120.0, 25_090.0, 25_110.0, 100.0,
        dt_time(10, 5), timestamp_ms, epoch,
        decision_available_at_ms=available_at,
    )

    assert result is None
    assert advisor._mode5_last_eval_rejection["NIFTY"] == expected_reason
    assert advisor._rp2_session_dates["NIFTY"] == before["rp2_session"]
    assert advisor._last_5m_timestamp_ms["NIFTY"] == before["last_ts"]
    assert advisor._last_completed_5m_epoch["NIFTY"] == before["last_epoch"]
    assert advisor.bars_5m_history["NIFTY"] == before["raw_history"]
    assert advisor.bars_5m_strategy_history["NIFTY"] == before["strategy_history"]
    assert advisor.session_open_prices["NIFTY"] == before["session_open"]
    assert (
        advisor.rp2_upper_pierced_before_1030["NIFTY"],
        advisor.rp2_lower_pierced_before_1030["NIFTY"],
        advisor.rp2_pierced_before_1030["NIFTY"],
    ) == before["latches"]
    assert advisor.evaluated_5m_epochs["NIFTY"] == before["epochs"]
    assert advisor.rbfn_grids_frozen["NIFTY"] is before["grid_frozen"]
    assert advisor.cached_rbfn_grids["NIFTY"] is before["grid"]
    assert advisor.cached_rbfn_signals["NIFTY"] is before["signal"]
    assert advisor._cached_rbfn_candidate_meta["NIFTY"] is before["metadata"]
    assert advisor.or_bounds["NIFTY"] == before["or_bounds"]
    assert advisor.or_evidence["NIFTY"] == before["or_evidence"]
    assert advisor._or_generation == before["or_generation"]
    assert advisor._or_request_queue.qsize() == before["queue_depth"]
    assert _ledger_path(tmp_path).read_bytes() == before["ledger"]
    enqueue.assert_not_called()


def test_stale_or_response_cannot_persist_after_new_request_reservation(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    first_reserved_at_ms = _india_ts(day, dt_time(10, 0))
    second_reserved_at_ms = first_reserved_at_ms + 60_000
    _freeze_advisor_clock(monkeypatch, second_reserved_at_ms)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, "stale-request-id")
    parsed = advisor._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None

    assert advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", first_reserved_at_ms, False, request_id="old-request"
    )[0]
    assert advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", second_reserved_at_ms, True, request_id="new-request"
    )[0]
    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=second_reserved_at_ms + 60_000,
        request_id="old-request",
    ) is False
    saved = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    state = saved["indices"]["NIFTY"]
    assert state["request_id"] == "new-request"
    assert state.get("completion_proof") is None


def test_mode5_bar_availability_after_evaluation_clock_is_rejected_pre_mutation(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    timestamp_ms = _india_ts(day, dt_time(10, 0))
    epoch = timestamp_ms // 300_000
    boundary_ms = (epoch + 1) * 300_000
    _freeze_advisor_clock(monkeypatch, boundary_ms + 2_000)
    advisor = _new_advisor(tmp_path, "availability-after-evaluation-clock")
    before = {
        "session": dict(advisor._rp2_session_dates),
        "raw": {key: list(value) for key, value in advisor.bars_5m_history.items()},
        "strategy": {key: list(value) for key, value in advisor.bars_5m_strategy_history.items()},
        "watermarks": dict(advisor._last_5m_timestamp_ms),
        "epochs": dict(advisor._last_completed_5m_epoch),
        "grid_frozen": dict(advisor.rbfn_grids_frozen),
        "candidate": dict(advisor._cached_rbfn_candidate_meta),
    }
    try:
        result = advisor._on_5m_bar_close_locked(
            "NIFTY", 25_100.0, 25_120.0, 25_090.0, 25_110.0, 100.0,
            dt_time(10, 5), timestamp_ms, epoch,
            decision_available_at_ms=boundary_ms + 2_001,
        )
        assert result is None
        assert advisor._mode5_last_eval_rejection["NIFTY"] == (
            "MODE5_BAR_AVAILABILITY_AFTER_EVALUATION_CLOCK"
        )
        assert dict(advisor._rp2_session_dates) == before["session"]
        assert {key: list(value) for key, value in advisor.bars_5m_history.items()} == before["raw"]
        assert {key: list(value) for key, value in advisor.bars_5m_strategy_history.items()} == before["strategy"]
        assert dict(advisor._last_5m_timestamp_ms) == before["watermarks"]
        assert dict(advisor._last_completed_5m_epoch) == before["epochs"]
        assert dict(advisor.rbfn_grids_frozen) == before["grid_frozen"]
        assert dict(advisor._cached_rbfn_candidate_meta) == before["candidate"]
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


@pytest.mark.parametrize("bar_close_time", [dt_time(9, 10), dt_time(15, 5)])
def test_out_of_session_completed_bars_do_not_advance_mode5_state(
    tmp_path: Path, monkeypatch, bar_close_time: dt_time
):
    day = date(2026, 11, 18)
    start = datetime.combine(day, bar_close_time, tzinfo=ZoneInfo("Asia/Kolkata")) - timedelta(minutes=5)
    timestamp_ms = int(start.timestamp() * 1000)
    epoch = timestamp_ms // 300_000
    boundary_ms = (epoch + 1) * 300_000
    decision_ms = boundary_ms + 1
    _freeze_advisor_clock(monkeypatch, decision_ms + 1)
    advisor = _new_advisor(tmp_path, f"outside-mode5-session-{bar_close_time:%H%M}")
    prior_signal = object()
    prior_metadata = object()
    advisor.cached_rbfn_signals["NIFTY"] = prior_signal
    advisor._cached_rbfn_candidate_meta["NIFTY"] = prior_metadata
    before = {
        "session": dict(advisor._rp2_session_dates),
        "timestamps": dict(advisor._last_5m_timestamp_ms),
        "epochs": dict(advisor._last_completed_5m_epoch),
        "raw_history": {key: list(value) for key, value in advisor.bars_5m_history.items()},
        "strategy_history": {
            key: list(value) for key, value in advisor.bars_5m_strategy_history.items()
        },
    }
    try:
        result = advisor._on_5m_bar_close_locked(
            "NIFTY", 25_000.0, 25_020.0, 24_990.0, 25_010.0, 100.0,
            bar_close_time, timestamp_ms, epoch,
            decision_available_at_ms=decision_ms,
        )
        assert result is None
        assert advisor._mode5_last_eval_rejection["NIFTY"] == "MODE5_BAR_OUTSIDE_ACTIVE_SESSION"
        assert advisor._rp2_session_dates == before["session"]
        assert advisor._last_5m_timestamp_ms == before["timestamps"]
        assert advisor._last_completed_5m_epoch == before["epochs"]
        assert advisor.bars_5m_history == before["raw_history"]
        assert advisor.bars_5m_strategy_history == before["strategy_history"]
        assert advisor.cached_rbfn_signals["NIFTY"] is prior_signal
        assert advisor._cached_rbfn_candidate_meta["NIFTY"] is prior_metadata
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


def test_mode5_or_pair_validates_target_and_companion_under_one_lock_snapshot(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    decision_ms = _india_ts(day, dt_time(10, 0))
    epoch = decision_ms // 300_000
    boundary_ms = (epoch + 1) * 300_000
    advisor = _new_advisor(tmp_path, "or-pair-atomic-snapshot")
    for index_name in ("NIFTY", "SENSEX"):
        advisor.or_evidence[index_name] = {
            **advisor._empty_or_evidence(day),
            "status": "PARTIAL",
        }

    target_validation_done = threading.Event()
    mutation_attempted = threading.Event()
    mutation_done = threading.Event()
    original_validate = advisor._validate_mode5_or_evidence
    observed_indices = []

    def observe_locked_validation(index_name, *args, **kwargs):
        assert advisor._lock._is_owned()
        observed_indices.append(index_name)
        result = original_validate(index_name, *args, **kwargs)
        if index_name == "NIFTY":
            target_validation_done.set()
            assert mutation_attempted.wait(timeout=2.0)
        return result

    advisor._validate_mode5_or_evidence = observe_locked_validation

    def replace_companion_after_target_snapshot():
        assert target_validation_done.wait(timeout=2.0)
        mutation_attempted.set()
        with advisor._lock:
            advisor._or_generation["SENSEX"] += 1
            advisor.or_evidence["SENSEX"] = {
                **advisor._empty_or_evidence(date(2026, 11, 19)),
                "status": "PARTIAL",
            }
        mutation_done.set()

    worker = threading.Thread(target=replace_companion_after_target_snapshot)
    worker.start()
    try:
        _, _, details = advisor._validate_mode5_or_pair(
            "NIFTY", decision_ms, boundary_ms, boundary_ms + 1
        )
        assert observed_indices == ["NIFTY", "SENSEX"]
        assert details["target"]["evidence"]["session_date"] == day.isoformat()
        assert details["companion"]["evidence"]["session_date"] == day.isoformat()
        worker.join(timeout=2.0)
        assert not worker.is_alive()
        assert mutation_done.is_set()
        assert advisor.or_evidence["SENSEX"]["session_date"] == "2026-11-19"
    finally:
        if worker.is_alive():
            worker.join(timeout=2.0)
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


def test_mode5_completed_bar_calculations_use_normalized_ohlcv_values(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    timestamp_ms = _india_ts(day, dt_time(10, 0))
    epoch = timestamp_ms // 300_000
    boundary_ms = (epoch + 1) * 300_000
    _freeze_advisor_clock(monkeypatch, boundary_ms + 2_000)
    advisor = _new_advisor(tmp_path, "normalized-bar-values")

    class NonArithmeticFloat(float):
        def __sub__(self, _other):
            raise AssertionError("raw caller OHLCV reached calculations")

        def __rsub__(self, _other):
            raise AssertionError("raw caller OHLCV reached calculations")

    try:
        advisor._on_5m_bar_close_locked(
            "NIFTY", NonArithmeticFloat(25_100), NonArithmeticFloat(25_120),
            NonArithmeticFloat(25_090), NonArithmeticFloat(25_110),
            NonArithmeticFloat(100), dt_time(10, 5), timestamp_ms, epoch,
            decision_available_at_ms=boundary_ms + 1,
        )
        stored = advisor.bars_5m_history["NIFTY"][-1]
        assert all(type(stored[key]) is float for key in ("open", "high", "low", "close", "volume"))
        strategy_stored = advisor.bars_5m_strategy_history["NIFTY"][-1]
        assert all(type(strategy_stored[key]) is float for key in ("open", "high", "low", "close", "volume"))
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


def test_non_applying_or_ledger_snapshot_leaves_all_memory_indices_unchanged(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    _, advisor = _write_valid_proof_ledger(tmp_path, monkeypatch, day, now_ms)
    before_bounds = {
        index: dict(bounds) for index, bounds in advisor.or_bounds.items()
    }
    before_evidence = {
        index: dict(evidence) for index, evidence in advisor.or_evidence.items()
    }

    ledger, indices = advisor._read_or_ledger_snapshot(day, apply_snapshot=False)

    assert set(ledger["indices"]) == {"NIFTY", "BANKNIFTY", "SENSEX"}
    assert all(indices[index].get("completion_proof") for index in indices)
    assert advisor.or_bounds == before_bounds
    assert advisor.or_evidence == before_evidence


@pytest.mark.parametrize("persist_result", [True, False])
def test_invalidated_or_request_cannot_apply_or_mutate_post_network_memory(
    tmp_path: Path, monkeypatch, persist_result: bool
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(9, 45))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: now_ms / 1000.0)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, f"invalidated-reread-{persist_result}")

    advisor._or_reconciliation_loaded_session_day = day
    advisor.or_reconciliation_frozen = False
    for index_name in advisor.or_bounds:
        advisor.or_evidence[index_name] = {
            **advisor._empty_or_evidence(day),
            "status": "PARTIAL",
            "source": "TEST_PRE_NETWORK_MEMORY",
        }
        advisor.or_bounds[index_name] = {"high": 123.0, "low": 100.0}
    with advisor._lock:
        generations = dict(advisor._or_generation)
    context = (f"request-{persist_result}", day, generations)
    with advisor._or_request_lock:
        advisor._or_outstanding_request = context

    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": _v2_or_candles(day)}},
    )
    advisor._http_client = SimpleNamespace(get=Mock(return_value=response))
    before_evidence = {
        index: dict(evidence) for index, evidence in advisor.or_evidence.items()
    }
    before_bounds = {index: dict(bounds) for index, bounds in advisor.or_bounds.items()}
    original_persist = advisor._persist_or_completion_proof

    def persist_then_invalidate(*args, **kwargs):
        if persist_result:
            result = original_persist(*args, **kwargs)
        else:
            result = False
        with advisor._or_request_lock:
            advisor._or_outstanding_request = None
        return result

    advisor._persist_or_completion_proof = persist_then_invalidate
    try:
        result = advisor._seed_or_bounds_from_api_if_late_boot(
            session_day=day,
            current_time_ms=now_ms,
            force=True,
            _request_context=context,
        )
        assert result is False
        assert advisor._http_client.get.call_count == 1
        assert advisor.or_evidence == before_evidence
        assert advisor.or_bounds == before_bounds
        persisted = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
        has_proof = "completion_proof" in persisted["indices"]["NIFTY"]
        assert has_proof is persist_result
    finally:
        advisor.shutdown_or_reconciliation_worker()


def test_same_digest_or_proof_preserves_effective_receipt_and_refetches_after_new_reservation(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    t1 = _india_ts(day, dt_time(10, 0))
    t2 = t1 + 60_000
    _freeze_advisor_clock(monkeypatch, t2 + 60_000)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, "same-digest-proof-writer")
    parsed = advisor._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: t1 / 1000.0)
    assert advisor._reserve_or_reconciliation_attempt(day, "NIFTY", t1, False)[0]

    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=t1 - 1
    ) is False
    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=t1
    ) is True
    ledger_path = _ledger_path(tmp_path)
    initial = json.loads(ledger_path.read_text(encoding="utf-8"))
    first_proof = initial["indices"]["NIFTY"]["completion_proof"]
    assert first_proof["available_at_ms"] == t1

    # A repeated identical response after T1 must not rewrite the receipt time.
    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=t1 + 1
    ) is True
    repeated = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert repeated["indices"]["NIFTY"]["completion_proof"] == first_proof

    conflicting_candles = [list(row) for row in _v2_or_candles(day)]
    conflicting_candles[0][4] = 100.25
    conflicting = advisor._parse_complete_v2_or_candles(conflicting_candles, day)
    assert conflicting is not None
    assert advisor._persist_or_completion_proof(
        day, "NIFTY", conflicting, available_at_ms=t1 + 2
    ) is False
    after_conflict = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert after_conflict["indices"]["NIFTY"]["completion_proof"] == first_proof

    _, current_indices = advisor._read_or_ledger_snapshot(day)
    assert current_indices["NIFTY"]["completion_proof"]["available_at_ms"] == t1
    assert advisor.or_evidence["NIFTY"]["available_at_ms"] == t1

    # Model a later durable retry reservation. The old proof is still intact
    # in bytes but is no longer admissible against T2, so its receipt cannot
    # be relabelled by an earlier retry response.
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    raw["indices"]["NIFTY"]["attempt_count"] = 2
    raw["indices"]["NIFTY"]["last_attempt_timestamp_ms"] = t2
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")
    _, stale_indices = advisor._read_or_ledger_snapshot(day)
    assert stale_indices["NIFTY"].get("completion_proof") is None
    assert stale_indices["NIFTY"]["legacy_availability_refetch_required"] is True
    assert advisor.or_evidence["NIFTY"]["status"] != "COMPLETE"
    assert advisor.or_evidence["NIFTY"]["available_at_ms"] is None
    assert advisor.or_bounds["NIFTY"] == {"high": -math.inf, "low": math.inf}
    assert "NIFTY" not in advisor._provider_verified_or_proofs

    t3 = t2 + advisor.OR_MIN_RETRY_INTERVAL_MS
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: t3 / 1000.0)
    reserved, reason, attempts = advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", t3, False
    )
    assert (reserved, reason, attempts) == (True, "RESERVED", 3)
    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=t3 - 1
    ) is False
    pending_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert "completion_proof" not in pending_ledger["indices"]["NIFTY"]
    assert pending_ledger["indices"]["NIFTY"]["legacy_availability_refetch_required"] is True
    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=t3
    ) is True
    _, effective_indices = advisor._read_or_ledger_snapshot(day)
    assert effective_indices["NIFTY"]["completion_proof"]["available_at_ms"] == t3
    assert advisor.or_evidence["NIFTY"]["available_at_ms"] == t3

    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        restarted = _new_advisor(tmp_path, "same-digest-proof-reader")
    restarted._read_or_ledger_snapshot(day)
    assert restarted.or_evidence["NIFTY"]["status"] == "COMPLETE"
    assert restarted.or_evidence["NIFTY"]["available_at_ms"] == t3
    assert "NIFTY" not in restarted._provider_verified_or_proofs


@pytest.mark.parametrize("tamper", ["availability", "missing_metadata_checksum", "metadata_checksum"])
def test_or_proof_metadata_tampering_routes_to_bounded_retry(
    tmp_path: Path, monkeypatch, tamper: str
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    ledger_path, _ = _write_valid_proof_ledger(tmp_path, monkeypatch, day, now_ms)
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    proof = raw["indices"]["NIFTY"]["completion_proof"]
    if tamper == "availability":
        proof["available_at_ms"] += 1
    elif tamper == "missing_metadata_checksum":
        proof.pop("metadata_sha256")
    else:
        proof["metadata_sha256"] = "0" * 64
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        restored = _new_advisor(tmp_path, f"tampered-proof-reader-{tamper}")
    restored._read_or_ledger_snapshot(day)
    assert restored.or_reconciliation_frozen is False
    assert restored.or_evidence["NIFTY"]["status"] != "COMPLETE"

    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: (now_ms + 65_000) / 1000.0)
    allowed, reason, attempts = restored._reserve_or_reconciliation_attempt(
        day, "NIFTY", now_ms + 65_000, False
    )
    assert (allowed, reason, attempts) == (True, "RESERVED", 2)
    saved = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert saved["indices"]["NIFTY"]["attempt_count"] == 2
    assert saved["indices"]["NIFTY"]["legacy_availability_refetch_required"] is True


def test_or_proof_availability_before_durable_attempt_is_legacy_untrusted(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    available_at_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, available_at_ms)
    ledger_path, _ = _write_valid_proof_ledger(
        tmp_path, monkeypatch, day, available_at_ms
    )
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    # Keep the proof checksum valid but make its receipt predate the durable
    # request reservation recorded for this attempt.
    raw["indices"]["NIFTY"]["last_attempt_timestamp_ms"] = available_at_ms + 1
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        restored = _new_advisor(tmp_path, "pre-attempt-availability-reader")
    restored._read_or_ledger_snapshot(day)
    assert restored.or_reconciliation_frozen is False
    assert restored.or_evidence["NIFTY"]["status"] != "COMPLETE"
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: (available_at_ms + 60_001) / 1000.0)
    allowed, reason, attempts = restored._reserve_or_reconciliation_attempt(
        day, "NIFTY", available_at_ms + 60_001, False
    )
    assert (allowed, reason, attempts) == (True, "RESERVED", 2)
    saved = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert saved["indices"]["NIFTY"]["legacy_availability_refetch_required"] is True


@pytest.mark.parametrize("legacy_availability", ["missing", None], ids=["missing", "null"])
def test_legacy_or_proof_without_availability_does_not_freeze_and_can_retry(
    tmp_path: Path, monkeypatch, legacy_availability
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)

    # Build a structurally valid pre-causality proof, then remove the field
    # that proves when the HTTP response became available to the engine.
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        writer = _new_advisor(tmp_path, "legacy-proof-writer")
    parsed = writer._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    proof = {
        "source": "UPSTOX_V2_1M_EXACT_30",
        "coverage_count": parsed["coverage_count"],
        "coverage_start_ms": parsed["coverage_start_ms"],
        "coverage_end_ms": parsed["coverage_end_ms"],
        "source_timestamp_ms": parsed["source_timestamp_ms"],
        "candles": parsed["normalized_candles"],
        "sha256": writer._or_candles_digest(parsed["normalized_candles"]),
    }
    if legacy_availability is None:
        proof["available_at_ms"] = None
    ledger_path = _ledger_path(tmp_path)
    _write_ledger(ledger_path, day, {
        "NIFTY": _attempt_state(2, now_ms - 120_000, proof),
        "BANKNIFTY": _attempt_state(0, 0),
        "SENSEX": _attempt_state(0, 0),
    })

    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    incomplete = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": _v2_or_candles(day, count=29)}},
    )
    with patch("requests.get", return_value=incomplete) as get_mock:
        restored = _new_advisor(tmp_path, "legacy-proof-reader")

    assert get_mock.call_count == 3
    assert restored.or_reconciliation_frozen is False
    assert restored.or_evidence["NIFTY"]["status"] == "PENDING_RECONCILIATION"
    assert restored.or_reconcile_retry_count["NIFTY"] == 3
    assert restored.or_bounds["NIFTY"] == {"high": -math.inf, "low": math.inf}
    saved = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert saved["indices"]["NIFTY"]["attempt_count"] == 3
    assert "completion_proof" not in saved["indices"]["NIFTY"]


def test_legacy_or_proof_at_attempt_cap_gets_one_separate_refetch(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        writer = _new_advisor(tmp_path, "capped-legacy-proof-writer")
    parsed = writer._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    proof = {
        "source": "UPSTOX_V2_1M_EXACT_30",
        "coverage_count": parsed["coverage_count"],
        "coverage_start_ms": parsed["coverage_start_ms"],
        "coverage_end_ms": parsed["coverage_end_ms"],
        "source_timestamp_ms": parsed["source_timestamp_ms"],
        "candles": parsed["normalized_candles"],
        "sha256": writer._or_candles_digest(parsed["normalized_candles"]),
    }
    ledger_path = _ledger_path(tmp_path)
    _write_ledger(ledger_path, day, {
        "NIFTY": _attempt_state(writer.OR_MAX_RETRY_ATTEMPTS, now_ms - 120_000, proof),
        "BANKNIFTY": _attempt_state(0, 0),
        "SENSEX": _attempt_state(0, 0),
    })

    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    incomplete = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": {"candles": _v2_or_candles(day, count=29)}},
    )
    with patch("requests.get", return_value=incomplete) as get_mock:
        restored = _new_advisor(tmp_path, "capped-legacy-proof-reader")
    assert get_mock.call_count == 3
    assert restored.or_reconcile_retry_count["NIFTY"] == writer.OR_MAX_RETRY_ATTEMPTS
    assert restored.or_evidence["NIFTY"]["status"] == "PENDING_RECONCILIATION"
    assert restored.or_reconciliation_frozen is False

    saved = json.loads(ledger_path.read_text(encoding="utf-8"))
    nifty = saved["indices"]["NIFTY"]
    assert nifty["attempt_count"] == writer.OR_MAX_RETRY_ATTEMPTS
    assert nifty["last_attempt_timestamp_ms"] == now_ms
    assert nifty["legacy_availability_refetch_count"] == 1
    assert nifty["legacy_availability_refetch_required"] is False
    assert "completion_proof" not in nifty

    # Restart before a replacement proof exists. The fresh constructor may
    # reconcile other indices, but must not issue a second NIFTY request.
    with patch("requests.get", return_value=incomplete) as restart_get:
        restarted = _new_advisor(tmp_path, "capped-legacy-proof-restarted")
    restarted_nifty_calls = [
        call for call in restart_get.call_args_list
        if "NSE_INDEX%7CNifty%2050" in call.args[0]
    ]
    assert restarted_nifty_calls == []
    assert restarted.or_last_reconcile_attempt_ms["NIFTY"] == now_ms
    restarted_allowed, restarted_reason, restarted_attempts = (
        restarted._reserve_or_reconciliation_attempt(day, "NIFTY", now_ms + 1, False)
    )
    assert (restarted_allowed, restarted_reason, restarted_attempts) == (
        False, "ATTEMPT_CAP_REACHED", writer.OR_MAX_RETRY_ATTEMPTS
    )
    migrated_state = json.loads(ledger_path.read_text(encoding="utf-8"))["indices"]["NIFTY"]
    assert migrated_state["attempt_count"] == writer.OR_MAX_RETRY_ATTEMPTS
    assert migrated_state["last_attempt_timestamp_ms"] == now_ms
    assert migrated_state["legacy_availability_refetch_count"] == 1
    assert migrated_state["legacy_availability_refetch_required"] is False
    assert "completion_proof" not in migrated_state

    # The durable migration reservation is T1. Candle bytes that were
    # available before T1 cannot satisfy it; availability at T1 can.
    parsed = restarted._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    assert restarted._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=now_ms - 1
    ) is False
    assert restarted._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=now_ms
    ) is True

    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        completed_restart = _new_advisor(tmp_path, "capped-legacy-proof-completed-restarted")
    completed_restart._read_or_ledger_snapshot(day)
    assert completed_restart.or_last_reconcile_attempt_ms["NIFTY"] == now_ms
    allowed, reason, attempts = completed_restart._reserve_or_reconciliation_attempt(
        day, "NIFTY", now_ms + 1, False
    )
    assert (allowed, reason, attempts) == (
        False, "COMPLETE", writer.OR_MAX_RETRY_ATTEMPTS
    )


def test_ledger_without_proof_clears_untrusted_complete_but_preserves_provider_verified_memory(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, "memory-proof-check")

    untrusted_digest = "a" * 64
    provider_digest = "b" * 64
    for index_name, digest in (("NIFTY", untrusted_digest), ("SENSEX", provider_digest)):
        advisor.or_bounds[index_name] = {"high": 101.0, "low": 99.0}
        advisor.or_evidence[index_name] = {
            "session_date": day.isoformat(),
            "status": "COMPLETE",
            "source": "UPSTOX_V2_1M_EXACT_30",
            "source_timestamp_ms": now_ms - 60_000,
            "available_at_ms": now_ms - 30_000,
            "proof_sha256": digest,
        }
        advisor._trusted_or_proofs[index_name] = (day.isoformat(), digest)
    advisor._provider_verified_or_proofs["SENSEX"] = (day.isoformat(), provider_digest)

    states = {
        index_name: _attempt_state(0, 0)
        for index_name in ("NIFTY", "BANKNIFTY", "SENSEX")
    }
    advisor._apply_or_ledger_snapshot(day, states)

    assert advisor.or_bounds["NIFTY"] == {"high": -math.inf, "low": math.inf}
    assert advisor.or_evidence["NIFTY"]["status"] != "COMPLETE"
    assert advisor.or_bounds["SENSEX"] == {"high": 101.0, "low": 99.0}
    assert advisor.or_evidence["SENSEX"]["status"] == "COMPLETE"


@pytest.mark.parametrize("bad_availability", [True, "not-an-epoch", 0])
def test_malformed_non_null_or_availability_proof_still_fails_closed(
    tmp_path: Path, monkeypatch, bad_availability
):
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock-token-005")
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        writer = _new_advisor(tmp_path, "malformed-proof-writer")
    parsed = writer._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    proof = {
        "source": "UPSTOX_V2_1M_EXACT_30",
        "coverage_count": parsed["coverage_count"],
        "coverage_start_ms": parsed["coverage_start_ms"],
        "coverage_end_ms": parsed["coverage_end_ms"],
        "source_timestamp_ms": parsed["source_timestamp_ms"],
        "available_at_ms": bad_availability,
        "candles": parsed["normalized_candles"],
        "sha256": writer._or_candles_digest(parsed["normalized_candles"]),
    }
    ledger_path = _ledger_path(tmp_path)
    _write_ledger(ledger_path, day, {
        "NIFTY": _attempt_state(1, now_ms - 120_000, proof),
        "BANKNIFTY": _attempt_state(0, 0),
        "SENSEX": _attempt_state(0, 0),
    })
    with patch("requests.get") as get_mock:
        restored = _new_advisor(tmp_path, "malformed-proof-reader")
    assert restored._or_reconciliation_ledger_degraded is True
    assert get_mock.call_count == 0


def test_partial_or_availability_aggregates_max_ingress_and_poison_is_sticky(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    market_now = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, market_now)
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: market_now / 1000.0)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, "partial-or-availability")

    advisor._rp2_session_dates["NIFTY"] = day
    advisor._last_spot_timestamp_ms["NIFTY"] = 0
    event_1 = _india_ts(day, dt_time(9, 15, 1))
    event_2 = _india_ts(day, dt_time(9, 15, 2))
    receipt_1 = _india_ts(day, dt_time(9, 16))
    receipt_2 = _india_ts(day, dt_time(9, 15, 30))
    assert advisor._update_spot("NIFTY", 100.0, event_1, available_at_ms=receipt_1)
    assert advisor._update_spot("NIFTY", 101.0, event_2, available_at_ms=receipt_2)
    evidence = advisor.or_evidence["NIFTY"]
    assert evidence["source_timestamp_ms"] == event_2
    assert evidence["available_at_ms"] == receipt_1
    assert evidence["partial_availability_unproven"] is False

    decision = _india_ts(day, dt_time(9, 17))
    boundary = _india_ts(day, dt_time(9, 20))
    valid, reason, _ = advisor._validate_mode5_or_evidence(
        "NIFTY", decision, boundary, decision
    )
    assert valid is True
    assert reason == "OR_PARTIAL_CAUSAL"

    equal_clock_valid, equal_clock_reason, equal_clock_details = advisor._validate_mode5_or_evidence(
        "NIFTY", decision, boundary, receipt_1
    )
    assert equal_clock_valid is False
    assert equal_clock_reason == "OR_AVAILABILITY_AMBIGUOUS"
    assert equal_clock_details["availability_relation"] == "EQUAL_CLOCKS_AMBIGUOUS"


@pytest.mark.parametrize(
    "bad_availability",
    [None, True, 0, "not-an-epoch", "pre-event"],
    ids=["missing", "boolean", "zero", "malformed", "pre-event"],
)
def test_partial_or_invalid_availability_poison_is_sticky_and_rejected(
    tmp_path: Path, monkeypatch, bad_availability
):
    day = date(2026, 11, 18)
    market_now = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, market_now)
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: market_now / 1000.0)
    with monkeypatch.context() as setup_patch:
        setup_patch.setattr(
            SentinelLiveStreamAdvisor,
            "_seed_or_bounds_from_api_if_late_boot",
            lambda *args, **kwargs: False,
        )
        advisor = _new_advisor(tmp_path, f"partial-or-poison-{bad_availability}")

    advisor._rp2_session_dates["NIFTY"] = day
    advisor._last_spot_timestamp_ms["NIFTY"] = 0
    event_1 = _india_ts(day, dt_time(9, 15, 1))
    event_2 = _india_ts(day, dt_time(9, 15, 2))
    receipt = _india_ts(day, dt_time(9, 15, 30))
    assert advisor._update_spot("NIFTY", 100.0, event_1, available_at_ms=receipt)
    assert advisor._update_spot("NIFTY", 101.0, event_2, available_at_ms=receipt)

    event_3 = _india_ts(day, dt_time(9, 15, 3))
    invalid_receipt = event_3 - 1 if bad_availability == "pre-event" else bad_availability
    assert advisor._update_spot(
        "NIFTY", 102.0, event_3, available_at_ms=invalid_receipt
    )
    assert advisor.or_evidence["NIFTY"]["available_at_ms"] is None
    assert advisor.or_evidence["NIFTY"]["partial_availability_unproven"] is True

    event_4 = _india_ts(day, dt_time(9, 15, 4))
    later_receipt = _india_ts(day, dt_time(9, 16))
    assert advisor._update_spot(
        "NIFTY", 103.0, event_4, available_at_ms=later_receipt
    )
    assert advisor.or_evidence["NIFTY"]["available_at_ms"] is None
    assert advisor.or_evidence["NIFTY"]["partial_availability_unproven"] is True

    valid, reason, _ = advisor._validate_mode5_or_evidence(
        "NIFTY", _india_ts(day, dt_time(9, 17)), _india_ts(day, dt_time(9, 20)),
        _india_ts(day, dt_time(9, 17)),
    )
    assert valid is False
    assert reason == "OR_AVAILABILITY_UNPROVEN"


def test_per_index_reservation_uses_locked_time_after_prior_index_delay(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    first_request_ms = _india_ts(day, dt_time(10, 0))
    clock_ms = [first_request_ms]
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: clock_ms[0] / 1000.0)
    advisor = _new_advisor(tmp_path, "per-index-reservation-clock")

    first = advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", first_request_ms, False, request_id="nifty-request"
    )
    assert first == (True, "RESERVED", 1)
    clock_ms[0] = first_request_ms + 125_000  # prior index's HTTP wait
    second = advisor._reserve_or_reconciliation_attempt(
        day, "SENSEX", first_request_ms, False, request_id="sensex-request"
    )
    assert second == (True, "RESERVED", 1)

    ledger = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert ledger["indices"]["SENSEX"]["last_attempt_timestamp_ms"] == clock_ms[0]
    assert ledger["indices"]["NIFTY"]["last_attempt_timestamp_ms"] == first_request_ms
    assert advisor._reserve_or_reconciliation_attempt(
        day, "SENSEX", first_request_ms, False, request_id="sensex-retry"
    ) == (False, "THROTTLED", 1)
    assert advisor._or_last_ledger_check_ms["SENSEX"] == clock_ms[0]


def test_stale_old_or_request_cannot_commit_after_new_reservation(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    available_at_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, available_at_ms)
    advisor = _new_advisor(tmp_path, "stale-or-request")
    parsed = advisor._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    assert advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", available_at_ms - 60_000, True, request_id="old-request"
    )[0]
    old_context = ("old-request", day, dict(advisor._or_generation))
    assert advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", available_at_ms - 60_000, True, request_id="new-request"
    )[0]
    new_context = ("new-request", day, dict(advisor._or_generation))
    with advisor._or_request_lock:
        advisor._or_outstanding_request = new_context

    assert advisor._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=available_at_ms,
        request_id="old-request", request_context=old_context,
    ) is False
    ledger = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert ledger["indices"]["NIFTY"].get("completion_proof") is None
    assert ledger["indices"]["NIFTY"]["request_id"] == "new-request"


def test_shutdown_and_or_proof_commit_are_serialized(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    available_at_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, available_at_ms)
    advisor = _new_advisor(tmp_path, "shutdown-proof-fence")
    parsed = advisor._parse_complete_v2_or_candles(_v2_or_candles(day), day)
    assert parsed is not None
    assert advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", available_at_ms - 60_000, True, request_id="fenced-request"
    )[0]
    context = ("fenced-request", day, dict(advisor._or_generation))
    with advisor._or_request_lock:
        advisor._or_outstanding_request = context

    proof_write_entered = threading.Event()
    release_proof_write = threading.Event()
    shutdown_lock_attempted = threading.Event()
    original_write = advisor._write_or_reconciliation_ledger_locked

    class ObservedRLock:
        def __init__(self):
            self.inner = threading.RLock()

        def acquire(self, *args, **kwargs):
            if threading.current_thread().name == "shutdown-fence":
                shutdown_lock_attempted.set()
            return self.inner.acquire(*args, **kwargs)

        def release(self):
            return self.inner.release()

        def _is_owned(self):
            return self.inner._is_owned()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, exc_type, exc, tb):
            self.release()

    advisor._lock = ObservedRLock()

    def blocked_proof_write(ledger):
        if ledger["indices"]["NIFTY"].get("completion_proof") is not None:
            proof_write_entered.set()
            assert release_proof_write.wait(timeout=5)
        return original_write(ledger)

    monkeypatch.setattr(advisor, "_write_or_reconciliation_ledger_locked", blocked_proof_write)
    proof_result = []
    proof_thread = threading.Thread(target=lambda: proof_result.append(
        advisor._persist_or_completion_proof(
            day, "NIFTY", parsed, available_at_ms=available_at_ms,
            request_id="fenced-request", request_context=context,
        )
    ))
    proof_thread.start()
    shutdown_done = threading.Event()
    shutdown_thread = threading.Thread(
        name="shutdown-fence",
        target=lambda: (advisor.shutdown_or_reconciliation_worker(), shutdown_done.set()),
    )
    try:
        assert proof_write_entered.wait(timeout=5)
        shutdown_thread.start()
        assert shutdown_lock_attempted.wait(timeout=5)
        assert not shutdown_done.wait(timeout=0.05)
    finally:
        release_proof_write.set()
        proof_thread.join(timeout=5)
        if shutdown_thread.ident is not None:
            shutdown_thread.join(timeout=5)
    assert not proof_thread.is_alive() and not shutdown_thread.is_alive()
    assert proof_result == [True]
    assert shutdown_done.is_set()
    stored = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert stored["indices"]["NIFTY"].get("completion_proof", {}).get("request_id") == "fenced-request"

    # The opposite ordering is fail-closed: shutdown invalidates a proof that
    # has not yet crossed the serialized commit section.
    second_root = tmp_path / "shutdown-before-proof"
    second_root.mkdir()
    second = _new_advisor(second_root, "shutdown-before-proof")
    assert second._reserve_or_reconciliation_attempt(
        day, "NIFTY", available_at_ms - 60_000, True, request_id="shutdown-first"
    )[0]
    stale_context = ("shutdown-first", day, dict(second._or_generation))
    with second._or_request_lock:
        second._or_outstanding_request = stale_context
    second.shutdown_or_reconciliation_worker()
    assert second._persist_or_completion_proof(
        day, "NIFTY", parsed, available_at_ms=available_at_ms,
        request_id="shutdown-first", request_context=stale_context,
    ) is False


@pytest.mark.parametrize("invalidator", ["shutdown", "session_rollover"])
def test_invalidated_or_context_does_not_consume_durable_attempt(
    tmp_path: Path, monkeypatch, invalidator: str
):
    day = date(2026, 11, 18)
    event_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, event_ms)
    advisor = _new_advisor(tmp_path, f"invalidated-before-reserve-{invalidator}")
    context = ("request-before-reserve", day, dict(advisor._or_generation))
    with advisor._or_request_lock:
        advisor._or_outstanding_request = context
    if invalidator == "shutdown":
        advisor.shutdown_or_reconciliation_worker()
    else:
        with advisor._lock:
            advisor._rp2_session_dates["NIFTY"] = day
            advisor._reset_rp2_state_for_session_locked("NIFTY", day + timedelta(days=1))

    # Model the already-active next-session target state. The obsolete
    # reservation may inspect the old durable ledger but must not restore it.
    next_day = day + timedelta(days=1)
    with advisor._lock:
        advisor._rp2_session_dates["NIFTY"] = next_day
        advisor.or_bounds["NIFTY"] = {"high": 26_101.0, "low": 25_901.0}
        advisor.or_evidence["NIFTY"] = {
            "session_date": next_day.isoformat(), "status": "PARTIAL",
            "source": "UPSTOX_TICK_PARTIAL", "source_timestamp_ms": event_ms + 1,
            "available_at_ms": event_ms + 2,
        }
        advisor.or_reconcile_retry_count["NIFTY"] = 0
        advisor.or_last_reconcile_attempt_ms["NIFTY"] = 0
        advisor._or_last_ledger_check_ms["NIFTY"] = 0
        advisor.active_range_high = 26_101.0
        advisor.active_range_low = 25_901.0
    before_state = (
        dict(advisor.or_bounds["NIFTY"]),
        dict(advisor.or_evidence["NIFTY"]),
        advisor.or_reconcile_retry_count["NIFTY"],
        advisor.or_last_reconcile_attempt_ms["NIFTY"],
        advisor._or_last_ledger_check_ms["NIFTY"],
        advisor.active_range_high,
        advisor.active_range_low,
        advisor._rp2_session_dates["NIFTY"],
    )

    result = advisor._reserve_or_reconciliation_attempt(
        day, "NIFTY", event_ms, True,
        request_id=context[0], request_context=context,
    )
    assert result == (False, "REQUEST_INVALIDATED", 0)
    ledger = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert ledger["indices"]["NIFTY"]["attempt_count"] == 0
    after_state = (
        dict(advisor.or_bounds["NIFTY"]),
        dict(advisor.or_evidence["NIFTY"]),
        advisor.or_reconcile_retry_count["NIFTY"],
        advisor.or_last_reconcile_attempt_ms["NIFTY"],
        advisor._or_last_ledger_check_ms["NIFTY"],
        advisor.active_range_high,
        advisor.active_range_low,
        advisor._rp2_session_dates["NIFTY"],
    )
    assert after_state == before_state


def test_or_ledger_read_does_not_resurrect_previous_session_after_rollover(
    tmp_path: Path, monkeypatch
):
    day = date(2026, 11, 18)
    next_day = day + timedelta(days=1)
    event_ms = _india_ts(day, dt_time(10, 0))
    advisor = _new_advisor(tmp_path, "snapshot-rollover-race")
    ledger_path = _ledger_path(tmp_path)
    _write_ledger(ledger_path, day, {
        "NIFTY": _attempt_state(8, event_ms),
        "BANKNIFTY": _attempt_state(4, event_ms),
        "SENSEX": _attempt_state(3, event_ms),
    })
    with advisor._lock:
        advisor._rp2_session_dates["NIFTY"] = day
        advisor._reset_rp2_state_for_session_locked("NIFTY", day)

    loaded = threading.Event()
    release_read = threading.Event()
    original_load = advisor._load_or_reconciliation_ledger_locked

    def pause_after_read(expected_day, lock_created):
        snapshot = original_load(expected_day, lock_created)
        loaded.set()
        if not release_read.wait(timeout=5):
            raise AssertionError("snapshot race test did not release ledger reader")
        return snapshot

    advisor._load_or_reconciliation_ledger_locked = pause_after_read
    read_errors: list[Exception] = []

    def read_snapshot():
        try:
            advisor._read_or_ledger_snapshot(day)
        except Exception as exc:
            read_errors.append(exc)

    reader = threading.Thread(
        name="stale-or-ledger-reader",
        target=read_snapshot,
    )
    reader.start()
    try:
        assert loaded.wait(timeout=5)
        with advisor._lock:
            advisor._rp2_session_dates["NIFTY"] = next_day
            advisor._reset_rp2_state_for_session_locked("NIFTY", next_day)
            advisor.or_bounds["NIFTY"] = {"high": 26_101.0, "low": 25_901.0}
            advisor.or_evidence["NIFTY"] = {
                "session_date": next_day.isoformat(), "status": "PARTIAL",
                "source": "UPSTOX_TICK_PARTIAL", "source_timestamp_ms": event_ms + 1,
                "available_at_ms": event_ms + 2,
            }
            advisor.or_reconcile_retry_count["NIFTY"] = 0
            advisor.or_last_reconcile_attempt_ms["NIFTY"] = 0
            advisor._or_last_ledger_check_ms["NIFTY"] = 0
            advisor.active_range_high = 26_101.0
            advisor.active_range_low = 25_901.0
        before = (
            dict(advisor.or_bounds["NIFTY"]),
            dict(advisor.or_evidence["NIFTY"]),
            advisor.or_reconcile_retry_count["NIFTY"],
            advisor.or_last_reconcile_attempt_ms["NIFTY"],
            advisor._or_last_ledger_check_ms["NIFTY"],
            advisor.active_range_high,
            advisor.active_range_low,
            advisor._rp2_session_dates["NIFTY"],
        )
    finally:
        release_read.set()
        reader.join(timeout=5)
    assert not reader.is_alive()
    assert len(read_errors) == 1
    assert isinstance(read_errors[0], RuntimeError)
    assert "invalidated before in-memory apply" in str(read_errors[0])
    after = (
        dict(advisor.or_bounds["NIFTY"]),
        dict(advisor.or_evidence["NIFTY"]),
        advisor.or_reconcile_retry_count["NIFTY"],
        advisor.or_last_reconcile_attempt_ms["NIFTY"],
        advisor._or_last_ledger_check_ms["NIFTY"],
        advisor.active_range_high,
        advisor.active_range_low,
        advisor._rp2_session_dates["NIFTY"],
    )
    assert after == before


def test_reservation_commit_winning_shutdown_prevents_following_http(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    event_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, event_ms)
    advisor = _new_advisor(tmp_path, "reservation-before-shutdown")
    advisor.session_clock = lambda: datetime.fromtimestamp(
        event_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
    )
    advisor._or_reconciliation_loaded_session_day = day
    context = ("request-reservation-wins", day, dict(advisor._or_generation))
    with advisor._or_request_lock:
        advisor._or_outstanding_request = context
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "offline-reservation-fence-token")

    class CountingHTTP:
        def __init__(self):
            self.get_calls = 0

        def get(self, *args, **kwargs):
            self.get_calls += 1
            raise AssertionError("stale request reached HTTP")

    client = CountingHTTP()
    advisor._http_client = client
    write_entered = threading.Event()
    release_write = threading.Event()
    shutdown_lock_attempted = threading.Event()
    original_write = advisor._write_or_reconciliation_ledger_locked

    class ObservedRequestLock:
        def __init__(self):
            self.inner = threading.Lock()

        def acquire(self, *args, **kwargs):
            if threading.current_thread().name == "shutdown-after-reservation":
                shutdown_lock_attempted.set()
            return self.inner.acquire(*args, **kwargs)

        def release(self):
            return self.inner.release()

        def locked(self):
            return self.inner.locked()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, exc_type, exc, tb):
            self.release()

    advisor._or_request_lock = ObservedRequestLock()

    def blocked_reservation_write(ledger):
        state = ledger["indices"]["NIFTY"]
        if state.get("attempt_count") == 1:
            write_entered.set()
            assert release_write.wait(timeout=5)
        return original_write(ledger)

    advisor._write_or_reconciliation_ledger_locked = blocked_reservation_write
    reconcile_result = []
    reconcile_thread = threading.Thread(target=lambda: reconcile_result.append(
        advisor._seed_or_bounds_from_api_serialized(
            session_day=day, current_time_ms=event_ms, force=True,
            _request_context=context,
        )
    ))
    reconcile_thread.start()
    shutdown_done = threading.Event()
    shutdown_thread = threading.Thread(
        name="shutdown-after-reservation",
        target=lambda: (advisor.shutdown_or_reconciliation_worker(), shutdown_done.set()),
    )
    try:
        assert write_entered.wait(timeout=5)
        shutdown_thread.start()
        assert shutdown_lock_attempted.wait(timeout=5)
        assert not shutdown_done.wait(timeout=0.05)
    finally:
        release_write.set()
        reconcile_thread.join(timeout=5)
        if shutdown_thread.ident is not None:
            shutdown_thread.join(timeout=5)
    assert not reconcile_thread.is_alive() and not shutdown_thread.is_alive()
    assert shutdown_done.is_set()
    assert client.get_calls == 0
    ledger = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert ledger["indices"]["NIFTY"]["attempt_count"] == 1
