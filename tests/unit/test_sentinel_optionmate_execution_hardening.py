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
import threading
import time
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo
from typing import Optional
import pytest

from core import sentinel_live_stream_advisor as advisor_module
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    CachedRBFNAuctionSignal,
    is_mode_5_structural_breakout,
    is_mode_5_exhaustion_fade,
    mode5_rp_exhaustion_displacement,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.upstox_stream_broadcaster import UpstoxLevel5DepthRecord
from core.sentinel_realtime_journal import SentinelRealtimeJournal
from strategies.optionmate_rbfn_strategy import OptionMateGrid


def _join_queue_bounded(task_queue, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while task_queue.unfinished_tasks:
        if time.monotonic() >= deadline:
            raise AssertionError(f"advisor queue did not drain within {timeout}s")
        time.sleep(0.01)


@pytest.fixture(autouse=True)
def isolate_default_mode5_trace_file(tmp_path: Path, monkeypatch, request):
    """Isolate advisor artifacts, deny default HTTP, and close every owned worker/handle."""
    original_init = SentinelLiveStreamAdvisor.__init__
    advisors = []

    class FailFastHTTP:
        def get(self, *args, **kwargs):
            raise AssertionError("advisor test attempted unmocked HTTP")

    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)

    def isolated_init(self, *args, **kwargs):
        advisor_index = len(advisors)
        if kwargs.get("wal_path") is None:
            kwargs["wal_path"] = str(tmp_path / f"default-wal-{advisor_index}.json")
        if kwargs.get("or_reconciliation_state_path") is None:
            kwargs["or_reconciliation_state_path"] = str(
                tmp_path / f"default-or-ledger-{advisor_index}.json"
            )
        if kwargs.get("http_client") is None:
            kwargs["http_client"] = FailFastHTTP()
        supplied_journal = kwargs.get("journal")
        if supplied_journal is None:
            supplied_journal = SentinelRealtimeJournal(
                logs_dir=tmp_path / f"journal-{advisor_index}",
                enable_writer_thread=False,
            )
            kwargs["journal"] = supplied_journal
        original_init(self, *args, **kwargs)
        retained_journals = []
        for journal in (supplied_journal, getattr(self, "journal", None)):
            if journal is not None and all(journal is not existing for existing in retained_journals):
                retained_journals.append(journal)
        advisors.append((self, retained_journals))
        if self.decision_trace_path == Path("runtime") / "sentinel_decision_trace.jsonl":
            self.decision_trace_path = tmp_path / f"decision-trace-{id(self)}.jsonl"

    monkeypatch.setattr(SentinelLiveStreamAdvisor, "__init__", isolated_init)

    def close_test_writers():
        cleanup_errors = []

        def attempt(label, cleanup):
            try:
                cleanup()
            except BaseException as exc:
                cleanup_errors.append(f"{label}: {type(exc).__name__}: {exc}")

        for advisor, retained_journals in reversed(advisors):
            attempt("OR worker shutdown", advisor.shutdown_or_reconciliation_worker)
            attempt("OR queue drain", lambda: _join_queue_bounded(advisor._or_request_queue))
            attempt("OR worker join", lambda: advisor._or_worker_thread.join(timeout=3.0))
            attempt(
                "OR worker termination check",
                lambda: (_ for _ in ()).throw(AssertionError("OR worker remains alive"))
                if advisor._or_worker_thread.is_alive() else None,
            )
            attempt(
                "trace writer shutdown",
                lambda: advisor.shutdown_mode5_trace_writer(timeout_sec=2.0),
            )
            attempt(
                "trace writer termination check",
                lambda: (_ for _ in ()).throw(AssertionError("trace writer remains alive"))
                if advisor._mode5_trace_writer.is_alive() else None,
            )
            attempt(
                "trace writer atexit check",
                lambda: (_ for _ in ()).throw(AssertionError("trace writer atexit hook remains"))
                if advisor._mode5_trace_atexit_callback is not None else None,
            )
            for manager in advisor.apms.values():
                attempt(f"APM close {getattr(manager, 'index_name', 'unknown')}", manager.close)
            current_journal = getattr(advisor, "journal", None)
            if current_journal is not None and all(
                current_journal is not journal for journal in retained_journals
            ):
                retained_journals.append(current_journal)
            for journal_index, journal in enumerate(retained_journals):
                close_journal = getattr(journal, "close", None)
                if callable(close_journal):
                    attempt(f"journal close {journal_index}", close_journal)
        if cleanup_errors:
            raise AssertionError("advisor fixture cleanup failures: " + "; ".join(cleanup_errors))

    request.addfinalizer(close_test_writers)


def _test_bar_epoch(bar_time: dt_time) -> int:
    """Return the epoch bucket for a completed five-minute bar on a fixed past IST day."""
    bar_start = datetime.combine(date(2026, 11, 17), bar_time, tzinfo=ZoneInfo("Asia/Kolkata")) - timedelta(minutes=5)
    return int(bar_start.timestamp() // 300)


def _test_bar_event_ms(bar_time: dt_time) -> int:
    """Use the last in-bucket exchange millisecond, before its close boundary."""
    return (_test_bar_epoch(bar_time) + 1) * 300_000 - 1


def _test_bar_decision_available_ms(bar_time: dt_time) -> int:
    """Test-only receipt clock one millisecond after the completed bar boundary."""
    return (_test_bar_epoch(bar_time) + 1) * 300_000 + 1


def _seed_test_or_pair(advisor, index_name: str, bar_time: dt_time) -> None:
    """Seed causal local OR evidence for tests exercising non-OR strategy behavior."""
    session_day = date(2026, 11, 17)
    ist = ZoneInfo("Asia/Kolkata")
    # This fixture supplies its own explicit test evidence. Freeze reconciliation
    # so historical tests cannot try to recover a live/current-session ledger.
    advisor.or_reconciliation_frozen = True
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
            # Test-only local decision availability clock; never inferred from
            # the source event timestamp above.
            "available_at_ms": int(datetime.combine(session_day, bar_time, tzinfo=ist).timestamp() * 1000) - 1,
            "coverage_count": 30 if complete else 0,
            "coverage_start_ms": int(start.timestamp() * 1000) if complete else 0,
            "coverage_end_ms": int(datetime.combine(session_day, dt_time(9, 44), tzinfo=ist).timestamp() * 1000) if complete else 0,
        }


def _seed_rp1_reversal_case(advisor, tmp_path: Path, side: str) -> None:
    """Seed a frozen test grid and two prior completed bars for RP1 reversal checks."""
    session_day = date(2026, 11, 17)
    advisor.decision_trace_path = tmp_path / f"rp1_{side}_trace.jsonl"
    _seed_test_or_pair(advisor, "NIFTY", dt_time(12, 10))
    advisor.or_reconciliation_frozen = True
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24500.0
    advisor.cached_rbfn_grids["NIFTY"] = OptionMateGrid(
        date=session_day.isoformat(),
        spot_open=24500.0,
        trend_decider=24500.0,
        rp1_upper=24600.0,
        rp2_upper=24700.0,
        rp1_lower=24400.0,
        rp2_lower=24300.0,
        call_strike=24700.0,
        put_strike=24300.0,
        recommended_bias="RANGE",
        target_strike=24700.0,
    )
    advisor.rbfn_grids_frozen["NIFTY"] = True
    prior_epochs = _test_bar_epoch(dt_time(12, 10)) - 2
    if side == "lower":
        advisor.bars_5m_strategy_history["NIFTY"] = [
            {"open": 24420.0, "high": 24430.0, "low": 24390.0, "close": 24410.0,
             "volume": 1000, "time": dt_time(12, 0), "timestamp_ms": 0, "epoch_5min": prior_epochs},
            {"open": 24420.0, "high": 24435.0, "low": 24410.0, "close": 24430.0,
             "volume": 1000, "time": dt_time(12, 5), "timestamp_ms": 0, "epoch_5min": prior_epochs + 1},
        ]
    else:
        advisor.bars_5m_strategy_history["NIFTY"] = [
            {"open": 24580.0, "high": 24610.0, "low": 24570.0, "close": 24580.0,
             "volume": 1000, "time": dt_time(12, 0), "timestamp_ms": 0, "epoch_5min": prior_epochs},
            {"open": 24580.0, "high": 24590.0, "low": 24565.0, "close": 24570.0,
             "volume": 1000, "time": dt_time(12, 5), "timestamp_ms": 0, "epoch_5min": prior_epochs + 1},
        ]


def _evaluate_rp1_reversal(advisor, side: str, open_price: float, close_price: float):
    bar_time = dt_time(12, 10)
    epoch_5min = _test_bar_epoch(bar_time)
    timestamp_ms = (epoch_5min + 1) * 300_000 - 1
    return advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=open_price,
        bar_high=max(open_price, close_price) + 5.0,
        bar_low=min(open_price, close_price) - 5.0,
        bar_close=close_price,
        bar_volume=1000.0,
        bar_time=bar_time,
        timestamp_ms=timestamp_ms,
        epoch_5min=epoch_5min,
        decision_available_at_ms=(epoch_5min + 1) * 300_000 + 1,
    )


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


def test_mode5_gate_2_friction_is_diagnostic_at_50_and_70_pts(tmp_path: Path):
    """Mode5 records inherited Gate 2 friction without changing RBFN signal authority."""
    wal = tmp_path / "test_wal_gate2.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    # 1. Under-hurdle: the inherited overlay would veto, but must not own Mode5.
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
        timestamp_ms=_test_bar_event_ms(dt_time(9, 20)),
        epoch_5min=_test_bar_epoch(dt_time(9, 20)),
        decision_available_at_ms=_test_bar_decision_available_ms(dt_time(9, 20)),
    )
    assert sig_vetoed is not None
    assert sig_vetoed.action in {"BUY_CALL", "BUY_PUT"}
    assert sig_vetoed.is_active is True
    assert sig_vetoed.is_vetoed is False
    assert advisor._mode5_bar_policy_observations["NIFTY"]["gate2"]["atr_frictional_hurdle"]["would_veto"] is True

    # 2. At 70 points, the signal remains active and the diagnostic says no veto.
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
        timestamp_ms=_test_bar_event_ms(dt_time(9, 20)),
        epoch_5min=_test_bar_epoch(dt_time(9, 20)),
        decision_available_at_ms=_test_bar_decision_available_ms(dt_time(9, 20)),
    )
    assert sig_passed is not None
    assert sig_passed.is_active is True
    assert sig_passed.is_vetoed is False
    assert sig_passed.action in {"BUY_CALL", "BUY_PUT"}
    assert advisor2._mode5_bar_policy_observations["NIFTY"]["gate2"]["atr_frictional_hurdle"]["would_veto"] is False


def test_1030_rp2_piercing_uncoupled_from_exhaustion_fade(tmp_path: Path):
    """Early morning RP2 touch does not block S5 ceiling fade or S7 floor bounce."""
    wal = tmp_path / "test_wal_uncouple.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "rp2_fade_trace.jsonl"
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
        timestamp_ms=_test_bar_event_ms(dt_time(10, 15)),
        epoch_5min=_test_bar_epoch(dt_time(10, 15)),
        decision_available_at_ms=_test_bar_decision_available_ms(dt_time(10, 15)),
    )
    assert advisor.rp2_pierced_before_1030["NIFTY"] is True

    # Preserve the early piercing state, then establish a fresh 11:25 touch.
    # The 11:30 and 11:35 completed bars are the two contiguous post-touch holds.
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24230.0,
        bar_high=24250.0,
        bar_low=24220.0,
        bar_close=24230.0,
        bar_volume=40000.0,
        bar_time=dt_time(11, 25),
        timestamp_ms=_test_bar_event_ms(dt_time(11, 25)),
        epoch_5min=_test_bar_epoch(dt_time(11, 25)),
        decision_available_at_ms=_test_bar_decision_available_ms(dt_time(11, 25)),
    )

    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24230.0,
        bar_high=24235.0,
        bar_low=24210.0,
        bar_close=24215.0,
        bar_volume=40000.0,
        bar_time=dt_time(11, 30),
        timestamp_ms=_test_bar_event_ms(dt_time(11, 30)),
        epoch_5min=_test_bar_epoch(dt_time(11, 30)),
        decision_available_at_ms=_test_bar_decision_available_ms(dt_time(11, 30)),
    )
    sig_fade = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24215.0,
        bar_high=24220.0,
        bar_low=24200.0,
        bar_close=24205.0,
        bar_volume=45000.0,
        bar_time=dt_time(11, 35),
        timestamp_ms=_test_bar_event_ms(dt_time(11, 35)),
        epoch_5min=_test_bar_epoch(dt_time(11, 35)),
        decision_available_at_ms=_test_bar_decision_available_ms(dt_time(11, 35)),
    )

    # S5 ceiling fade must NOT be vetoed by 10:30 RP2 piercing!
    assert sig_fade is not None
    assert sig_fade.action == "BUY_PUT"
    assert sig_fade.setup_reason == "RP2_UPPER_10M_CEILING_FADE"
    assert sig_fade.triggering_reference_price == advisor.cached_rbfn_grids["NIFTY"].rp2_upper
    assert sig_fade.is_active is True
    assert sig_fade.is_vetoed is False


@pytest.mark.parametrize(
    ("side", "variant", "expected_reason", "reference_field"),
    [
        ("upper", "fast", "RP2_UPPER_FAST_REJECTION", "rp2_upper"),
        ("upper", "10m", "RP2_UPPER_10M_CEILING_FADE", "rp2_upper"),
        ("lower", "fast", "RP2_LOWER_FAST_BOUNCE", "rp2_lower"),
        ("lower", "10m", "RP2_LOWER_10M_FLOOR_BOUNCE", "rp2_lower"),
    ],
)
def test_rp2_fade_producers_snapshot_their_triggering_boundary(
    tmp_path: Path, side: str, variant: str, expected_reason: str, reference_field: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"rp2-{side}-{variant}.json"), enable_stdout=False
    )
    _seed_test_or_pair(advisor, "NIFTY", dt_time(11, 25))
    advisor.or_reconciliation_frozen = True
    advisor.seed_prior_day_levels("NIFTY", pdh=24300.0, pdl=23700.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0
    grid = OptionMateGrid(
        date="2026-11-17",
        spot_open=24000.0,
        trend_decider=24000.0,
        rp1_upper=24120.0,
        rp2_upper=24240.0,
        rp1_lower=23880.0,
        rp2_lower=23760.0,
        call_strike=24200.0,
        put_strike=23800.0,
        recommended_bias="RANGE",
        target_strike=24000.0,
    )
    advisor.cached_rbfn_grids["NIFTY"] = grid
    advisor.rbfn_grids_frozen["NIFTY"] = True

    def evaluate(bar_time: dt_time, open_price: float, high: float, low: float, close: float):
        epoch_5min = _test_bar_epoch(bar_time)
        timestamp_ms = (epoch_5min + 1) * 300_000 - 1
        return advisor._on_5m_bar_close(
            index_name="NIFTY",
            bar_open=open_price,
            bar_high=high,
            bar_low=low,
            bar_close=close,
            bar_volume=45000.0,
            bar_time=bar_time,
            timestamp_ms=timestamp_ms,
            epoch_5min=epoch_5min,
                decision_available_at_ms=(epoch_5min + 1) * 300_000 + 1,
        )

    if variant == "fast":
        current_epoch = _test_bar_epoch(dt_time(11, 25))
        advisor._rp2_session_dates["NIFTY"] = date(2026, 11, 17)
        advisor.bars_5m_strategy_history["NIFTY"] = [
            {
                "open": 24000.0, "high": 24020.0, "low": 23980.0, "close": 24000.0,
                "volume": 45000.0, "time": dt_time(11, 15), "timestamp_ms": (current_epoch - 2) * 300_000,
                "epoch_5min": current_epoch - 2,
            },
            {
                "open": 24000.0, "high": 24020.0, "low": 23980.0, "close": 24000.0,
                "volume": 45000.0, "time": dt_time(11, 20), "timestamp_ms": (current_epoch - 1) * 300_000,
                "epoch_5min": current_epoch - 1,
            },
        ]
        advisor._last_completed_5m_epoch["NIFTY"] = current_epoch - 1
        advisor._last_5m_timestamp_ms["NIFTY"] = (current_epoch - 1) * 300_000
        if side == "upper":
            signal = evaluate(dt_time(11, 25), 24240.0, 24270.0, 24190.0, 24225.0)
        else:
            signal = evaluate(dt_time(11, 25), 23770.0, 23850.0, 23730.0, 23775.0)
    elif side == "upper":
        evaluate(dt_time(11, 25), 24220.0, 24250.0, 24180.0, 24235.0)
        evaluate(dt_time(11, 30), 24230.0, 24235.0, 24190.0, 24235.0)
        signal = evaluate(dt_time(11, 35), 24230.0, 24235.0, 24190.0, 24235.0)
    else:
        evaluate(dt_time(11, 25), 23780.0, 23840.0, 23750.0, 23765.0)
        evaluate(dt_time(11, 30), 23770.0, 23810.0, 23765.0, 23765.0)
        signal = evaluate(dt_time(11, 35), 23770.0, 23810.0, 23765.0, 23765.0)

    assert signal is not None
    assert signal.setup_reason == expected_reason
    assert signal.triggering_reference_price == getattr(grid, reference_field)


@pytest.mark.parametrize(
    ("side", "open_price", "close_price", "expected_reason"),
    [
        ("lower", 24460.0, 24450.0, None),  # bearish candle cannot confirm CE
        ("lower", 24450.0, 24450.0, None),  # doji has no bullish trade direction
        ("lower", 24440.0, 24450.0, "RP1_LOWER_REVERSAL_CONFIRMED"),
        ("upper", 24520.0, 24530.0, None),  # bullish candle cannot confirm PE
        ("upper", 24550.0, 24550.0, None),  # doji has no bearish trade direction
        ("upper", 24540.0, 24530.0, "RP1_UPPER_REVERSAL_CONFIRMED"),
    ],
)
def test_rp1_reversal_requires_current_bar_direction(
    tmp_path: Path, side: str, open_price: float, close_price: float, expected_reason: str | None
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"rp1_{side}_{open_price}.json"), enable_stdout=False
    )
    _seed_rp1_reversal_case(advisor, tmp_path, side)

    signal = _evaluate_rp1_reversal(advisor, side, open_price, close_price)

    if expected_reason is None:
        assert signal is not None
        assert signal.setup_reason != (
            "RP1_LOWER_REVERSAL_CONFIRMED" if side == "lower"
            else "RP1_UPPER_REVERSAL_CONFIRMED"
        )
    else:
        assert signal is not None
        assert signal.setup_reason == expected_reason
        expected_reference = advisor.cached_rbfn_grids["NIFTY"].rp1_lower if side == "lower" else advisor.cached_rbfn_grids["NIFTY"].rp1_upper
        assert signal.triggering_reference_price == expected_reference


def test_mode5_bar_signal_is_independent_of_target_and_companion_or_availability(
    tmp_path: Path,
):
    results = []
    for or_state in ("VALID", "TARGET_UNAVAILABLE", "COMPANION_UNAVAILABLE", "BOTH_UNAVAILABLE"):
        advisor = SentinelLiveStreamAdvisor(
            wal_path=str(tmp_path / f"bar-or-diagnostic-{or_state}.json"),
            enable_stdout=False,
        )
        _seed_rp1_reversal_case(advisor, tmp_path, "lower")
        if or_state in {"TARGET_UNAVAILABLE", "BOTH_UNAVAILABLE"}:
            advisor.or_evidence["NIFTY"]["available_at_ms"] = None
        if or_state in {"COMPANION_UNAVAILABLE", "BOTH_UNAVAILABLE"}:
            advisor.or_evidence["SENSEX"]["status"] = "PENDING_RECONCILIATION"
            advisor.or_evidence["SENSEX"]["available_at_ms"] = None

        signal = _evaluate_rp1_reversal(
            advisor, "lower", open_price=24440.0, close_price=24450.0
        )
        assert signal is not None
        records = _read_mode5_trace_records(advisor)
        records = [row for row in records if row.get("trace_run_id") == advisor.trace_run_id]
        matching = [row for row in records if row.get("reason") == signal.setup_reason]
        assert matching
        or_validation = matching[-1]["details"]["or_validation"]
        assert or_validation["decision_authority"] == "DIAGNOSTIC_ONLY"
        assert or_validation["reason"].startswith(
            "MODE5_TARGET_OR_VALID" if or_state in {"VALID", "COMPANION_UNAVAILABLE"}
            else "MODE5_TARGET_OR_AVAILABILITY_UNPROVEN"
        )
        results.append((signal.action, signal.setup_reason, signal.target_pts, signal.sl_pts))
        advisor.shutdown_mode5_trace_writer(timeout_sec=2)

    assert len(set(results)) == 1


@pytest.mark.parametrize("side", ["upper", "lower"])
def test_rp1_reversal_does_not_join_confirmation_across_missing_five_minute_bar(
    tmp_path: Path, side: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"rp1-gap-{side}.json"), enable_stdout=False
    )
    _seed_rp1_reversal_case(advisor, tmp_path, side)
    current_epoch = _test_bar_epoch(dt_time(12, 10))
    history = advisor.bars_5m_strategy_history["NIFTY"]
    assert len(history) >= 2
    history[-2]["epoch_5min"] = current_epoch - 3
    history[-1]["epoch_5min"] = current_epoch - 2  # distinct E-3, E-2; E-1 is absent

    signal = _evaluate_rp1_reversal(
        advisor, side, open_price=24440.0 if side == "lower" else 24540.0,
        close_price=24450.0 if side == "lower" else 24530.0,
    )

    expected = "RP1_LOWER_REVERSAL_CONFIRMED" if side == "lower" else "RP1_UPPER_REVERSAL_CONFIRMED"
    assert signal is not None
    assert signal.setup_reason != expected


def test_mode5_epoch_adjacency_helper_requires_exact_two_and_three_bar_windows():
    two = [{"epoch_5min": 100}, {"epoch_5min": 101}]
    three = [{"epoch_5min": 100}, {"epoch_5min": 101}, {"epoch_5min": 102}]
    assert SentinelLiveStreamAdvisor._has_consecutive_bar_epochs(two, 2) is True
    assert SentinelLiveStreamAdvisor._has_consecutive_bar_epochs(three, 3) is True
    assert SentinelLiveStreamAdvisor._has_consecutive_bar_epochs(
        [{"epoch_5min": 100}, {"epoch_5min": 102}], 2
    ) is False
    assert SentinelLiveStreamAdvisor._has_consecutive_bar_epochs(
        [{"epoch_5min": 100}, {"epoch_5min": 102}, {"epoch_5min": 103}], 3
    ) is False
    assert SentinelLiveStreamAdvisor._has_consecutive_bar_epochs(
        [{"epoch_5min": 100}, {"epoch_5min": True}], 2
    ) is False
    assert SentinelLiveStreamAdvisor._has_consecutive_bar_epochs(
        [{"epoch_5min": True}, {"epoch_5min": 2}], 2
    ) is False


def test_rp1_upper_expansion_producer_snapshots_frozen_rp1_boundary(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "rp1-upper-expansion.json"), enable_stdout=False
    )
    bar_time = dt_time(11, 35)
    _seed_test_or_pair(advisor, "NIFTY", bar_time)
    advisor.or_reconciliation_frozen = True
    advisor.seed_prior_day_levels("NIFTY", pdh=25700.0, pdl=25000.0, pdc=25350.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 25370.0
    grid = OptionMateGrid(
        date="2026-11-17",
        spot_open=25370.0,
        trend_decider=25370.0,
        rp1_upper=25575.0,
        rp2_upper=25770.0,
        rp1_lower=25160.0,
        rp2_lower=25052.0,
        call_strike=25600.0,
        put_strike=25100.0,
        recommended_bias="CALL",
        target_strike=25600.0,
    )
    advisor.cached_rbfn_grids["NIFTY"] = grid
    advisor.rbfn_grids_frozen["NIFTY"] = True
    prior_epoch = _test_bar_epoch(dt_time(11, 30))
    advisor._rp2_session_dates["NIFTY"] = date(2026, 11, 17)
    advisor.bars_5m_strategy_history["NIFTY"] = [
        {
            "open": 25570.0,
            "high": 25595.0,
            "low": 25560.0,
            "close": 25580.0,
            "volume": 1000.0,
            "time": dt_time(11, 25),
            "timestamp_ms": (prior_epoch - 1) * 300_000,
            "epoch_5min": prior_epoch - 1,
        },
        {
            "open": 25580.0,
            "high": 25605.0,
            "low": 25575.0,
            "close": 25590.0,
            "volume": 1000.0,
            "time": dt_time(11, 30),
            "timestamp_ms": prior_epoch * 300_000,
            "epoch_5min": prior_epoch,
        },
    ]
    advisor._last_completed_5m_epoch["NIFTY"] = prior_epoch
    advisor._last_5m_timestamp_ms["NIFTY"] = prior_epoch * 300_000

    epoch_5min = _test_bar_epoch(bar_time)
    timestamp_ms = (epoch_5min + 1) * 300_000 - 1
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25600.0,
        bar_high=25640.0,
        bar_low=25595.0,
        bar_close=25618.8,
        bar_volume=1000.0,
        bar_time=bar_time,
        timestamp_ms=timestamp_ms,
        epoch_5min=epoch_5min,
        decision_available_at_ms=(epoch_5min + 1) * 300_000 + 1,
    )

    assert signal is not None
    assert signal.setup_reason == "RP1_UPPER_10M_EXPANSION_BREAKOUT"
    assert signal.triggering_reference_price == grid.rp1_upper


def test_rp1_lower_expansion_producer_snapshots_frozen_rp1_boundary(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "rp1-lower-expansion.json"), enable_stdout=False
    )
    bar_time = dt_time(11, 35)
    _seed_test_or_pair(advisor, "NIFTY", bar_time)
    advisor.or_reconciliation_frozen = True
    advisor.seed_prior_day_levels("NIFTY", pdh=25700.0, pdl=25000.0, pdc=25350.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 25370.0
    grid = OptionMateGrid(
        date="2026-11-17",
        spot_open=25370.0,
        trend_decider=25370.0,
        rp1_upper=25575.0,
        rp2_upper=25770.0,
        rp1_lower=25160.0,
        rp2_lower=25052.0,
        call_strike=25600.0,
        put_strike=25100.0,
        recommended_bias="PUT",
        target_strike=25100.0,
    )
    advisor.cached_rbfn_grids["NIFTY"] = grid
    advisor.rbfn_grids_frozen["NIFTY"] = True
    prior_epoch = _test_bar_epoch(dt_time(11, 30))
    advisor._rp2_session_dates["NIFTY"] = date(2026, 11, 17)
    advisor.bars_5m_strategy_history["NIFTY"] = [
        {
            "open": 25170.0,
            "high": 25180.0,
            "low": 25140.0,
            "close": 25155.0,
            "volume": 1000.0,
            "time": dt_time(11, 25),
            "timestamp_ms": (prior_epoch - 1) * 300_000,
            "epoch_5min": prior_epoch - 1,
        },
        {
            "open": 25155.0,
            "high": 25165.0,
            "low": 25130.0,
            "close": 25150.0,
            "volume": 1000.0,
            "time": dt_time(11, 30),
            "timestamp_ms": prior_epoch * 300_000,
            "epoch_5min": prior_epoch,
        },
    ]
    advisor._last_completed_5m_epoch["NIFTY"] = prior_epoch
    advisor._last_5m_timestamp_ms["NIFTY"] = prior_epoch * 300_000

    epoch_5min = _test_bar_epoch(bar_time)
    timestamp_ms = (epoch_5min + 1) * 300_000 - 1
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25150.0,
        bar_high=25160.0,
        bar_low=25120.0,
        bar_close=25140.0,
        bar_volume=1000.0,
        bar_time=bar_time,
        timestamp_ms=timestamp_ms,
        epoch_5min=epoch_5min,
        decision_available_at_ms=(epoch_5min + 1) * 300_000 + 1,
    )

    assert signal is not None
    assert signal.setup_reason == "RP1_LOWER_10M_EXPANSION_BREAKDOWN"
    assert signal.trade_phase == "MIDDAY_EXPANSION_BREAKDOWN"
    assert signal.action == "BUY_PUT"
    assert signal.triggering_reference_price == grid.rp1_lower


def _make_dummy_depth(
    token: str = "NSE_FO|45408",
    symbol: str = "NIFTY 25400 CE",
    ltp: float = 25.0,
    oi: int = 500000,
    ts_ms: int = 1793196900000,
    ingress_ns: int = 1000000,
    sequence_id: int = 1,
    ingress_wall_utc: str = "2026-11-17T11:35:00Z",
) -> UpstoxLevel5DepthRecord:
    """Helper to produce a valid Upstox Level-5 depth record."""
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=ingress_ns,
        ingress_wall_utc=ingress_wall_utc,
        sequence_id=sequence_id,
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


@pytest.mark.parametrize(
    "setup_reason,reference",
    [
        ("RP2_UPPER_10M_CEILING_FADE", 25000.0),
        ("RP2_LOWER_10M_FLOOR_BOUNCE", 24000.0),
        ("RP2_UPPER_FAST_REJECTION", 25000.0),
        ("RP2_LOWER_FAST_BOUNCE", 24000.0),
        ("RP1_UPPER_REVERSAL_CONFIRMED", 24800.0),
        ("RP1_LOWER_REVERSAL_CONFIRMED", 24200.0),
    ],
)
def test_mode5_rp_fade_uses_frozen_trigger_boundary(setup_reason, reference):
    displacement, reason = mode5_rp_exhaustion_displacement(
        setup_reason, reference, spot=reference + 17.5, fallback_displacement=900.0
    )
    assert displacement == 17.5
    assert reason is None


@pytest.mark.parametrize(
    ("setup_reason", "reference", "spot", "expected_displacement"),
    [
        ("RP1_UPPER_10M_EXPANSION_BREAKOUT", 25575.0, 25618.8, 43.8),
        ("RP1_LOWER_10M_EXPANSION_BREAKDOWN", 25160.0, 25116.2, 43.8),
    ],
)
def test_mode5_rp1_expansions_use_their_frozen_trigger_boundary(
    setup_reason: str, reference: float, spot: float, expected_displacement: float
):
    displacement, reason = mode5_rp_exhaustion_displacement(
        setup_reason,
        reference,
        spot=spot,
        fallback_displacement=248.8,
    )
    assert displacement == pytest.approx(expected_displacement)
    assert reason is None


def test_mode5_rp_fade_boundary_snapshot_survives_grid_replacement(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "rp-snapshot.json"), enable_stdout=False)
    original_grid = OptionMateGrid(
        date="2026-11-17",
        spot_open=24500.0,
        trend_decider=24500.0,
        rp1_upper=24800.0,
        rp2_upper=25000.0,
        rp1_lower=24200.0,
        rp2_lower=24000.0,
        call_strike=25000.0,
        put_strike=24000.0,
        recommended_bias="RANGE",
        target_strike=24500.0,
    )
    replacement_grid = OptionMateGrid(
        date="2026-11-17",
        spot_open=24500.0,
        trend_decider=24600.0,
        rp1_upper=24900.0,
        rp2_upper=25100.0,
        rp1_lower=24100.0,
        rp2_lower=23900.0,
        call_strike=25100.0,
        put_strike=23900.0,
        recommended_bias="RANGE",
        target_strike=24600.0,
    )
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=1793196900000,
        index_name="NIFTY",
        action="BUY_PUT",
        direction="PE",
        target_strike=24500.0,
        target_pts=20.0,
        sl_pts=15.0,
        setup_reason="RP2_UPPER_FAST_REJECTION",
        trade_phase="EXTREME_EXHAUSTION_REVERSAL",
        bar_time=dt_time(11, 35),
        triggering_reference_price=original_grid.rp2_upper,
    )
    advisor.cached_rbfn_grids["NIFTY"] = original_grid
    advisor.cached_rbfn_signals["NIFTY"] = signal
    advisor.cached_rbfn_grids["NIFTY"] = replacement_grid

    displacement, reason = mode5_rp_exhaustion_displacement(
        signal.setup_reason,
        signal.triggering_reference_price,
        spot=25020.0,
        fallback_displacement=700.0,
    )

    assert displacement == 20.0
    assert reason is None
    with pytest.raises((AttributeError, TypeError)):
        signal.triggering_reference_price = replacement_grid.rp2_upper


@pytest.mark.parametrize("bad_reference", [None, 0.0, -1.0, math.nan, math.inf, -math.inf])
def test_mode5_known_rp_fade_missing_or_nonfinite_boundary_fails_closed(bad_reference):
    displacement, reason = mode5_rp_exhaustion_displacement(
        "RP1_LOWER_REVERSAL_CONFIRMED",
        bad_reference,
        spot=24400.0,
        fallback_displacement=10.0,
    )
    assert displacement == 10.0
    assert reason == "MISSING_RP_BOUNDARY_REFERENCE"


def test_mode5_unknown_rp_fade_fails_closed_and_unrelated_td_setup_keeps_fallback():
    unknown_displacement, unknown_reason = mode5_rp_exhaustion_displacement(
        "RP2_UPPER_NEW_FADE_FAMILY",
        25000.0,
        spot=24900.0,
        fallback_displacement=80.0,
    )
    unrelated_displacement, unrelated_reason = mode5_rp_exhaustion_displacement(
        "TD_PULLBACK_REENTRY_BEAR_CONFIRMED_2BAR",
        None,
        spot=24900.0,
        fallback_displacement=80.0,
    )

    assert (unknown_displacement, unknown_reason) == (80.0, "UNKNOWN_RP_BOUNDARY_SETUP")
    assert (unrelated_displacement, unrelated_reason) == (80.0, None)


@pytest.mark.parametrize("bad_reference", [None, 0.0, -1.0, math.nan, math.inf, -math.inf])
def test_mode5_rp1_lower_expansion_missing_or_nonfinite_boundary_fails_closed(bad_reference):
    displacement, reason = mode5_rp_exhaustion_displacement(
        "RP1_LOWER_10M_EXPANSION_BREAKDOWN",
        bad_reference,
        spot=25120.0,
        fallback_displacement=250.0,
    )
    assert displacement == 250.0
    assert reason == "MISSING_RP_BOUNDARY_REFERENCE"


def test_mode5_rp1_upper_breakout_missing_boundary_fails_closed():
    displacement, reason = mode5_rp_exhaustion_displacement(
        "RP1_UPPER_10M_EXPANSION_BREAKOUT",
        None,
        spot=25618.8,
        fallback_displacement=248.8,
    )
    assert displacement == 248.8
    assert reason == "MISSING_RP_BOUNDARY_REFERENCE"


@pytest.mark.parametrize(
    ("setup_reason", "reference", "direction"),
    [
        ("RP1_UPPER_10M_EXPANSION_BREAKOUT", 25575.0, 1.0),
        ("RP1_LOWER_10M_EXPANSION_BREAKDOWN", 25160.0, -1.0),
    ],
)
@pytest.mark.parametrize("multiple,expected_allowed", [(2.5 - 1e-6, True), (2.5, True), (2.5 + 1e-6, False)])
def test_mode5_rp1_expansion_displacement_preserves_strict_atr_threshold(
    setup_reason, reference, direction, multiple, expected_allowed
):
    atr60 = 20.0
    displacement, error = mode5_rp_exhaustion_displacement(
        setup_reason,
        reference,
        spot=reference + direction * multiple * atr60,
        fallback_displacement=700.0,
    )
    allowed, _, _ = advisor_module.VolatilityCompressionGate().evaluate_compression(
        atr_15m=25.0,
        atr_60m=atr60,
        recent_displacement_pts=displacement,
    )
    assert error is None
    assert allowed is expected_allowed


def test_cached_rbfn_signal_300s_monotonic_ttl_eviction(tmp_path: Path, monkeypatch):
    """Candidate stays valid at exactly 300s and expires only after that boundary."""
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
    clock_ns = [10_000_000_000]
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: clock_ns[0])
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", fresh_signal, base_ts_ms // 300_000)

    # Query within 100 seconds (fresh)
    clock_ns[0] += 100_000_000_000
    queried_fresh = advisor.get_valid_cached_rbfn_signal("NIFTY", ttl_seconds=300.0)
    assert queried_fresh is not None
    assert queried_fresh.setup_reason == "RP1_UPPER_10M_EXPANSION_BREAKOUT"

    # Exactly 300 seconds remains valid; the next nanosecond expires it.
    clock_ns[0] += 200_000_000_000
    queried_at_boundary = advisor.get_valid_cached_rbfn_signal("NIFTY", ttl_seconds=300.0)
    assert queried_at_boundary is not None
    clock_ns[0] += 1
    queried_expired = advisor.get_valid_cached_rbfn_signal("NIFTY", ttl_seconds=300.0)
    assert queried_expired is None
    assert advisor.cached_rbfn_signals["NIFTY"] is None


def test_mode5_quote_clock_validation_rejects_bad_source_and_ingress(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "quote-clock.json"), enable_stdout=False)
    ist = ZoneInfo("Asia/Kolkata")
    boundary = datetime(2026, 11, 18, 11, 35, 0, tzinfo=ist)
    wall_now_ms = int(boundary.timestamp() * 1000) + 500
    mono_now_ns = 10_000_000_000
    depth = _make_dummy_depth(
        ts_ms=wall_now_ms,
        ingress_ns=mono_now_ns - 100_000_000,
    )
    valid = advisor._option_quote_identity(
        "NIFTY", depth, wall_now_ms=wall_now_ms, monotonic_now_ns=mono_now_ns
    )
    assert valid[0] is True

    invalid_depths = [
        _make_dummy_depth(ts_ms=0, ingress_ns=mono_now_ns - 100_000_000),
        _make_dummy_depth(ts_ms=-1, ingress_ns=mono_now_ns - 100_000_000),
        _make_dummy_depth(ts_ms=True, ingress_ns=mono_now_ns - 100_000_000),
        _make_dummy_depth(ts_ms=wall_now_ms + 60_000, ingress_ns=mono_now_ns - 100_000_000),
        _make_dummy_depth(ts_ms=wall_now_ms - 60_000, ingress_ns=mono_now_ns - 100_000_000),
        _make_dummy_depth(ts_ms=wall_now_ms, ingress_ns=mono_now_ns - 10_000_000_000),
        _make_dummy_depth(ts_ms=wall_now_ms, ingress_ns=mono_now_ns + 1),
        _make_dummy_depth(ts_ms=wall_now_ms, ingress_ns=mono_now_ns - 100_000_000, sequence_id=0),
    ]
    for invalid in invalid_depths:
        result = advisor._option_quote_identity(
            "NIFTY", invalid, wall_now_ms=wall_now_ms, monotonic_now_ns=mono_now_ns
        )
        assert result[0] is False


def test_lagging_quote_preserves_candidate_and_boundary_quote_is_eligible(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "quote-boundary.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "quote-suppression.jsonl"
    ist = ZoneInfo("Asia/Kolkata")
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ist)
    boundary_ms = int(boundary.timestamp() * 1000)
    current_wall_ms = boundary_ms + 500
    clock_ns = [10_000_000_000]
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: clock_ns[0])
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=boundary_ms - 100,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="CE",
        target_strike=25400.0,
        target_pts=30.0,
        sl_pts=15.0,
        setup_reason="TEST_COMPLETED_BAR_CANDIDATE",
        trade_phase="MIDDAY_REVERSAL",
        bar_time=dt_time(11, 35),
        is_active=True,
    )
    epoch = (boundary_ms // 300_000) - 1
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, epoch)
    issued_ns = advisor._cached_rbfn_candidate_meta["NIFTY"].issued_monotonic_ns

    lagging = _make_dummy_depth(
        ts_ms=boundary_ms - 1,
        ingress_ns=issued_ns + 100_000_000,
    )
    quote_info = advisor._option_quote_identity(
        "NIFTY", lagging, wall_now_ms=current_wall_ms, monotonic_now_ns=issued_ns + 500_000_000
    )
    assert quote_info[0] is True
    assert advisor._record_option_depth_order("NIFTY", quote_info[2], quote_info[3], quote_info[4])
    rejected, generation = advisor._candidate_for_option_depth(
        "NIFTY", lagging, quote_info[2], quote_info[3], quote_info[4], now_ns=issued_ns + 500_000_000
    )
    assert rejected is None and generation is None
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    records = _read_mode5_trace_records(advisor)
    assert len(records) == 1
    assert records[0]["event_type"] == "MODE5_QUOTE_SUPPRESSED"
    assert records[0]["action"] == "ABSTAIN"
    assert records[0]["decision"] == "RETAIN_CANDIDATE"
    assert records[0]["reason"] == "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"
    assert records[0]["candidate_generation"] == advisor._cached_rbfn_candidate_meta["NIFTY"].generation
    assert records[0]["boundary_timestamp_ms"] == boundary_ms

    eligible = _make_dummy_depth(
        ts_ms=boundary_ms + 100,
        ingress_ns=issued_ns + 200_000_000,
        sequence_id=2,
    )
    eligible_info = advisor._option_quote_identity(
        "NIFTY", eligible, wall_now_ms=current_wall_ms, monotonic_now_ns=issued_ns + 500_000_000
    )
    assert eligible_info[0] is True
    assert advisor._record_option_depth_order("NIFTY", eligible_info[2], eligible_info[3], eligible_info[4])
    found, generation = advisor._candidate_for_option_depth(
        "NIFTY", eligible, eligible_info[2], eligible_info[3], eligible_info[4], now_ns=issued_ns + 500_000_000
    )
    assert found is signal
    assert generation == advisor._cached_rbfn_candidate_meta["NIFTY"].generation
    assert len(_read_mode5_trace_records(advisor)) == 1


def test_candidate_lookup_uses_fresh_locked_monotonic_after_prepublication_sample(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "candidate-fresh-lock-clock.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, wall_now_ms, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=106_000_000_000,
    )
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert metadata is not None
    prepublication_sample_ns = metadata.issued_monotonic_ns - 1
    current_lookup_ns = metadata.issued_monotonic_ns + 5_000_000
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: current_lookup_ns)
    quote_valid, reason, quote_day, key, source_order = advisor._option_quote_identity(
        "NIFTY", depth, wall_now_ms=wall_now_ms,
        monotonic_now_ns=depth.ingress_monotonic_ns + 1,
    )
    assert quote_valid, reason
    assert quote_day is not None and key is not None and source_order is not None
    assert advisor._record_option_depth_order("NIFTY", quote_day, key, source_order)

    candidate, found_generation = advisor._candidate_for_option_depth(
        "NIFTY", depth, quote_day, key, source_order,
        now_ns=prepublication_sample_ns,
    )

    assert candidate is signal
    assert found_generation == generation
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"


def test_mode5_research_bar_does_not_mutate_shared_runner_gears(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-gear-isolation.json"), enable_stdout=False
    )
    bar_time = dt_time(9, 20)
    timestamp_ms = _test_bar_event_ms(bar_time)
    epoch = _test_bar_epoch(bar_time)
    boundary_ms = (epoch + 1) * 300_000
    decision_ms = _test_bar_decision_available_ms(bar_time)
    monkeypatch.setattr(
        advisor_module, "_wall_clock_seconds", lambda: (decision_ms + 1) / 1000.0
    )
    day = date(2026, 11, 17)
    _seed_test_or_pair(advisor, "NIFTY", bar_time)
    assert advisor.seed_prior_day_levels(
        "NIFTY", pdh=25_300.0, pdl=24_700.0, pdc=25_000.0,
        session_date=day, atr_20=100.0,
    )
    advisor.session_gears["NIFTY"] = "GEAR_1_RANGE"
    advisor.session_gear = "GEAR_1_RANGE"
    advisor.gear_range_bar_counters["NIFTY"] = 0
    advisor.gear_trend_bar_counters["NIFTY"] = 0
    advisor.gear_expansion_ratios["NIFTY"] = 0.0

    try:
        advisor._on_5m_bar_close(
            "NIFTY", 25_000.0, 25_300.0, 24_800.0, 25_100.0, 100.0,
            bar_time, timestamp_ms, epoch,
            decision_available_at_ms=decision_ms,
        )
        assert advisor._last_completed_5m_epoch["NIFTY"] == epoch
        assert advisor.session_gears["NIFTY"] == "GEAR_1_RANGE"
        assert advisor.session_gear == "GEAR_1_RANGE"
        assert advisor.gear_range_bar_counters["NIFTY"] == 0
        assert advisor.gear_trend_bar_counters["NIFTY"] == 0
        assert advisor.gear_expansion_ratios["NIFTY"] == 0.0
    finally:
        advisor.shutdown_or_reconciliation_worker()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3.0)
        for manager in advisor.apms.values():
            manager.close()


def test_invalid_bar_nonfinite_value_is_traced_as_null_without_state_advance(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "invalid-bar-nonfinite.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / "invalid-bar-nonfinite.jsonl"
    boundary = datetime(2026, 11, 18, 9, 55, tzinfo=ZoneInfo("Asia/Kolkata"))
    timestamp_ms = int(boundary.timestamp() * 1000) - 1
    epoch = timestamp_ms // 300_000
    decision_ms = (epoch + 1) * 300_000 + 1
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: decision_ms / 1000.0)

    result = advisor._on_5m_bar_close(
        "NIFTY", math.nan, 25010.0, 24990.0, 25005.0, 100.0,
        boundary.time(), timestamp_ms, epoch,
        decision_available_at_ms=decision_ms,
    )

    assert result is None
    assert advisor.bars_5m_history.get("NIFTY", []) == []
    assert advisor._last_5m_timestamp_ms.get("NIFTY", 0) == 0
    summaries = [
        row for row in _read_mode5_trace_records(advisor)
        if row.get("event_type") == "MODE5_EVALUATION_SUMMARY"
    ]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["evaluation_state"] == "REJECTED"
    assert summary["candidate_state"] == "NOT_EMITTED"
    assert summary["reason_code"] == "INVALID_COMPLETED_BAR_OHLCV"
    assert summary["bar_ohlcv"]["open"] is None
    assert summary["bar_ohlcv"]["telemetry_sanitization"] == {
        "status": "REPLACED_WITH_NULL",
        "replaced_paths": ["or_details.open"],
    }


def _seed_quote_trace_candidate(advisor, boundary: datetime):
    boundary_ms = int(boundary.timestamp() * 1000)
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=boundary_ms - 1,
        index_name="NIFTY", action="BUY_CALL", direction="CE", target_strike=25400.0,
        target_pts=30.0, sl_pts=15.0, setup_reason="TRACE_TEST_SETUP",
        trade_phase="MIDDAY_REVERSAL", bar_time=boundary.timetz().replace(tzinfo=None), is_active=True,
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, boundary_ms // 300_000 - 1)
    return signal, advisor._cached_rbfn_candidate_meta["NIFTY"]


def _wait_for_mode5_trace_quiescent(advisor, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = advisor.get_mode5_trace_health()
        if (
            health["queue_depth"] == 0
            and health["active_writes"] == 0
            and health["pending_unpersisted"] == 0
        ):
            return health
        time.sleep(0.005)
    health = advisor.get_mode5_trace_health()
    raise AssertionError(
        "Mode5 trace writer did not become quiescent: "
        f"queue_depth={health['queue_depth']} active_writes={health['active_writes']} "
        f"pending_unpersisted={health['pending_unpersisted']} "
        f"append_failures={health['append_failures']} "
        f"queue_full_drops={health['queue_full_drops']} "
        f"oversize_drops={health['oversize_drops']} "
        f"writer_unavailable_drops={health['writer_unavailable_drops']} "
        f"last_error={health['last_error']}"
    )


def _wait_for_mode5_trace_expected_failures(
    advisor, target_sequence: int, expected_append_failures: int, timeout: float = 3.0
) -> dict:
    """Wait for one sequence and a failure count while allowing known pending failures."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = advisor.get_mode5_trace_health()
        if (
            health["queue_depth"] == 0
            and health["active_writes"] == 0
            and health["append_failures"] >= expected_append_failures
            and (health["last_processed_sequence"] or 0) >= target_sequence
        ):
            return health
        time.sleep(0.005)
    health = advisor.get_mode5_trace_health()
    raise AssertionError(
        "Mode5 trace writer did not finish expected failures: "
        f"target_sequence={target_sequence} "
        f"expected_append_failures={expected_append_failures} "
        f"queue_depth={health['queue_depth']} active_writes={health['active_writes']} "
        f"pending_unpersisted={health['pending_unpersisted']} "
        f"append_failures={health['append_failures']} "
        f"last_processed_sequence={health['last_processed_sequence']} "
        f"last_error={health['last_error']}"
    )


def _wait_for_mode5_trace_idle(advisor, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = advisor.get_mode5_trace_health()
        if (
            health["queue_depth"] == 0
            and health["active_writes"] == 0
            and health["pending_unpersisted"] == 0
        ):
            return health
        time.sleep(0.005)
    health = advisor.get_mode5_trace_health()
    raise AssertionError(
        "Mode5 trace writer did not become idle: "
        f"queue_depth={health['queue_depth']} active_writes={health['active_writes']} "
        f"pending_unpersisted={health['pending_unpersisted']} "
        f"append_failures={health['append_failures']} "
        f"queue_full_drops={health['queue_full_drops']} "
        f"oversize_drops={health['oversize_drops']} "
        f"writer_unavailable_drops={health['writer_unavailable_drops']} "
        f"last_error={health['last_error']}"
    )


def test_mode5_trace_pending_records_prevent_idle_while_queue_and_writer_are_empty(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-pending-only.json"), enable_stdout=False)
    with advisor._mode5_trace_health_lock:
        advisor._mode5_trace_health["pending_unpersisted"] = 1
    health = advisor.get_mode5_trace_health()
    assert health["queue_depth"] == 0
    assert health["active_writes"] == 0
    with pytest.raises(AssertionError) as exc:
        _wait_for_mode5_trace_idle(advisor, timeout=0.03)
    assert "queue_depth=0" in str(exc.value)
    assert "active_writes=0" in str(exc.value)
    assert "pending_unpersisted=1" in str(exc.value)
    with advisor._mode5_trace_health_lock:
        advisor._mode5_trace_health["pending_unpersisted"] = 0


def _read_mode5_trace_records(
    advisor, *, allow_unpersisted: bool = False, expected_append_failures: Optional[int] = None,
    target_sequence: Optional[int] = None,
) -> list[dict]:
    if allow_unpersisted:
        if expected_append_failures is None or target_sequence is None:
            raise ValueError(
                "expected_append_failures and target_sequence are required when allowing unpersisted records"
            )
        health = _wait_for_mode5_trace_expected_failures(
            advisor, target_sequence, expected_append_failures
        )
        if (health["last_persisted_sequence"] or 0) < target_sequence:
            raise AssertionError(
                "Mode5 trace target was processed but not persisted: "
                f"target_sequence={target_sequence} "
                f"last_persisted_sequence={health['last_persisted_sequence']} "
                f"pending_unpersisted={health['pending_unpersisted']}"
            )
    else:
        _wait_for_mode5_trace_quiescent(advisor)
    if not advisor.decision_trace_path.exists():
        records = []
    else:
        records = [json.loads(line) for line in advisor.decision_trace_path.read_text().splitlines()]
    if allow_unpersisted and not any(
        row.get("trace_run_id") == advisor.trace_run_id
        and row.get("trace_sequence") == target_sequence
        for row in records
    ):
        raise AssertionError(
            "Mode5 trace target identity is absent from persisted JSONL: "
            f"trace_run_id={advisor.trace_run_id} "
            f"target_sequence={target_sequence} "
            f"last_persisted_sequence={health['last_persisted_sequence']}"
        )
    return records


def test_mode5_quote_suppression_requires_active_candidate_and_records_both_reasons(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-reasons.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-reasons.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    boundary_ms = int(boundary.timestamp() * 1000)
    depth = _make_dummy_depth(ts_ms=boundary_ms - 1, ingress_ns=1, sequence_id=1)
    instrument = advisor._canonical_option_instrument_key("NIFTY", depth.token)
    assert instrument is not None

    # No active candidate means a source/incoming-time mismatch remains untraced.
    no_signal, no_generation = advisor._candidate_for_option_depth(
        "NIFTY", depth, boundary.date(), instrument, (depth.exchange_timestamp_ms, depth.sequence_id),
        now_ns=time.monotonic_ns(),
    )
    assert no_signal is None and no_generation is None
    assert not advisor.decision_trace_path.exists()

    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=boundary_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns - 1,
        sequence_id=2,
    )
    instrument = advisor._canonical_option_instrument_key("NIFTY", depth.token)
    source_order = (depth.exchange_timestamp_ms, depth.sequence_id)
    advisor._option_depth_watermarks["NIFTY"][instrument] = (
        boundary.date(), source_order[0], source_order[1]
    )
    result = advisor._candidate_for_option_depth(
        "NIFTY", depth, boundary.date(), instrument, source_order,
        now_ns=metadata.issued_monotonic_ns + 100,
        validated_decision_timestamp_ms=boundary_ms + 10,
    )
    assert result == (None, None)
    # Same event/reasons are deduplicated; the candidate remains available.
    advisor._candidate_for_option_depth(
        "NIFTY", depth, boundary.date(), instrument, source_order,
        now_ns=metadata.issued_monotonic_ns + 100,
        validated_decision_timestamp_ms=boundary_ms + 11,
    )
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    records = _read_mode5_trace_records(advisor)
    assert {row["reason"] for row in records} == {
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY",
        "MODE5_QUOTE_INGRESS_BEFORE_CANDIDATE_ISSUE",
    }
    assert len(records) == 2
    for row in records:
        assert row["event_type"] == "MODE5_QUOTE_SUPPRESSED"
        assert row["action"] == "ABSTAIN"
        assert row["decision"] == "RETAIN_CANDIDATE"
        assert row["index_name"] == "NIFTY"
        assert row["candidate_id"] == advisor._mode5_candidate_id(
            "NIFTY", metadata.session_day, metadata.generation
        )
        assert row["canonical_instrument"] == instrument
        assert row["candidate_generation"] == metadata.generation
        assert row["candidate_action"] == signal.action
        assert row["candidate_setup"] == signal.setup_reason
        assert row["candidate_bar_time"] == "11:35:00"
        assert row["boundary_timestamp_ms"] == boundary_ms
        assert row["issued_monotonic_ns"] == metadata.issued_monotonic_ns
        assert row["quote_exchange_timestamp_ms"] == depth.exchange_timestamp_ms
        assert row["ingress_monotonic_ns"] == depth.ingress_monotonic_ns
        assert row["validated_decision_timestamp_ms"] == boundary_ms + 10


def test_mode5_invalid_bar_summary_preserves_validation_reason(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "evaluation-summary.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / "evaluation-summary.jsonl"
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=25000.0,
        bar_high=25010.0,
        bar_low=24990.0,
        bar_close=25005.0,
        bar_volume=100.0,
        bar_time=dt_time(10, 0),
        timestamp_ms=int(datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000),
        epoch_5min=-1,
        decision_available_at_ms=None,
    )
    records = _read_mode5_trace_records(advisor)
    summaries = [r for r in records if r.get("event_type") == "MODE5_EVALUATION_SUMMARY"]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["evaluation_state"] == "REJECTED"
    assert summary["candidate_state"] == "NOT_EMITTED"
    assert summary["candidate_id"] is None
    assert summary["reason_code"] == "INVALID_COMPLETED_BAR"
    assert not advisor._lock._is_owned()


def test_mode5_validated_no_signal_has_no_invented_reason(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "valid-no-signal.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / "valid-no-signal.jsonl"
    boundary = datetime(2026, 11, 18, 9, 55, tzinfo=ZoneInfo("Asia/Kolkata"))
    timestamp_ms = int(boundary.timestamp() * 1000) - 1
    epoch = timestamp_ms // 300_000
    assert datetime.fromtimestamp(epoch * 300, tz=ZoneInfo("Asia/Kolkata")).time() == dt_time(9, 50)
    evaluator = Mock(return_value=None)
    monkeypatch.setattr(advisor, "_on_5m_bar_close_locked", evaluator)
    # Freeze host wall time to the supplied completed-bar availability point.
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: ((epoch + 1) * 300_000 + 1) / 1000.0)
    advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=25000.0, bar_high=25010.0, bar_low=24990.0,
        bar_close=25005.0, bar_volume=100.0, bar_time=boundary.time(),
        timestamp_ms=timestamp_ms, epoch_5min=epoch,
        decision_available_at_ms=(epoch + 1) * 300_000 + 1,
    )
    summaries = [
        r for r in _read_mode5_trace_records(advisor)
        if r.get("event_type") == "MODE5_EVALUATION_SUMMARY"
    ]
    assert len(summaries) == 1
    assert summaries[0]["evaluation_state"] == "NO_SIGNAL"
    assert summaries[0]["candidate_state"] == "NOT_EMITTED"
    assert summaries[0]["candidate_id"] is None
    assert summaries[0]["reason_code"] is None
    assert summaries[0]["epoch_5min"] == epoch
    assert evaluator.call_count == 1
    assert advisor._mode5_last_eval_rejection.get("NIFTY") is None


def test_mode5_evaluator_exception_is_traced_and_original_exception_survives_queue_failure(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "evaluation-error.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / "evaluation-error.jsonl"
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    timestamp_ms = int(boundary.timestamp() * 1000) - 1
    epoch = timestamp_ms // 300_000
    original_error = RuntimeError("private details must not be serialized")
    monkeypatch.setattr(
        advisor, "_on_5m_bar_close_locked", Mock(side_effect=original_error)
    )
    with pytest.raises(RuntimeError) as caught:
        advisor._on_5m_bar_close(
            "NIFTY", 25000.0, 25010.0, 24990.0, 25005.0, 100.0,
            boundary.time(), timestamp_ms, epoch,
            decision_available_at_ms=(epoch + 1) * 300_000 + 1,
        )
    assert caught.value is original_error
    error_events = [
        row for row in _read_mode5_trace_records(advisor)
        if row.get("event_type") == "MODE5_EVALUATION_ERROR"
    ]
    assert len(error_events) == 1
    assert error_events[0]["evaluation_id"].endswith(f":NIFTY:{epoch}")
    assert error_events[0]["exception_class"] == "RuntimeError"
    assert "private details" not in json.dumps(error_events[0])
    assert error_events[0]["evaluation_stage"] == "BAR_EVALUATOR"
    assert error_events[0]["partial_state_unknown"] is True

    queue_error = OSError("trace queue failure")
    monkeypatch.setattr(
        advisor, "_enqueue_mode5_trace_record", Mock(side_effect=queue_error)
    )
    second_error = ValueError("original evaluator error")
    monkeypatch.setattr(
        advisor, "_on_5m_bar_close_locked", Mock(side_effect=second_error)
    )
    with pytest.raises(ValueError) as caught_queue_failure:
        advisor._on_5m_bar_close(
            "NIFTY", 25000.0, 25010.0, 24990.0, 25005.0, 100.0,
            boundary.time(), timestamp_ms, epoch,
            decision_available_at_ms=(epoch + 1) * 300_000 + 1,
        )
    assert caught_queue_failure.value is second_error


@pytest.mark.parametrize("use_dispatcher", [True, False])
def test_mode5_candidate_is_blocked_before_sizing_and_apm(
    tmp_path: Path, monkeypatch, use_dispatcher: bool,
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"apm-outcome-{use_dispatcher}.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    reservation = SimpleNamespace(
        accepted=True, reason="RESERVED_PAPER", action="RESERVED", routed_mode="PAPER"
    )
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=90_000_000_000 + int(use_dispatcher) * 10_000_000_000,
        reservation_result=reservation,
    )
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)
    advisor.decision_trace_path = tmp_path / f"apm-outcome-{use_dispatcher}.jsonl"
    if not use_dispatcher:
        advisor.automated_dispatcher = None
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    advisor._evaluate_option_depth(depth)

    records = _read_mode5_trace_records(advisor)
    stage_rows = [r for r in records if r.get("event_type") == "MODE5_CANDIDATE_STAGE"]
    terminal_rows = [r for r in records if r.get("event_type") == "MODE5_CANDIDATE_TERMINAL"]
    observation_rows = [r for r in records if r.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert stage_rows == []
    assert len(terminal_rows) == 1
    assert terminal_rows[0]["terminal_reason"] == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert len(observation_rows) == 1
    assert observation_rows[0]["candidate_generation"] == generation
    assert any(
        row.get("reason") == "MODE5_OR_FINAL_DIAGNOSTIC_ONLY"
        for row in _read_mode5_trace_records(advisor)
    )
    lot_sizing.assert_not_called()
    assert advisor.apms["NIFTY"].arm_and_enter.call_count == 0
    if use_dispatcher:
        advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    assert terminal_rows[0]["broker_fill_confirmed"] is False


@pytest.mark.parametrize("or_state", ["VALID", "TARGET_UNAVAILABLE", "COMPANION_UNAVAILABLE", "BOTH_UNAVAILABLE"])
def test_actual_mode5_quote_path_observes_overlays_but_never_authorizes_entry(
    tmp_path: Path, monkeypatch, or_state: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-overlay-nonauthorizing.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, rbfn_signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=95_000_000_000,
        setup_reason="TEST_DIRECTIONAL_CONTINUATION",
        trade_phase="CONTINUOUS_STATE_MACHINE",
    )
    if or_state in {"TARGET_UNAVAILABLE", "BOTH_UNAVAILABLE"}:
        advisor.or_evidence["NIFTY"]["available_at_ms"] = None
    if or_state in {"COMPANION_UNAVAILABLE", "BOTH_UNAVAILABLE"}:
        advisor.or_evidence["SENSEX"]["status"] = "PENDING_RECONCILIATION"
        advisor.or_evidence["SENSEX"]["available_at_ms"] = None
    expected_strategy_target_pts = rbfn_signal.target_pts
    advisor._mode5_bar_policy_observations["NIFTY"] = {
        "gate2": {
            "compression": {"would_veto": True, "effect": "DIAGNOSTIC_ONLY"},
            "atr_frictional_hurdle": {"would_veto": True, "effect": "DIAGNOSTIC_ONLY"},
        }
    }
    # Force the shared macro overlay to evaluate its companion alignment branch.
    advisor.spots["SENSEX"] = 84000.0
    advisor.macro_gate.evaluate_alignment = Mock(return_value=(False, "TEST_MACRO_VETO"))
    advisor.vol_compression_gate.evaluate_compression = Mock(
        return_value=(False, "TEST_EXHAUSTION_VETO", None)
    )
    advisor.evaluate_nifty_frictional_hurdle = Mock(return_value=(False, "TEST_FRICTION_VETO"))
    advisor.confidence_scorer.evaluate_confidence = Mock(return_value=SimpleNamespace(
        is_actionable=False, total_score=float("nan"), grade="C", probable_win_rate_pct=20,
        sizing_recommendation="ZERO_SUPPRESS",
    ))
    advisor.wall_gates["NIFTY"] = SimpleNamespace(
        evaluate_entry_gate=Mock(return_value=SimpleNamespace(
            action=advisor_module.GATE_ACTION_VETO, reason="TEST_WALL_VETO"
        )),
        clamp_target_to_wall=Mock(return_value=SimpleNamespace(
            action=advisor_module.GATE_ACTION_CLAMP_TARGET,
            reason="TEST_WALL_CLAMP",
            clamped_target_pts=1.0,
        )),
    )
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)
    advisor.record_veto = Mock(wraps=advisor.record_veto)
    active_apm = advisor.apms["NIFTY"]
    active_apm.state = advisor_module.STATE_IN_FLIGHT
    active_apm.payload = SimpleNamespace(opt_symbol=depth.symbol)
    active_apm.evaluate_tick = Mock()
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver,
        "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    decision_available_ms = advisor._observed_ingress_timestamp_ms(depth.ingress_wall_utc)
    assert decision_available_ms is not None
    or_valid, or_reason, _ = advisor._validate_mode5_or_pair(
        "NIFTY", depth.exchange_timestamp_ms, metadata.boundary_timestamp_ms,
        decision_available_ms,
    )
    assert or_valid is (or_state in {"VALID", "COMPANION_UNAVAILABLE"}), or_reason
    quote_valid, quote_reason, quote_day, instrument_key, source_order = advisor._option_quote_identity(
        "NIFTY", depth, wall_now_ms=depth.exchange_timestamp_ms + 10,
        monotonic_now_ns=metadata.issued_monotonic_ns + 2_000_000,
    )
    assert quote_valid, quote_reason
    assert quote_day == metadata.session_day
    assert instrument_key is not None and source_order is not None
    assert depth.ltp < advisor.max_premium_cap
    assert (depth.ask_p1 - depth.bid_p1) / depth.ltp <= advisor.spread_veto_threshold

    advisor._evaluate_option_depth(depth)
    advisor._evaluate_option_depth(depth)  # duplicate quote cannot repeat lifecycle/veto
    assert not any(call.args[:1] == ("MODE5_OR",) for call in advisor.record_veto.call_args_list)
    active_apm.evaluate_tick.assert_called_once()
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()

    advisor.macro_gate.evaluate_alignment.assert_called_once()
    advisor.vol_compression_gate.evaluate_compression.assert_called_once()
    advisor.evaluate_nifty_frictional_hurdle.assert_called_once()
    advisor.confidence_scorer.evaluate_confidence.assert_called_once()
    assert advisor.confidence_scorer.evaluate_confidence.call_args.kwargs["writer_conviction"] == 0.5
    advisor.wall_gates["NIFTY"].evaluate_entry_gate.assert_called_once()
    advisor.wall_gates["NIFTY"].clamp_target_to_wall.assert_called_once()
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == generation
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "MODE5_SIZING_POLICY_UNVERIFIED"

    records = _read_mode5_trace_records(advisor)
    terminal_rows = [row for row in records if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"]
    policy_rows = [row for row in records if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert len(terminal_rows) == len(policy_rows) == 1
    or_rows = [row for row in records if row.get("reason") == "MODE5_OR_DIAGNOSTIC_ONLY"]
    assert or_rows
    assert or_rows[0]["action"] == rbfn_signal.action
    assert or_rows[0]["details"]["decision_authority"] == "DIAGNOSTIC_ONLY"
    assert or_rows[0]["details"]["valid"] is (or_state in {"VALID", "COMPANION_UNAVAILABLE"})
    observed = policy_rows[0]["observations"]
    assert observed["gate2"]["compression"]["effect"] == "DIAGNOSTIC_ONLY"
    assert observed["macro"]["would_veto"] is True
    assert observed["exhaustion"]["would_veto"] is True
    assert observed["wall_and_clamp"]["entry_decision"]["reason"] == "TEST_WALL_VETO"
    assert observed["wall_and_clamp"]["status"] == "EVALUATED"
    assert observed["wall_and_clamp"]["target_clamp"]["target_mutation_applied"] is False
    assert observed["friction"]["would_veto"] is True
    assert observed["confidence"]["would_be_actionable"] is False
    assert observed["target"]["strategy_target_pts"] == expected_strategy_target_pts
    assert observed["target"]["effective_target_pts"] == expected_strategy_target_pts
    assert observed["target"]["overlay_mutation_applied"] is False
    assert observed["confidence"]["score"] is None
    assert observed["diagnostic_sanitization"]["status"] == "NONFINITE_REPLACED_WITH_NULL"
    assert "observations.confidence.score" in observed["diagnostic_sanitization"]["replaced_paths"]
    json.dumps(policy_rows[0], allow_nan=False)
    assert observed["opening_range"]["decision_authority"] == "DIAGNOSTIC_ONLY"
    assert observed["opening_range"]["valid"] is (or_state in {"VALID", "COMPANION_UNAVAILABLE"})


def test_mode5_research_policy_does_not_consume_wrong_strike_quote(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-wrong-strike-retained.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=95_500_000_000,
    )
    advisor.strike_resolver.is_contract_matching = Mock(return_value=False)
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)

    advisor._evaluate_option_depth(depth)

    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert metadata.generation == generation
    assert metadata.status == "AVAILABLE"
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    records = _read_mode5_trace_records(advisor)
    assert not any(row.get("event_type") == "MODE5_CANDIDATE_TERMINAL" for row in records)
    assert not any(row.get("event_type") == "MODE5_POLICY_OBSERVATION" for row in records)
    after_quote = [
        row for row in records
        if row.get("reason") == "MODE5_CANDIDATE_STATE_AFTER_QUOTE_REJECTION"
    ]
    assert after_quote and after_quote[-1]["details"]["candidate_state"] == "AVAILABLE"
    assert after_quote[-1]["details"]["entry_authorized"] is False


def test_mode5_research_policy_does_not_consume_candidate_after_newer_quote_watermark(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-newer-watermark-retained.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=95_750_000_000,
    )
    instrument_key = advisor._canonical_option_instrument_key("NIFTY", depth.token)
    assert instrument_key is not None

    def advance_watermark(**kwargs):
        with advisor._lock:
            advisor._option_depth_watermarks["NIFTY"][instrument_key] = (
                date(2026, 11, 18), depth.exchange_timestamp_ms + 1, depth.sequence_id + 1
            )
        return SimpleNamespace(
            is_actionable=True, total_score=90, grade="A", probable_win_rate_pct=70,
            sizing_recommendation="FULL",
        )

    advisor.confidence_scorer.evaluate_confidence = Mock(side_effect=advance_watermark)
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)

    advisor._evaluate_option_depth(depth)

    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == generation
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    advisor.confidence_scorer.evaluate_confidence.assert_called_once()
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    records = _read_mode5_trace_records(advisor)
    assert not any(row.get("event_type") == "MODE5_POLICY_OBSERVATION" for row in records)


def test_mode5_research_policy_expires_candidate_at_terminalization_recheck(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-terminalization-expired.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=96_000_000_000,
    )
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]

    def expire_before_policy_recheck(**kwargs):
        monkeypatch.setattr(
            advisor_module,
            "_monotonic_clock_ns",
            lambda: metadata.issued_monotonic_ns + 300_000_000_001,
        )
        return SimpleNamespace(
            is_actionable=True, total_score=90, grade="A", probable_win_rate_pct=70,
            sizing_recommendation="FULL",
        )

    advisor.confidence_scorer.evaluate_confidence = Mock(side_effect=expire_before_policy_recheck)
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)

    advisor._evaluate_option_depth(depth)

    assert advisor._cached_rbfn_candidate_meta["NIFTY"] is None
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    records = _read_mode5_trace_records(advisor)
    terminal_rows = [
        row for row in records
        if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"
        and row.get("candidate_generation") == generation
    ]
    assert len(terminal_rows) == 1
    assert terminal_rows[0]["terminal_reason"] == "EXPIRED"
    assert not any(row.get("event_type") == "MODE5_POLICY_OBSERVATION" for row in records)


@pytest.mark.parametrize(
    "position_state",
    [
        advisor_module.STATE_IN_FLIGHT,
        advisor_module.STATE_TRAIL_LOCK,
        advisor_module.STATE_EXIT_PENDING,
    ],
)
def test_mode5_or_entry_veto_still_manages_matching_open_position_once(
    tmp_path: Path, monkeypatch, position_state: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"mode5-or-position-{position_state}.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=96_000_000_000,
    )
    advisor.decision_trace_path = tmp_path / f"mode5-or-position-{position_state}.jsonl"
    advisor.or_evidence["NIFTY"]["available_at_ms"] = None
    apm = advisor.apms["NIFTY"]
    apm.state = position_state
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol)
    apm.evaluate_tick = Mock()
    apm.arm_and_enter = Mock()
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver,
        "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )
    advisor.record_veto = Mock(wraps=advisor.record_veto)

    advisor._evaluate_option_depth(depth)

    assert not any(call.args[:1] == ("MODE5_OR",) for call in advisor.record_veto.call_args_list)
    apm.evaluate_tick.assert_called_once_with(
        current_spot=advisor.spots["NIFTY"],
        current_opt_ltp=depth.ltp,
        tick_time_str=datetime.fromtimestamp(
            depth.exchange_timestamp_ms / 1000.0, tz=ZoneInfo("Asia/Kolkata")
        ).strftime("%H:%M:%S"),
        atr_1m=12.0,
    )
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    apm.arm_and_enter.assert_not_called()
    advisor.journal.record_execution.assert_not_called()
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == generation
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "MODE5_SIZING_POLICY_UNVERIFIED"
    records = _read_mode5_trace_records(advisor)
    policy_rows = [row for row in records if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert len(policy_rows) == 1
    assert any(row.get("reason") == "MODE5_OR_DIAGNOSTIC_ONLY" for row in records)


def test_mode5_or_veto_preserves_existing_liquidation_journal_and_dispatch_once(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-or-exit-transition.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=96_500_000_000,
    )
    advisor.decision_trace_path = tmp_path / "mode5-or-exit-transition.jsonl"
    advisor.or_evidence["NIFTY"]["available_at_ms"] = None
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol)
    apm.last_completed_trade = None
    @dataclass
    class CompletedTrade:
        position_id: str = "existing-position-17"
        direction: str = "CE"
        entry_price: float = 24100.0
        exit_price: float = 24080.0
        opt_entry_ltp: float = 25.0
        opt_exit_ltp: float = 21.0
        opt_pnl_pts: float = -4.0
        pnl_pts: float = -20.0
        exit_reason: str = "STOP_LOSS"
        total_quantity: int = 25
        max_spot_excursion: float = 0.0
        max_opt_excursion: float = 0.0
        target_1_hit: bool = False
        target_2_hit: bool = False
        half_booked: bool = False
        trail_locked: bool = False

    completed_trade = CompletedTrade()

    def complete_exit(**kwargs):
        apm.last_completed_trade = completed_trade
        apm.state = advisor_module.STATE_LIQUIDATED

    apm.evaluate_tick = Mock(side_effect=complete_exit)
    apm.arm_and_enter = Mock()
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver,
        "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )
    advisor.record_veto = Mock(wraps=advisor.record_veto)

    advisor._evaluate_option_depth(depth)

    assert not any(call.args[:1] == ("MODE5_OR",) for call in advisor.record_veto.call_args_list)
    apm.evaluate_tick.assert_called_once()
    advisor.journal.record_exit.assert_called_once()
    broker_key = advisor._canonical_option_instrument_key("NIFTY", depth.token)
    assert broker_key is not None
    advisor.automated_dispatcher.on_apm_exit.assert_called_once_with(
        index_name="NIFTY",
        symbol=broker_key,
        exit_price=21.0,
        reason="STOP_LOSS",
        qty=25,
        intent_id="existing-position-17",
    )
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    apm.arm_and_enter.assert_not_called()
    advisor.journal.record_execution.assert_not_called()
    lot_sizing.assert_not_called()


@pytest.mark.parametrize(
    ("quote_time", "expected_squareoff"),
    [(dt_time(15, 14, 59), False), (dt_time(15, 15), True)],
)
def test_eod_quote_manages_matching_position_once_without_entry(
    tmp_path: Path, monkeypatch, quote_time: dt_time, expected_squareoff: bool
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"eod-manage-{quote_time.isoformat()}.json"),
        enable_stdout=False,
    )
    day = date(2026, 11, 18)
    boundary = datetime.combine(day, quote_time, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=98_000_000_000 + quote_time.minute * 1_000_000,
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    completed_trade = {
        "position_id": "eod-position-1",
        "direction": "CE",
        "entry_price": 24000.0,
        "exit_price": 24010.0,
        "opt_entry_ltp": 20.0,
        "opt_exit_ltp": 22.0,
        "opt_pnl_pts": 2.0,
        "pnl_pts": 10.0,
        "exit_reason": "EOD_MANDATORY_SQUAREOFF",
        "total_quantity": 25,
    }

    def manage_eod(**kwargs):
        if expected_squareoff:
            apm.last_completed_trade = completed_trade
            apm.state = advisor_module.STATE_LIQUIDATED

    apm.evaluate_tick = Mock(side_effect=manage_eod)
    apm.arm_and_enter = Mock()
    advisor.journal.record_exit = Mock()
    advisor.automated_dispatcher.on_apm_exit = Mock()
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)

    advisor._evaluate_option_depth(depth)

    apm.evaluate_tick.assert_called_once_with(
        current_spot=advisor.spots["NIFTY"],
        current_opt_ltp=depth.ltp,
        tick_time_str=(
            boundary.isoformat()
            if expected_squareoff
            else boundary.strftime("%H:%M:%S")
        ),
        atr_1m=12.0,
    )
    assert expected_squareoff is (quote_time >= dt_time(15, 15))
    assert advisor.journal.record_exit.call_count == int(expected_squareoff)
    assert advisor.automated_dispatcher.on_apm_exit.call_count == int(expected_squareoff)
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    apm.arm_and_enter.assert_not_called()


@pytest.mark.parametrize(
    "mutation",
    [
        "zero_spot_timestamp", "stale_spot_timestamp", "invalid_spot", "stale_option",
        "zero_ltp", "nan_ltp", "infinite_ltp", "missing_ltp", "string_ltp", "overflow_ltp", "zero_bid",
        "nan_ask", "bool_ask", "crossed_book", "token_mismatch", "symbol_mismatch",
    ],
)
def test_invalid_or_mismatched_quote_never_updates_active_position(
    tmp_path: Path, monkeypatch, mutation: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"invalid-position-quote-{mutation}.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=99_000_000_000,
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    apm.evaluate_tick = Mock()
    sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", sizing)
    if mutation == "zero_spot_timestamp":
        advisor.spots_ts_ms["NIFTY"] = 0
    elif mutation == "stale_spot_timestamp":
        advisor.spots_ts_ms["NIFTY"] = depth.exchange_timestamp_ms - int(advisor.skew_threshold_ms) - 1
    elif mutation == "invalid_spot":
        advisor.spots["NIFTY"] = math.nan
    elif mutation == "stale_option":
        depth = replace(
            depth,
            exchange_timestamp_ms=(
                depth.exchange_timestamp_ms
                - int(float(advisor_module.app_config.MAX_QUOTE_AGE_SEC) * 1000)
                - 1
            ),
        )
    elif mutation == "zero_ltp":
        depth = replace(depth, ltp=0.0)
    elif mutation == "nan_ltp":
        depth = replace(depth, ltp=math.nan)
    elif mutation == "infinite_ltp":
        depth = replace(depth, ltp=math.inf)
    elif mutation == "missing_ltp":
        depth = replace(depth, ltp=None)
    elif mutation == "string_ltp":
        depth = replace(depth, ltp="25.0")
    elif mutation == "overflow_ltp":
        depth = replace(depth, ltp=10**10000)
    elif mutation == "zero_bid":
        depth = replace(depth, bid_p1=0.0)
    elif mutation == "nan_ask":
        depth = replace(depth, ask_p1=math.nan)
    elif mutation == "bool_ask":
        depth = replace(depth, ask_p1=True)
    elif mutation == "crossed_book":
        depth = replace(depth, bid_p1=30.0, ask_p1=29.0)
    elif mutation == "token_mismatch":
        apm.payload.opt_token = "NSE_FO|OTHER"
    elif mutation == "symbol_mismatch":
        apm.payload.opt_symbol = "NIFTY 24000 PE"

    advisor._evaluate_option_depth(depth)

    apm.evaluate_tick.assert_not_called()
    advisor.journal.record_exit.assert_not_called()
    advisor.automated_dispatcher.on_apm_exit.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    apm.arm_and_enter.assert_not_called()
    sizing.assert_not_called()
    assert apm.state == advisor_module.STATE_IN_FLIGHT


def test_strict_quote_value_helper_rejects_integer_float_overflow():
    assert SentinelLiveStreamAdvisor._strict_positive_finite_quote_value(10**10000) is None


def test_future_timestamp_check_fails_closed_when_decision_clock_is_unavailable(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "future-clock-fail-closed.json"), enable_stdout=False
    )
    monkeypatch.setattr(advisor, "_decision_wall_clock_ms", lambda: None)
    assert advisor._source_timestamp_exceeds_future_skew(1_800_000_000_000) is True

    monkeypatch.setattr(
        advisor, "_decision_wall_clock_ms", Mock(side_effect=RuntimeError("clock unavailable"))
    )
    assert advisor._source_timestamp_exceeds_future_skew(1_800_000_000_000) is True

    monkeypatch.setattr(advisor, "_decision_wall_clock_ms", lambda: 1_800_000_000_000)
    assert advisor._source_timestamp_exceeds_future_skew(1_800_000_000_000) is False


def test_position_exit_transition_blocks_same_quote_entry_and_dispatch(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "same-quote-exit-no-reentry.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=100_000_000_000,
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    apm.last_completed_trade = None
    apm.evaluate_tick = Mock(side_effect=lambda **_: setattr(apm, "state", advisor_module.STATE_LIQUIDATED))
    advisor.journal.record_exit = Mock()
    advisor.automated_dispatcher.on_apm_exit = Mock()
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)

    advisor._evaluate_option_depth(depth)

    apm.evaluate_tick.assert_called_once()
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    apm.arm_and_enter.assert_not_called()


def test_oi_entry_veto_does_not_suppress_matching_position_management(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "oi-veto-still-manages.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=101_000_000_000, strike_oi_allowed=False,
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    apm.evaluate_tick = Mock()
    apm.arm_and_enter = Mock()

    advisor._evaluate_option_depth(depth)

    apm.evaluate_tick.assert_called_once()
    advisor.evaluate_strike_oi.assert_called_once()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    apm.arm_and_enter.assert_not_called()


def test_eod_exit_pending_position_is_evaluated_once_without_duplicate_exit_callbacks(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "eod-exit-pending.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 15, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=102_000_000_000,
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_EXIT_PENDING
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    apm.evaluate_tick = Mock()
    advisor.journal.record_exit = Mock()
    advisor.automated_dispatcher.on_apm_exit = Mock()

    advisor._evaluate_option_depth(depth)
    advisor._evaluate_option_depth(depth)  # duplicate source order must not repeat APM work

    apm.evaluate_tick.assert_called_once()
    advisor.journal.record_exit.assert_not_called()
    advisor.automated_dispatcher.on_apm_exit.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()


@pytest.mark.parametrize("position_kind", ["none", "wrong_symbol"])
def test_mode5_or_entry_veto_does_not_manage_unmatched_position_or_enter(
    tmp_path: Path, monkeypatch, position_kind: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"mode5-or-unmatched-{position_kind}.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=97_000_000_000,
    )
    advisor.or_evidence["NIFTY"]["available_at_ms"] = None
    apm = advisor.apms["NIFTY"]
    if position_kind == "none":
        apm.state = advisor_module.STATE_STANDBY
        apm.payload = None
    else:
        apm.state = advisor_module.STATE_IN_FLIGHT
        apm.payload = SimpleNamespace(opt_symbol="NIFTY 24000 PE")
    apm.evaluate_tick = Mock()
    apm.arm_and_enter = Mock()
    lot_sizing = Mock(return_value=(1, "FULL"))
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lot_sizing)
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver,
        "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    advisor._evaluate_option_depth(depth)

    apm.evaluate_tick.assert_not_called()
    lot_sizing.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    apm.arm_and_enter.assert_not_called()


def test_mode5_dispatch_unknown_is_not_terminalized_again_on_invalidation(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "dispatch-unknown-terminal.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / "dispatch-unknown-terminal.jsonl"
    advisor._mode5_candidate_lifecycle_slots["NIFTY"] = {
        "candidate_id": "run:2026-11-18:NIFTY:7",
        "session_date": "2026-11-18",
        "generation": 7,
        "state": "AVAILABLE",
        "action": "BUY_CALL",
        "setup_reason": "RBFN_TEST",
    }
    with advisor._lock:
        advisor._terminalize_mode5_candidate_locked(
            "NIFTY", "RESERVATION_EXCEPTION_UNKNOWN", timestamp_ms=1000
        )
        assert advisor._mode5_candidate_lifecycle_slots["NIFTY"]["state"] == "DISPATCH_UNKNOWN"
        advisor._terminalize_mode5_candidate_locked(
            "NIFTY", "LEVELS_INVALIDATED", timestamp_ms=2000
        )
    advisor._flush_mode5_lifecycle_records_after_unlock()

    terminal_rows = [
        row for row in _read_mode5_trace_records(advisor)
        if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"
    ]
    assert len(terminal_rows) == 1
    assert terminal_rows[0]["candidate_id"] == "run:2026-11-18:NIFTY:7"
    assert terminal_rows[0]["candidate_state"] == "DISPATCH_UNKNOWN"
    assert terminal_rows[0]["terminal_reason"] == "RESERVATION_EXCEPTION_UNKNOWN"


def test_mode5_sizing_block_prevents_apm_entry_before_apm_handler(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "apm-exception-unknown.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    reservation = SimpleNamespace(
        accepted=True, reason="RESERVED_PAPER", action="RESERVED", routed_mode="PAPER"
    )
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=150_000_000_000,
        reservation_result=reservation,
    )
    advisor.decision_trace_path = tmp_path / "apm-exception-unknown.jsonl"
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    advisor._evaluate_option_depth(depth)

    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    assert advisor.automated_dispatcher.on_apm_entry.call_count == 0
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    advisor.journal.record_execution.assert_not_called()
    records = _read_mode5_trace_records(advisor)
    stage_rows = [row for row in records if row.get("event_type") == "MODE5_CANDIDATE_STAGE"]
    terminal_rows = [row for row in records if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"]
    observation_rows = [row for row in records if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert stage_rows == []
    assert len(terminal_rows) == 1
    assert terminal_rows[0]["terminal_reason"] == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert len(observation_rows) == 1
    assert terminal_rows[0]["broker_fill_confirmed"] is False
    assert not any(row.get("record_type") == "EXECUTION" for row in records)


def test_mode5_candidate_id_is_stable_across_issue_quote_and_terminal(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "candidate-id-chain.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    accepted = SimpleNamespace(
        accepted=True, reason="RESERVED_PAPER", action="RESERVED", routed_mode="PAPER"
    )
    depth, _, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=170_000_000_000,
        reservation_result=accepted,
    )
    advisor.decision_trace_path = tmp_path / "candidate-id-chain.jsonl"
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    candidate_id = advisor._mode5_candidate_id("NIFTY", metadata.session_day, generation)
    advisor._flush_mode5_lifecycle_records_after_unlock()
    lagging_depth = _make_dummy_depth(
        token=depth.token,
        symbol=depth.symbol,
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", depth.token, advisor.cached_rbfn_signals["NIFTY"], metadata,
        lagging_depth, "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms + 10,
    )
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    advisor._evaluate_option_depth(depth)

    records = _read_mode5_trace_records(advisor)
    issued = [row for row in records if row.get("event_type") == "MODE5_CANDIDATE_ISSUED"]
    quote = [row for row in records if row.get("event_type") == "MODE5_QUOTE_SUPPRESSED"]
    terminal = [row for row in records if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"]
    observations = [row for row in records if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert len(issued) == len(quote) == len(terminal) == len(observations) == 1
    assert [row["candidate_id"] for row in (issued[0], quote[0], terminal[0], observations[0])] == [candidate_id] * 4
    assert terminal[0]["terminal_reason"] == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert observations[0]["authorization_block"] == "MODE5_SIZING_POLICY_UNVERIFIED"


def test_mode5_candidate_lifecycle_slots_stay_one_per_supported_index(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "candidate-slot-bounds.json"), enable_stdout=False
    )
    monkeypatch.setattr(advisor, "_publish_mode5_lifecycle_record", Mock(return_value=True))
    session_day = date(2026, 11, 18)
    timestamp_ms = int(datetime.combine(
        session_day, dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata")
    ).timestamp() * 1000)
    supported = ("NIFTY", "SENSEX", "BANKNIFTY")
    for generation_index in range(100):
        index_name = supported[generation_index % len(supported)]
        signal = CachedRBFNAuctionSignal(
            timestamp_ms=timestamp_ms,
            index_name=index_name,
            action="BUY_CALL",
            direction="CE",
            target_strike=25000.0,
            target_pts=25.0,
            sl_pts=15.0,
            setup_reason="RBFN_SLOT_BOUND_TEST",
            trade_phase="MIDDAY_REVERSAL",
            bar_time=dt_time(10, 0),
            is_active=True,
        )
        with advisor._lock:
            advisor._cache_rbfn_signal_locked(index_name, signal, timestamp_ms // 300_000)
        assert set(advisor._mode5_candidate_lifecycle_slots) == set(supported)
        assert len(advisor._mode5_candidate_lifecycle_slots) == 3


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "stale_source", "future_source", "zero_source_clock", "missing_source_clock",
        "zero_ingress_clock", "missing_ingress_clock", "zero_sequence", "missing_sequence",
        "out_of_order",
    ],
)
def test_production_mode5_invalid_quote_cannot_reserve_or_dispatch(
    tmp_path: Path, monkeypatch, invalid_kind: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"invalid-quote-{invalid_kind}.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, wall_now_ms, mono_now_ns = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=180_000_000_000,
    )
    source_timestamp_ms = depth.exchange_timestamp_ms
    ingress_monotonic_ns = depth.ingress_monotonic_ns
    sequence_id = depth.sequence_id
    if invalid_kind == "stale_source":
        source_timestamp_ms = wall_now_ms - 10_000
    elif invalid_kind == "future_source":
        source_timestamp_ms = wall_now_ms + 6_000
    elif invalid_kind == "zero_source_clock":
        source_timestamp_ms = 0
    elif invalid_kind == "missing_source_clock":
        source_timestamp_ms = None
    elif invalid_kind == "zero_ingress_clock":
        ingress_monotonic_ns = 0
    elif invalid_kind == "missing_ingress_clock":
        ingress_monotonic_ns = None
    elif invalid_kind == "zero_sequence":
        sequence_id = 0
    elif invalid_kind == "missing_sequence":
        sequence_id = None
    depth = _make_dummy_depth(
        token=depth.token,
        symbol=depth.symbol,
        ts_ms=source_timestamp_ms,
        ingress_ns=ingress_monotonic_ns,
        sequence_id=sequence_id,
        ingress_wall_utc=depth.ingress_wall_utc,
    )
    if invalid_kind == "out_of_order":
        instrument_key = advisor._canonical_option_instrument_key("NIFTY", depth.token)
        assert instrument_key is not None
        advisor._option_depth_watermarks["NIFTY"][instrument_key] = (
            boundary.date(), depth.exchange_timestamp_ms, depth.sequence_id + 1
        )
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )
    advisor.record_veto = Mock(wraps=advisor.record_veto)

    advisor._evaluate_option_depth(depth)

    if invalid_kind == "out_of_order":
        advisor.record_veto.assert_any_call(
            "OPTION_DEPTH_ORDER", "OPTION_DEPTH_DUPLICATE_DECREASING_OR_PRIOR_SESSION"
        )
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == generation


def test_expired_candidate_terminal_flushes_immediately_when_read(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "expired-candidate-immediate.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    _, _, generation, _, mono_now_ns = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=190_000_000_000,
    )
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    advisor._flush_mode5_lifecycle_records_after_unlock()
    monkeypatch.setattr(
        advisor_module, "_monotonic_clock_ns",
        lambda: mono_now_ns + 300_000_000_001,
    )

    assert advisor.get_valid_cached_rbfn_signal("NIFTY") is None

    terminal_rows = [
        row for row in _read_mode5_trace_records(advisor)
        if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"
    ]
    assert len(terminal_rows) == 1
    assert terminal_rows[0]["candidate_generation"] == generation
    assert terminal_rows[0]["candidate_state"] == "EXPIRED"


def test_mode5_quote_suppression_dedup_is_atomic_and_append_is_outside_state_lock(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-concurrent.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-concurrent.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    original_append = advisor._append_decision_trace_record_locked

    def assert_unlocked_append(record):
        assert not advisor._lock._is_owned()
        assert threading.current_thread().name.startswith("Mode5TraceWriter-")
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        return original_append(record)

    advisor._append_decision_trace_record_locked = assert_unlocked_append
    barrier = threading.Barrier(2)
    emitted = []

    def emit_same_reason():
        barrier.wait(timeout=2)
        emitted.append(advisor._emit_mode5_quote_suppression(
            "NIFTY", "NSE_FO|45408", signal, metadata, depth,
            "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
        ))

    threads = [threading.Thread(target=emit_same_reason) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(emitted) == [False, True]
    records = _read_mode5_trace_records(advisor)
    assert len(records) == 1


def test_mode5_trace_capacity_one_full_drop_is_sticky_and_does_not_veto_dispatch(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "trace-capacity-one.json"),
        enable_stdout=False,
        mode5_trace_queue_capacity=1,
        mode5_trace_max_record_bytes=2048,
    )
    advisor.decision_trace_path = tmp_path / "trace-capacity-one.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    writer_started = threading.Event()
    release_writer = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def blocking_writer(serialized):
        writer_started.set()
        assert release_writer.wait(timeout=4)
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = blocking_writer
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|SUPPRESS", signal, metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )
    assert writer_started.wait(timeout=2)

    producer_barrier = threading.Barrier(10)
    producer_outcomes = []

    def enqueue_concurrent(index):
        reason = f"QUEUE_FILL_{index}"
        record = {
            "event_type": "MODE5_DECISION_TRACE", "index_name": "NIFTY",
            "bar_time": "11:35:00", "action": "ABSTAIN", "reason": reason,
            "details": {"candidate": metadata.generation},
            "timestamp_ms": metadata.boundary_timestamp_ms,
            "candidate_generation": metadata.generation,
        }
        key = advisor._mode5_trace_key("NIFTY", metadata.generation, reason, metadata.boundary_timestamp_ms)
        producer_barrier.wait(timeout=2)
        producer_outcomes.append((reason, advisor._enqueue_mode5_trace_record(record, dedup_key=key)))

    producers = [threading.Thread(target=enqueue_concurrent, args=(i,)) for i in range(10)]
    for producer in producers:
        producer.start()
    for producer in producers:
        producer.join(timeout=3)
    assert all(not producer.is_alive() for producer in producers)
    accepted_reasons = [reason for reason, accepted in producer_outcomes if accepted]
    assert len(accepted_reasons) == 1
    full_record = {
        "event_type": "MODE5_DECISION_TRACE", "index_name": "NIFTY",
        "bar_time": "11:35:00", "action": "ABSTAIN", "reason": "QUEUE_FULL_DROP",
        "details": {}, "timestamp_ms": metadata.boundary_timestamp_ms,
        "candidate_generation": metadata.generation,
    }
    key = advisor._mode5_trace_key("NIFTY", metadata.generation, "QUEUE_FULL_DROP", metadata.boundary_timestamp_ms)
    assert not advisor._enqueue_mode5_trace_record(full_record, dedup_key=key)
    before = advisor.get_mode5_trace_health()
    assert before["queue_full_drops"] == 10
    assert before["queue_depth"] == 1
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"

    # Queue pressure affects only telemetry. The already accepted mock dispatch
    # callback still runs while the trace writer is blocked.
    dispatched = []
    advisor.automated_dispatcher = SimpleNamespace(on_apm_entry=lambda **kwargs: dispatched.append(kwargs))
    advisor._dispatch_reserved_entry_then_flush_traces({"intent_id": "capacity-test"})
    assert dispatched == [{"intent_id": "capacity-test"}]

    # A repeat of the dropped key is coalesced and does not inflate drop counts.
    repeat_record = dict(full_record)
    assert not advisor._enqueue_mode5_trace_record(repeat_record, dedup_key=key)
    assert advisor.get_mode5_trace_health()["queue_full_drops"] == 10
    release_writer.set()
    health = advisor.shutdown_mode5_trace_writer(timeout_sec=3)
    assert health["writer_status"] == "STOPPED"
    assert health["pending_unpersisted"] == 0
    assert health["capacity"] == 1
    records = _read_mode5_trace_records(advisor)
    assert {record["reason"] for record in records} == {
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", accepted_reasons[0]
    }
    assert all(record["reason"] != "QUEUE_FULL_DROP" for record in records)


def test_mode5_trace_oversize_drop_health_and_decision_neutrality(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "trace-oversize.json"), enable_stdout=False,
        mode5_trace_queue_capacity=2, mode5_trace_max_record_bytes=512,
    )
    advisor.decision_trace_path = tmp_path / "trace-oversize.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "OVERSIZE_REASON",
        details={"payload": "x" * 5000}, timestamp_ms=metadata.boundary_timestamp_ms,
        candidate_generation=metadata.generation,
    )
    health = advisor.get_mode5_trace_health()
    assert health["oversize_drops"] == 1
    assert health["enqueued"] == 0
    assert health["max_record_bytes"] == 512
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "OVERSIZE_REASON",
        details={"payload": "small"}, timestamp_ms=metadata.boundary_timestamp_ms,
        candidate_generation=metadata.generation,
    )
    assert advisor.get_mode5_trace_health()["oversize_drops"] == 1
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"
    final = advisor.shutdown_mode5_trace_writer(timeout_sec=2)
    assert final["writer_status"] == "STOPPED"
    assert final["remaining_unpersisted"] == 0


def test_mode5_trace_bounded_shutdown_reports_pending_then_drains(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-shutdown.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-shutdown.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    append_started = threading.Event()
    release_append = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def blocked_append(serialized):
        append_started.set()
        assert release_append.wait(timeout=4)
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = blocked_append
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "SHUTDOWN_DRAIN",
        timestamp_ms=metadata.boundary_timestamp_ms, candidate_generation=metadata.generation,
    )
    assert append_started.wait(timeout=2)
    timed_out = advisor.shutdown_mode5_trace_writer(timeout_sec=0.01)
    assert timed_out["writer_status"] != "STOPPED"
    assert timed_out["remaining_unpersisted"] == 1
    assert timed_out["degraded"] is True

    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "AFTER_SHUTDOWN",
        timestamp_ms=metadata.boundary_timestamp_ms, candidate_generation=metadata.generation,
    )
    assert advisor.get_mode5_trace_health()["writer_unavailable_drops"] == 1
    assert advisor.cached_rbfn_signals["NIFTY"] is signal

    release_append.set()
    drained = advisor.shutdown_mode5_trace_writer(timeout_sec=2)
    assert drained["writer_status"] == "STOPPED"
    assert drained["pending_unpersisted"] == 0
    assert drained["remaining_unpersisted"] == 0
    assert drained["append_successes"] == 1
    assert len(_read_mode5_trace_records(advisor)) == 1


def test_mode5_trace_pending_is_reserved_before_queue_publication(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-publish-race.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-publish-race.jsonl"
    publish_entered = threading.Event()
    allow_publish = threading.Event()
    append_started = threading.Event()
    allow_append = threading.Event()
    original_put = advisor._mode5_trace_queue.put_nowait
    original_append = advisor._append_decision_trace_record_locked

    def blocked_append(serialized):
        append_started.set()
        assert allow_append.wait(timeout=3)
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = blocked_append

    def held_publication(item):
        # The producer has reserved pending health before publishing the item.
        assert advisor._mode5_trace_health["pending_unpersisted"] == 1
        assert advisor._mode5_trace_health["enqueued"] == 0
        assert advisor._mode5_trace_queue.qsize() == 0
        publish_entered.set()
        assert allow_publish.wait(timeout=3)
        return original_put(item)

    monkeypatch.setattr(advisor._mode5_trace_queue, "put_nowait", held_publication)
    outcome = []
    producer = threading.Thread(target=lambda: outcome.append(advisor._enqueue_mode5_trace_record(
        {"event_type": "MODE5_DECISION_TRACE", "index_name": "NIFTY", "reason": "PUBLISH_RACE"},
        dedup_key=None,
    )))
    producer.start()
    assert publish_entered.wait(timeout=2)

    snapshot_started = threading.Event()
    snapshot_done = threading.Event()
    snapshots = []

    def read_snapshot():
        snapshot_started.set()
        snapshots.append(advisor.get_mode5_trace_health())
        snapshot_done.set()

    snapshotter = threading.Thread(target=read_snapshot)
    snapshotter.start()
    assert snapshot_started.wait(timeout=2)
    assert not snapshot_done.wait(timeout=0.05)

    allow_publish.set()
    producer.join(timeout=2)
    assert not producer.is_alive()
    assert outcome == [True]
    assert append_started.wait(timeout=2)
    snapshotter.join(timeout=2)
    assert not snapshotter.is_alive()
    assert snapshots[0]["enqueued"] == 1
    assert snapshots[0]["pending_unpersisted"] == 1
    allow_append.set()
    final = advisor.shutdown_mode5_trace_writer(timeout_sec=2)
    assert final["pending_unpersisted"] == 0
    assert final["append_successes"] == 1


def test_mode5_trace_queue_full_rolls_back_pending_reservation(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "trace-pending-rollback.json"), enable_stdout=False,
        mode5_trace_queue_capacity=1,
    )
    advisor.decision_trace_path = tmp_path / "trace-pending-rollback.jsonl"
    append_started = threading.Event()
    release_append = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def blocking_append(serialized):
        append_started.set()
        assert release_append.wait(timeout=4)
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = blocking_append

    def enqueue(reason):
        return advisor._enqueue_mode5_trace_record(
            {"event_type": "MODE5_DECISION_TRACE", "index_name": "NIFTY", "reason": reason},
            dedup_key=None,
        )

    assert enqueue("ACTIVE_WRITER")
    assert append_started.wait(timeout=2)
    assert enqueue("QUEUED_ITEM")
    before = advisor.get_mode5_trace_health()
    assert before["pending_unpersisted"] == 2
    assert before["enqueued"] == 2
    assert before["queue_depth"] == 1

    assert not enqueue("FULL_QUEUE_DROP")
    after = advisor.get_mode5_trace_health()
    assert after["pending_unpersisted"] == before["pending_unpersisted"]
    assert after["enqueued"] == before["enqueued"]
    assert after["queue_full_drops"] == before["queue_full_drops"] + 1
    assert after["queue_depth"] == 1

    release_append.set()
    final = advisor.shutdown_mode5_trace_writer(timeout_sec=3)
    assert final["pending_unpersisted"] == 0
    assert final["append_successes"] == 2


def test_mode5_trace_explicit_shutdown_is_idempotent_and_unregisters_atexit(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-close-callback.json"), enable_stdout=False)
    callback = advisor._mode5_trace_atexit_callback
    assert callback is not None
    removed = []
    original_unregister = advisor_module.atexit.unregister

    def record_unregister(function):
        removed.append(function)
        return original_unregister(function)

    monkeypatch.setattr(advisor_module.atexit, "unregister", record_unregister)
    first = advisor.shutdown_mode5_trace_writer(timeout_sec=2)
    second = advisor.shutdown_mode5_trace_writer(timeout_sec=2)
    assert first["writer_status"] == second["writer_status"] == "STOPPED"
    assert advisor._mode5_trace_writer.is_alive() is False
    assert callback in removed
    assert advisor._mode5_trace_atexit_callback is None


def test_mode5_generic_decision_trace_deduplicates_per_candidate_reason(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-generic-dedup.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-generic-dedup.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    _, metadata = _seed_quote_trace_candidate(advisor, boundary)
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "MODE5_OR_REJECTED",
        details={"first_quote": "representative"}, timestamp_ms=metadata.boundary_timestamp_ms,
        candidate_generation=metadata.generation,
    )
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "MODE5_OR_REJECTED",
        details={"second_quote": "coalesced"}, timestamp_ms=metadata.boundary_timestamp_ms,
        candidate_generation=metadata.generation,
    )
    _wait_for_mode5_trace_idle(advisor)
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "MODE5_OR_REJECTED",
        details={"later_quote": "deduped"}, timestamp_ms=metadata.boundary_timestamp_ms,
        candidate_generation=metadata.generation,
    )
    assert advisor.get_mode5_trace_health()["enqueued"] == 1
    records = _read_mode5_trace_records(advisor)
    assert len(records) == 1
    assert records[0]["details"] == {"first_quote": "representative"}
    assert records[0]["candidate_generation"] == metadata.generation


def test_mode5_trace_run_id_disambiguates_advisors_sharing_append_path(tmp_path: Path):
    shared_path = tmp_path / "shared-advisor-trace.jsonl"
    first = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "shared-first.json"), enable_stdout=False)
    second = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "shared-second.json"), enable_stdout=False)
    first.decision_trace_path = shared_path
    second.decision_trace_path = shared_path
    event_time = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    timestamp_ms = int(event_time.timestamp() * 1000)

    for advisor in (first, second):
        advisor.log_decision_trace(
            "NIFTY", event_time.time(), "ABSTAIN", "SHARED_PATH_REASON",
            timestamp_ms=timestamp_ms,
        )
        _wait_for_mode5_trace_idle(advisor)

    rows = [json.loads(line) for line in shared_path.read_text().splitlines()]
    assert len(rows) == 2
    assert [row["trace_sequence"] for row in rows] == [1, 1]
    for row in rows:
        uuid.UUID(row["trace_run_id"])
    identities = {(row["trace_run_id"], row["trace_sequence"]) for row in rows}
    assert len(identities) == 2
    assert rows[0]["trace_run_id"] != rows[1]["trace_run_id"]


def test_mode5_trace_persisted_read_requires_run_id_and_sequence_on_shared_file(tmp_path: Path):
    shared_path = tmp_path / "shared-target-trace.jsonl"
    target = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "target-advisor.json"), enable_stdout=False)
    other = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "other-advisor.json"), enable_stdout=False)
    target.decision_trace_path = shared_path
    other.decision_trace_path = shared_path
    event_time = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    timestamp_ms = int(event_time.timestamp() * 1000)

    other.log_decision_trace(
        "NIFTY", event_time.time(), "ABSTAIN", "OTHER_RUN_SEQUENCE_ONE",
        timestamp_ms=timestamp_ms,
    )
    _wait_for_mode5_trace_idle(other)

    original_append = target._append_decision_trace_record_locked
    attempts = []

    def fail_target_sequence_one_then_append(serialized):
        attempts.append(serialized)
        if len(attempts) <= 2:
            return False
        return original_append(serialized)

    target._append_decision_trace_record_locked = fail_target_sequence_one_then_append
    target.log_decision_trace(
        "NIFTY", event_time.time(), "ABSTAIN", "TARGET_RUN_SEQUENCE_ONE_FAILED",
        timestamp_ms=timestamp_ms,
    )
    target.log_decision_trace(
        "NIFTY", event_time.time(), "ABSTAIN", "TARGET_RUN_SEQUENCE_TWO_PERSISTED",
        timestamp_ms=timestamp_ms,
    )
    health = _wait_for_mode5_trace_expected_failures(target, 2, 2)
    assert health["last_persisted_sequence"] == 2
    assert target.trace_run_id != other.trace_run_id

    with pytest.raises(AssertionError, match="target identity is absent.*target_sequence=1"):
        _read_mode5_trace_records(
            target, allow_unpersisted=True, expected_append_failures=2,
            target_sequence=1,
        )
    rows = _read_mode5_trace_records(
        target, allow_unpersisted=True, expected_append_failures=2,
        target_sequence=2,
    )
    assert any(
        row["trace_run_id"] == other.trace_run_id and row["trace_sequence"] == 1
        for row in rows
    )
    assert any(
        row["trace_run_id"] == target.trace_run_id and row["trace_sequence"] == 2
        for row in rows
    )


def test_mode5_trace_writer_start_failure_is_visible_and_decision_neutral(tmp_path: Path, monkeypatch):
    original_start = threading.Thread.start

    def fail_mode5_writer(thread):
        if thread.name.startswith("Mode5TraceWriter-"):
            raise RuntimeError("writer unavailable")
        return original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", fail_mode5_writer)
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-start-failure.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-start-failure.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "WRITER_START_FAILURE",
        timestamp_ms=metadata.boundary_timestamp_ms, candidate_generation=metadata.generation,
    )
    health = advisor.get_mode5_trace_health()
    assert health["writer_status"] == "FAILED"
    assert health["writer_unavailable_drops"] == 1
    assert health["degraded"] is True
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"
    assert not advisor.decision_trace_path.exists()


def test_mode5_quote_suppression_deduplicates_across_instruments_but_separates_reason_and_generation(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-keys.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-keys.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth_a = _make_dummy_depth(ts_ms=metadata.boundary_timestamp_ms - 1, ingress_ns=metadata.issued_monotonic_ns + 1)
    depth_b = _make_dummy_depth(
        token="NSE_FO|NIFTY26NOV24150CE", ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1, sequence_id=2,
    )
    reason_a = "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"
    reason_b = "MODE5_QUOTE_INGRESS_BEFORE_CANDIDATE_ISSUE"
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, metadata, depth_a, reason_a, metadata.boundary_timestamp_ms
    )
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, metadata, depth_a, reason_b, metadata.boundary_timestamp_ms
    )
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|NIFTY26NOV24150CE", signal, metadata, depth_b, reason_a, metadata.boundary_timestamp_ms
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, metadata.boundary_timestamp_ms // 300_000)
    next_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert next_metadata.generation != metadata.generation
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, next_metadata, depth_a, reason_a,
        metadata.boundary_timestamp_ms,
    )
    _wait_for_mode5_trace_idle(advisor)
    assert all(key[1] != "NIFTY" or key[2] == next_metadata.generation
               for key in advisor._mode5_quote_trace_emitted)
    records = _read_mode5_trace_records(advisor)
    assert len(records) == 3
    assert records[0]["canonical_instrument"] == "NSE_FO|45408"
    assert records[0]["quote_exchange_timestamp_ms"] == depth_a.exchange_timestamp_ms
    assert records[1]["reason"] == reason_b
    assert records[2]["candidate_generation"] == next_metadata.generation


def test_mode5_quote_trace_failure_circuit_is_bounded_across_tokens_and_resets(tmp_path: Path, caplog):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-circuit.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-circuit.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    reason_a = "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"
    reason_b = "MODE5_QUOTE_INGRESS_BEFORE_CANDIDATE_ISSUE"
    calls = []
    advisor._append_decision_trace_record_locked = lambda serialized: calls.append(serialized) or False
    tokens = [f"NSE_FO|TOKEN-{i}" for i in range(12)]
    outcomes = []
    barrier = threading.Barrier(len(tokens))

    def enqueue_same_reason(token):
        token_depth = _make_dummy_depth(
            token=token,
            ts_ms=metadata.boundary_timestamp_ms - 1,
            ingress_ns=metadata.issued_monotonic_ns + 1,
        )
        barrier.wait(timeout=3)
        outcomes.append(advisor._emit_mode5_quote_suppression(
            "NIFTY", token, signal, metadata, token_depth, reason_a,
            metadata.boundary_timestamp_ms,
        ))

    workers = [threading.Thread(target=enqueue_same_reason, args=(token,)) for token in tokens]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)
    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == len(tokens) - 1
    assert advisor.get_mode5_trace_health()["enqueued"] == 1
    assert _wait_for_mode5_trace_expected_failures(
        advisor, advisor._mode5_quote_trace_sequence, 2
    )["append_failures"] == 2
    assert len(calls) == 2

    # One completed failure circuit per reason; later instruments cannot churn it.
    for reason in (reason_a, reason_b):
        for token in tokens:
            accepted = advisor._emit_mode5_quote_suppression(
                "NIFTY", token, signal, metadata, depth, reason,
                metadata.boundary_timestamp_ms,
            )
            if reason == reason_a:
                assert not accepted
    assert _wait_for_mode5_trace_expected_failures(
        advisor, advisor._mode5_quote_trace_sequence, 4
    )["append_failures"] == 4
    assert len(calls) == 4
    assert advisor.get_mode5_trace_health()["degraded"] is True
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"

    old_metadata = metadata
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, metadata.boundary_timestamp_ms // 300_000)
    new_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert new_metadata.generation != old_metadata.generation
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", tokens[0], signal, old_metadata, depth, reason_a,
        metadata.boundary_timestamp_ms,
    )
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", tokens[0], signal, new_metadata, depth, reason_a,
        new_metadata.boundary_timestamp_ms,
    )
    assert _wait_for_mode5_trace_expected_failures(
        advisor, advisor._mode5_quote_trace_sequence, 6
    )["append_failures"] == 6
    assert len(calls) == 6


def test_mode5_quote_trace_inflight_coalesces_failure_then_allows_single_retry(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-coalesce.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-coalesce.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    entered_append = threading.Event()
    allow_append = threading.Event()
    write_calls = []
    original_append = advisor._append_decision_trace_record_locked

    def fail_first_append_then_write(record):
        assert not advisor._lock._is_owned()
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        assert not advisor._decision_trace_lock.acquire(blocking=False)
        write_calls.append(record)
        if len(write_calls) == 1:
            entered_append.set()
            assert allow_append.wait(timeout=3)
            return False
        return original_append(record)

    advisor._append_decision_trace_record_locked = fail_first_append_then_write
    accepted = advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )
    assert entered_append.wait(timeout=2)
    # A different token with the same candidate/reason coalesces while the first
    # write is waiting in the append-only critical section.
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|OTHER", signal, metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )
    assert len(write_calls) == 1
    allow_append.set()
    assert accepted is True
    _wait_for_mode5_trace_idle(advisor)
    assert len(write_calls) == 2
    rows = _read_mode5_trace_records(advisor)
    assert len(rows) == 1
    assert rows[0]["canonical_instrument"] == "NSE_FO|45408"
    assert advisor._mode5_quote_trace_attempts[
        (metadata.session_day.isoformat(), "NIFTY", metadata.generation, "MODE5_QUOTE_BEFORE_BAR_BOUNDARY")
    ] == 2


def test_mode5_quote_trace_inflight_coalesces_concurrent_success(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-coalesce-success.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-coalesce-success.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    append_entered = threading.Event()
    release_append = threading.Event()
    write_calls = []
    original_append = advisor._append_decision_trace_record_locked

    def blocked_success(record):
        assert not advisor._lock._is_owned()
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        assert not advisor._decision_trace_lock.acquire(blocking=False)
        write_calls.append(record)
        append_entered.set()
        assert release_append.wait(timeout=3)
        return original_append(record)

    advisor._append_decision_trace_record_locked = blocked_success
    outcomes = []
    worker = threading.Thread(target=lambda: outcomes.append(advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|FIRST", signal, metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )))
    worker.start()
    assert append_entered.wait(timeout=2)
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|SECOND", signal, metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )
    assert len(write_calls) == 1
    release_append.set()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert outcomes == [True]
    rows = _read_mode5_trace_records(advisor)
    assert len(rows) == 1
    assert rows[0]["canonical_instrument"] == "NSE_FO|FIRST"


def test_mode5_quote_trace_append_does_not_block_candidate_replacement_and_keeps_sequence(
    tmp_path: Path,
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-replace-during-append.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-replace-during-append.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, old_metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=old_metadata.boundary_timestamp_ms - 1,
        ingress_ns=old_metadata.issued_monotonic_ns + 1,
    )
    append_entered = threading.Event()
    release_append = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def block_first_append(record):
        assert not advisor._lock._is_owned()
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        assert not advisor._decision_trace_lock.acquire(blocking=False)
        decoded = json.loads(record)
        if decoded["candidate_generation"] == old_metadata.generation:
            append_entered.set()
            assert release_append.wait(timeout=4)
        return original_append(record)

    advisor._append_decision_trace_record_locked = block_first_append
    outcomes = {}
    old_thread = threading.Thread(target=lambda: outcomes.setdefault("old", advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|OLD", signal, old_metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", old_metadata.boundary_timestamp_ms,
    )))
    old_thread.start()
    assert append_entered.wait(timeout=2)

    # Lifecycle state operations remain available while a trace append is blocked.
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, old_metadata.boundary_timestamp_ms // 300_000)
    new_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert new_metadata.generation != old_metadata.generation
    with advisor._mode5_quote_trace_state_lock:
        assert advisor._mode5_quote_trace_active_generation["NIFTY"] == new_metadata.generation
        assert not advisor._mode5_quote_trace_emitted

    new_thread = threading.Thread(target=lambda: outcomes.setdefault("new", advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|NEW", signal, new_metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", new_metadata.boundary_timestamp_ms,
    )))
    new_thread.start()
    key = (new_metadata.session_day.isoformat(), "NIFTY", new_metadata.generation,
           "MODE5_QUOTE_BEFORE_BAR_BOUNDARY")
    for _ in range(100):
        with advisor._mode5_quote_trace_state_lock:
            if key in advisor._mode5_quote_trace_inflight:
                break
        time.sleep(0.005)
    else:
        pytest.fail("new-generation append reservation was not published")

    release_append.set()
    old_thread.join(timeout=4)
    new_thread.join(timeout=4)
    assert not old_thread.is_alive() and not new_thread.is_alive()
    assert outcomes == {"old": True, "new": True}
    rows = _read_mode5_trace_records(advisor)
    assert [row["candidate_generation"] for row in rows] == [old_metadata.generation, new_metadata.generation]
    assert [row["trace_sequence"] for row in rows] == [1, 2]
    assert len(rows) == 2
    with advisor._mode5_quote_trace_state_lock:
        assert advisor._mode5_quote_trace_emitted == {key}
        assert advisor._mode5_quote_trace_attempts == {key: 1}
        assert advisor._mode5_quote_trace_inflight == {}


def test_mode5_append_stall_does_not_hold_lock_while_deferred_decision_waits(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-deferred-contention.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-deferred-contention.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, old_metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=old_metadata.boundary_timestamp_ms - 1,
        ingress_ns=old_metadata.issued_monotonic_ns + 1,
    )
    mode5_append_entered = threading.Event()
    deferred_staged = threading.Event()
    release_append = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def block_mode5_record(record):
        assert not advisor._lock._is_owned()
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        if json.loads(record)["event_type"] == "MODE5_QUOTE_SUPPRESSED":
            mode5_append_entered.set()
            assert release_append.wait(timeout=4)
        return original_append(record)

    advisor._append_decision_trace_record_locked = block_mode5_record
    results = {}

    def emit_suppression():
        results["mode5"] = advisor._emit_mode5_quote_suppression(
            "NIFTY", "NSE_FO|MODE5", signal, old_metadata, depth,
            "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", old_metadata.boundary_timestamp_ms,
        )

    def defer_ordinary_trace():
        details = {"snapshot": [1, 2]}
        with advisor._lock:
            advisor._defer_mode5_decision_trace_locked(
                "NIFTY", boundary.time(), "ABSTAIN", "ORDINARY_MODE5_VETO",
                details=details, timestamp_ms=old_metadata.boundary_timestamp_ms,
                candidate_generation=old_metadata.generation,
            )
            details["snapshot"].append(3)
            deferred_staged.set()
        results["deferred"] = True

    mode5_thread = threading.Thread(target=emit_suppression)
    mode5_thread.start()
    assert mode5_append_entered.wait(timeout=2)
    deferred_thread = threading.Thread(target=defer_ordinary_trace)
    deferred_thread.start()
    assert deferred_staged.wait(timeout=2)

    deferred_thread.join(timeout=2)
    assert not deferred_thread.is_alive()
    # The deferred ordinary record is queued while its worker is blocked; advisor
    # state replacement remains available before that writer unblocks.
    with advisor._lock:
        advisor._cache_rbfn_signal_locked(
            "NIFTY", signal, old_metadata.boundary_timestamp_ms // 300_000
        )
    new_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert new_metadata.generation != old_metadata.generation
    assert advisor.get_mode5_trace_health()["queue_depth"] >= 1

    release_append.set()
    mode5_thread.join(timeout=4)
    deferred_thread.join(timeout=4)
    assert not mode5_thread.is_alive() and not deferred_thread.is_alive()
    assert results == {"mode5": True, "deferred": True}
    records = _read_mode5_trace_records(advisor)
    assert [row["event_type"] for row in records] == [
        "MODE5_QUOTE_SUPPRESSED", "MODE5_DECISION_TRACE"
    ]
    assert [row["trace_sequence"] for row in records] == [1, 2]
    assert records[1]["candidate_generation"] == old_metadata.generation
    assert records[1]["reason"] == "ORDINARY_MODE5_VETO"
    assert records[1]["details"] == {"snapshot": [1, 2]}
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == new_metadata.generation


def test_deferred_mode5_trace_failure_does_not_change_candidate_or_entry_state(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-deferred-fail.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-deferred-fail.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)

    def fail_append(record):
        assert not advisor._lock._is_owned()
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        return False

    advisor._append_decision_trace_record_locked = fail_append
    details = {"mutable": [1]}
    with advisor._lock:
        advisor._defer_mode5_decision_trace_locked(
            "NIFTY", boundary.time(), "ABSTAIN", "DEFERRED_WRITE_FAILURE",
            details=details, timestamp_ms=metadata.boundary_timestamp_ms,
            candidate_generation=metadata.generation,
        )
        details["mutable"].append(2)
    health = _wait_for_mode5_trace_expected_failures(
        advisor, advisor._mode5_quote_trace_sequence, 2
    )

    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == metadata.generation
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"
    assert health["append_failures"] == 2
    key = (metadata.session_day.isoformat(), "NIFTY", metadata.generation, "DEFERRED_WRITE_FAILURE")
    assert key in advisor._mode5_quote_trace_dropped
    assert advisor.get_mode5_trace_health()["pending_unpersisted"] == 1


def test_five_minute_trace_flush_waits_for_outermost_advisor_lock(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-five-minute-deferred.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-five-minute-deferred.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)

    def stage_from_locked_bar(*args, **kwargs):
        advisor._defer_mode5_decision_trace_locked(
            "NIFTY", boundary.time(), signal.action, signal.setup_reason,
            details={"candidate": "snapshot"}, timestamp_ms=metadata.boundary_timestamp_ms,
            candidate_generation=metadata.generation,
        )
        return signal

    monkeypatch.setattr(advisor, "_on_5m_bar_close_locked", stage_from_locked_bar)
    with advisor._lock:
        assert advisor._on_5m_bar_close(
            "NIFTY", 100, 101, 99, 100, 1, boundary.time(),
            metadata.boundary_timestamp_ms, metadata.boundary_timestamp_ms // 300_000 - 1,
            decision_available_at_ms=metadata.boundary_timestamp_ms + 1,
        ) is signal
        assert advisor.get_mode5_trace_health()["enqueued"] == 1
    rows = _read_mode5_trace_records(advisor)
    assert len(rows) == 1
    assert rows[0]["candidate_generation"] == metadata.generation
    assert rows[0]["trace_sequence"] == 1


def test_reserved_dispatch_finishes_before_deferred_append_and_state_stays_available(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-after-dispatch.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-after-dispatch.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    append_started = threading.Event()
    append_release = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def blocking_append(serialized):
        assert not advisor._lock._is_owned()
        assert advisor._mode5_quote_trace_state_lock.acquire(blocking=False)
        advisor._mode5_quote_trace_state_lock.release()
        append_started.set()
        assert append_release.wait(timeout=4)
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = blocking_append
    with advisor._lock:
        advisor._defer_mode5_decision_trace_locked(
            "NIFTY", boundary.time(), "ABSTAIN", "POST_RESERVATION_TRACE",
            details={"reservation": "accepted"}, timestamp_ms=metadata.boundary_timestamp_ms,
            candidate_generation=metadata.generation,
        )
        assert advisor._consume_cached_rbfn_candidate_locked(
            "NIFTY", metadata.generation, "RESERVATION_ACCEPTED"
        )

    assert append_started.wait(timeout=2)
    callback_completed = threading.Event()

    def mock_dispatcher(**request):
        assert not advisor._lock._is_owned()
        assert request == {"intent_id": "mock-intent"}
        callback_completed.set()

    advisor.automated_dispatcher = SimpleNamespace(on_apm_entry=mock_dispatcher)
    advisor._dispatch_reserved_entry_then_flush_traces({"intent_id": "mock-intent"})
    assert callback_completed.is_set()
    assert append_started.is_set()

    state_read = threading.Event()

    def read_consumed_state():
        with advisor._lock:
            assert advisor.cached_rbfn_signals["NIFTY"] is None
            assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "RESERVATION_ACCEPTED"
            advisor.spots["NIFTY"] = 25_200.0
        state_read.set()

    state_thread = threading.Thread(target=read_consumed_state)
    state_thread.start()
    assert state_read.wait(timeout=2), "advisor state remained blocked by trace append"
    assert advisor.spots["NIFTY"] == 25_200.0

    append_release.set()
    health = _wait_for_mode5_trace_quiescent(advisor)
    state_thread.join(timeout=2)
    assert not state_thread.is_alive()
    assert health["append_successes"] == 1
    rows = _read_mode5_trace_records(advisor)
    assert len(rows) == 1
    assert rows[0]["candidate_generation"] == metadata.generation


def test_dispatch_exception_and_no_callback_leave_traces_to_bounded_writer(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-dispatch-finally.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-dispatch-finally.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    with advisor._lock:
        advisor._defer_mode5_decision_trace_locked(
            "NIFTY", boundary.time(), "ABSTAIN", "DISPATCH_EXCEPTION_TRACE",
            timestamp_ms=metadata.boundary_timestamp_ms, candidate_generation=metadata.generation,
        )

    advisor.automated_dispatcher = SimpleNamespace(
        on_apm_entry=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("mock callback failure"))
    )
    with pytest.raises(RuntimeError, match="mock callback failure"):
        advisor._dispatch_reserved_entry_then_flush_traces({"intent_id": "mock-intent"})
    assert advisor.get_mode5_trace_health()["enqueued"] == 1
    assert len(_read_mode5_trace_records(advisor)) == 1

    with advisor._lock:
        advisor._defer_mode5_decision_trace_locked(
            "NIFTY", boundary.time(), "ABSTAIN", "NO_CALLBACK_TRACE",
            timestamp_ms=metadata.boundary_timestamp_ms, candidate_generation=metadata.generation,
        )
    advisor._dispatch_reserved_entry_then_flush_traces(None)
    assert advisor.get_mode5_trace_health()["enqueued"] == 2
    assert len(_read_mode5_trace_records(advisor)) == 2


def test_mode5_quote_suppression_old_generation_cannot_emit_and_failed_append_retries(
    tmp_path: Path, monkeypatch, caplog
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-retry.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-retry.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    old_signal, old_metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=old_metadata.boundary_timestamp_ms - 1,
        ingress_ns=old_metadata.issued_monotonic_ns + 1,
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", old_signal, old_metadata.boundary_timestamp_ms // 300_000)
    new_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", old_signal, old_metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", new_metadata.boundary_timestamp_ms,
    )
    assert not advisor.decision_trace_path.exists()

    new_signal = advisor.cached_rbfn_signals["NIFTY"]
    original_open = open
    def fail_open(*args, **kwargs):
        raise OSError("trace unavailable")

    caplog.set_level("ERROR", logger="core.sentinel_live_stream_advisor")
    monkeypatch.setattr("builtins.open", fail_open)
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", new_signal, new_metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", new_metadata.boundary_timestamp_ms,
    )
    health = _wait_for_mode5_trace_expected_failures(
        advisor, advisor._mode5_quote_trace_sequence, 2
    )
    assert advisor.cached_rbfn_signals["NIFTY"] is new_signal
    assert not advisor._mode5_quote_trace_emitted
    assert health["append_failures"] == 2
    assert health["degraded"]
    assert any("Mode5 trace append exhausted retries" in row.message for row in caplog.records)
    monkeypatch.setattr("builtins.open", original_open)
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", new_signal, new_metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", new_metadata.boundary_timestamp_ms,
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", new_signal, new_metadata.boundary_timestamp_ms // 300_000)
    reopened_meta = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", new_signal, reopened_meta, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", reopened_meta.boundary_timestamp_ms,
    )
    assert len(_read_mode5_trace_records(
        advisor, allow_unpersisted=True, expected_append_failures=2,
        target_sequence=advisor._mode5_quote_trace_sequence,
    )) == 1


def test_mode5_trace_append_exception_retries_clears_stale_reservation_and_continues(
    tmp_path: Path,
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-raise-retry.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-raise-retry.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    old_signal, old_metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=old_metadata.boundary_timestamp_ms - 1,
        ingress_ns=old_metadata.issued_monotonic_ns + 1,
    )
    append_started = threading.Event()
    release_first_append = threading.Event()
    write_calls = []
    original_append = advisor._append_decision_trace_record_locked

    def raise_twice_then_append(serialized):
        write_calls.append(serialized)
        if len(write_calls) == 1:
            append_started.set()
            assert release_first_append.wait(timeout=4)
        if len(write_calls) <= 2:
            raise OSError("mock trace disk failure")
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = raise_twice_then_append
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|OLD", old_signal, old_metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", old_metadata.boundary_timestamp_ms,
    )
    assert append_started.wait(timeout=2)

    # Supersede the old candidate while its first append attempt is blocked.
    with advisor._lock:
        advisor._cache_rbfn_signal_locked(
            "NIFTY", old_signal, old_metadata.boundary_timestamp_ms // 300_000
        )
    new_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert new_metadata.generation != old_metadata.generation
    advisor.log_decision_trace(
        "NIFTY", boundary.time(), "ABSTAIN", "NEW_GENERATION_RECORD",
        timestamp_ms=new_metadata.boundary_timestamp_ms,
        candidate_generation=new_metadata.generation,
    )

    release_first_append.set()
    health = _wait_for_mode5_trace_expected_failures(
        advisor, advisor._mode5_quote_trace_sequence, 2
    )
    assert health["append_failures"] == 2
    assert health["append_successes"] == 1
    assert health["pending_unpersisted"] == 1
    assert health["writer_status"] == "RUNNING"
    assert advisor._mode5_trace_writer.is_alive()
    old_key = (
        old_metadata.session_day.isoformat(), "NIFTY", old_metadata.generation,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY",
    )
    assert old_key not in advisor._mode5_quote_trace_inflight
    assert old_key not in advisor._mode5_quote_trace_attempts
    assert old_key not in advisor._mode5_quote_trace_dropped
    new_key = (
        new_metadata.session_day.isoformat(), "NIFTY", new_metadata.generation,
        "NEW_GENERATION_RECORD",
    )
    assert new_key in advisor._mode5_quote_trace_emitted
    assert len(write_calls) == 3
    # A later persisted high-water mark must not disguise missing sequence 1.
    with pytest.raises(AssertionError, match="target identity is absent.*target_sequence=1"):
        _read_mode5_trace_records(
            advisor, allow_unpersisted=True, expected_append_failures=2,
            target_sequence=1,
        )
    records = _read_mode5_trace_records(
        advisor, allow_unpersisted=True, expected_append_failures=2,
        target_sequence=advisor._mode5_quote_trace_sequence,
    )
    assert len(records) == 1
    assert records[0]["reason"] == "NEW_GENERATION_RECORD"
    assert records[0]["candidate_generation"] == new_metadata.generation


def test_mode5_trace_worker_finalizes_unexpected_item_exception_and_processes_next(
    tmp_path: Path,
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-worker-finalizer.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-worker-finalizer.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    old_signal, old_metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=old_metadata.boundary_timestamp_ms - 1,
        ingress_ns=old_metadata.issued_monotonic_ns + 1,
    )
    second_item_started = threading.Event()
    release_second_item = threading.Event()
    original_persist = advisor._persist_mode5_trace_item
    reason_a = "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"
    reason_b = "MODE5_QUOTE_INGRESS_BEFORE_CANDIDATE_ISSUE"
    old_key_a = (old_metadata.session_day.isoformat(), "NIFTY", old_metadata.generation, reason_a)
    old_key_b = (old_metadata.session_day.isoformat(), "NIFTY", old_metadata.generation, reason_b)

    def inject_unexpected_failures(item):
        if item.dedup_key == old_key_a:
            raise RuntimeError("synthetic worker finalizer failure")
        if item.dedup_key == old_key_b:
            second_item_started.set()
            assert release_second_item.wait(timeout=4)
            raise RuntimeError("synthetic stale completion failure")
        return original_persist(item)

    advisor._persist_mode5_trace_item = inject_unexpected_failures
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|A", old_signal, old_metadata, depth, reason_a,
        old_metadata.boundary_timestamp_ms,
    )
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|B", old_signal, old_metadata, depth, reason_b,
        old_metadata.boundary_timestamp_ms,
    )
    assert second_item_started.wait(timeout=2)
    assert advisor.get_mode5_trace_health()["append_failures"] == 1
    assert old_key_a in advisor._mode5_quote_trace_dropped
    assert old_key_a not in advisor._mode5_quote_trace_inflight

    try:
        with advisor._lock:
            advisor._cache_rbfn_signal_locked(
                "NIFTY", old_signal, old_metadata.boundary_timestamp_ms // 300_000
            )
        new_metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
        assert new_metadata.generation != old_metadata.generation
        advisor.log_decision_trace(
            "NIFTY", boundary.time(), "ABSTAIN", "AFTER_UNEXPECTED_EXCEPTION",
            timestamp_ms=new_metadata.boundary_timestamp_ms,
            candidate_generation=new_metadata.generation,
        )
        target_sequence = advisor._mode5_quote_trace_sequence
    finally:
        release_second_item.set()

    health = _wait_for_mode5_trace_expected_failures(advisor, target_sequence, 2)
    assert health["append_failures"] == 2
    assert health["last_processed_sequence"] >= target_sequence
    assert health["last_persisted_sequence"] >= target_sequence
    assert health["pending_unpersisted"] == 2
    assert health["writer_status"] == "RUNNING"
    assert advisor._mode5_trace_writer.is_alive()
    for stale_key in (old_key_a, old_key_b):
        assert stale_key not in advisor._mode5_quote_trace_inflight
        assert stale_key not in advisor._mode5_quote_trace_attempts
        assert stale_key not in advisor._mode5_quote_trace_dropped
    rows = _read_mode5_trace_records(
        advisor, allow_unpersisted=True, expected_append_failures=2,
        target_sequence=target_sequence,
    )
    assert len(rows) == 1
    assert rows[0]["reason"] == "AFTER_UNEXPECTED_EXCEPTION"
    assert rows[0]["candidate_generation"] == new_metadata.generation


def test_mode5_quote_suppression_dedup_state_clears_on_candidate_lifecycle(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-clear.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-clear.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(ts_ms=metadata.boundary_timestamp_ms - 1, ingress_ns=metadata.issued_monotonic_ns + 1)
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, metadata, depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )
    _wait_for_mode5_trace_idle(advisor)
    assert len(advisor._mode5_quote_trace_emitted) == 1
    with advisor._lock:
        advisor._clear_cached_rbfn_candidate_locked("NIFTY", "TEST_CLEARED")
    assert advisor._mode5_quote_trace_emitted == set()
    assert advisor._mode5_quote_trace_attempts == {}
    assert advisor._mode5_quote_trace_active_generation["NIFTY"] is None


def test_mode5_quote_suppression_consumption_clears_keys_and_blocks_captured_snapshot(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-consume.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-consume.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    reason = "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, metadata, depth, reason, metadata.boundary_timestamp_ms
    )
    _wait_for_mode5_trace_idle(advisor)
    assert len(advisor._mode5_quote_trace_emitted) == 1
    with advisor._lock:
        assert advisor._consume_cached_rbfn_candidate_locked(
            "NIFTY", metadata.generation, "RESERVATION_ACCEPTED"
        )
    assert advisor._mode5_quote_trace_emitted == set()
    assert advisor._mode5_quote_trace_attempts == {}
    assert advisor._mode5_quote_trace_active_generation["NIFTY"] is None
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|45408", signal, metadata, depth, reason, metadata.boundary_timestamp_ms + 1
    )
    assert len(_read_mode5_trace_records(advisor)) == 1


def test_mode5_quote_trace_state_clears_on_expiry_and_session_rollover(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "trace-expiry-rollover.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace-expiry-rollover.jsonl"
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ZoneInfo("Asia/Kolkata"))
    session_day = boundary.date()
    with advisor._lock:
        advisor._reset_rp2_state_for_session_locked("NIFTY", session_day)

    signal, metadata = _seed_quote_trace_candidate(advisor, boundary)
    depth = _make_dummy_depth(
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    reason = "MODE5_QUOTE_BEFORE_BAR_BOUNDARY"
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|EXPIRY", signal, metadata, depth, reason,
        metadata.boundary_timestamp_ms,
    )
    _wait_for_mode5_trace_idle(advisor)
    with advisor._lock:
        assert advisor._candidate_snapshot_locked(
            "NIFTY", now_ns=metadata.issued_monotonic_ns + 300_000_000_001
        ) == (None, None)
    assert advisor._mode5_quote_trace_emitted == set()
    assert advisor._mode5_quote_trace_attempts == {}
    assert advisor._mode5_quote_trace_inflight == {}
    assert advisor._mode5_quote_trace_active_generation["NIFTY"] is None

    next_signal, next_metadata = _seed_quote_trace_candidate(advisor, boundary)
    assert advisor._emit_mode5_quote_suppression(
        "NIFTY", "NSE_FO|ROLLOVER", next_signal, next_metadata, depth, reason,
        next_metadata.boundary_timestamp_ms,
    )
    _wait_for_mode5_trace_idle(advisor)
    with advisor._lock:
        assert advisor._reset_rp2_state_for_session_locked("NIFTY", session_day + timedelta(days=1))
    assert advisor._mode5_quote_trace_emitted == set()
    assert advisor._mode5_quote_trace_attempts == {}
    assert advisor._mode5_quote_trace_inflight == {}
    assert advisor._mode5_quote_trace_active_generation["NIFTY"] is None


def test_mode5_generation_recheck_blocks_superseded_quote_and_old_consume(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "candidate-generation.json"), enable_stdout=False)
    ist = ZoneInfo("Asia/Kolkata")
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ist)
    boundary_ms = int(boundary.timestamp() * 1000)
    now_wall_ms = boundary_ms + 500
    clock_ns = [20_000_000_000]
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: clock_ns[0])
    old_signal = CachedRBFNAuctionSignal(
        timestamp_ms=boundary_ms - 100,
        index_name="NIFTY", action="BUY_CALL", direction="CE", target_strike=25400.0,
        target_pts=30.0, sl_pts=15.0, setup_reason="OLD_CANDIDATE",
        trade_phase="MIDDAY_REVERSAL", bar_time=dt_time(11, 35), is_active=True,
    )
    old_epoch = boundary_ms // 300_000 - 1
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", old_signal, old_epoch)
    old_generation = advisor._cached_rbfn_candidate_meta["NIFTY"].generation
    old_issue_ns = advisor._cached_rbfn_candidate_meta["NIFTY"].issued_monotonic_ns
    depth = _make_dummy_depth(
        ts_ms=boundary_ms + 100, ingress_ns=old_issue_ns + 100_000_000
    )
    identity = advisor._option_quote_identity(
        "NIFTY", depth, wall_now_ms=now_wall_ms, monotonic_now_ns=old_issue_ns + 500_000_000
    )
    assert identity[0]
    assert advisor._record_option_depth_order("NIFTY", identity[2], identity[3], identity[4])

    new_boundary_ms = boundary_ms + 300_000
    new_signal = CachedRBFNAuctionSignal(
        timestamp_ms=new_boundary_ms - 100,
        index_name="NIFTY", action="BUY_PUT", direction="PE", target_strike=25350.0,
        target_pts=30.0, sl_pts=15.0, setup_reason="NEW_CANDIDATE",
        trade_phase="MIDDAY_REVERSAL", bar_time=dt_time(11, 40), is_active=True,
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", new_signal, new_boundary_ms // 300_000 - 1)
        authorized, reason = advisor._final_candidate_authorization_locked(
            "NIFTY", old_generation, depth, identity[2], identity[3], identity[4], old_issue_ns + 500_000_000
        )
        old_clear = advisor._consume_cached_rbfn_candidate_locked(
            "NIFTY", old_generation, "OLD_COMPLETION"
        )
    assert not authorized
    assert reason == "MODE5_CANDIDATE_SUPERSEDED_OR_EXPIRED"
    assert not old_clear
    assert advisor.cached_rbfn_signals["NIFTY"] is new_signal


def test_mode5_concurrent_quote_reserves_candidate_once(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "candidate-once.json"), enable_stdout=False)
    ist = ZoneInfo("Asia/Kolkata")
    boundary = datetime(2026, 11, 18, 11, 35, tzinfo=ist)
    boundary_ms = int(boundary.timestamp() * 1000)
    now_wall_ms = boundary_ms + 500
    clock_ns = [30_000_000_000]
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: clock_ns[0])
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=boundary_ms - 100,
        index_name="NIFTY", action="BUY_CALL", direction="CE", target_strike=25400.0,
        target_pts=30.0, sl_pts=15.0, setup_reason="ONE_SHOT_CANDIDATE",
        trade_phase="MIDDAY_REVERSAL", bar_time=dt_time(11, 35), is_active=True,
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, boundary_ms // 300_000 - 1)
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    depth = _make_dummy_depth(
        ts_ms=boundary_ms + 100, ingress_ns=metadata.issued_monotonic_ns + 100_000_000
    )
    identity = advisor._option_quote_identity(
        "NIFTY", depth, wall_now_ms=now_wall_ms, monotonic_now_ns=metadata.issued_monotonic_ns + 500_000_000
    )
    assert identity[0]
    assert advisor._record_option_depth_order("NIFTY", identity[2], identity[3], identity[4])
    barrier = threading.Barrier(2)
    accepted = []

    def reserve_once():
        barrier.wait()
        with advisor._lock:
            ok, _ = advisor._final_candidate_authorization_locked(
                "NIFTY", metadata.generation, depth, identity[2], identity[3], identity[4],
                metadata.issued_monotonic_ns + 500_000_000, wall_now_ms=now_wall_ms,
            )
            if ok:
                advisor._consume_cached_rbfn_candidate_locked(
                    "NIFTY", metadata.generation, "RESERVATION_ACCEPTED"
                )
                accepted.append(True)

    threads = [threading.Thread(target=reserve_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert len(accepted) == 1
    assert advisor.get_valid_cached_rbfn_signal("NIFTY") is None


def test_mode5_option_watermark_rollover_and_consumption_lifecycle(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "candidate-lifecycle.json"), enable_stdout=False)
    ist = ZoneInfo("Asia/Kolkata")
    day1 = date(2026, 11, 18)
    boundary = datetime.combine(day1, dt_time(11, 35), tzinfo=ist)
    boundary_ms = int(boundary.timestamp() * 1000)
    clock_ns = [40_000_000_000]
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: clock_ns[0])
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=boundary_ms - 100,
        index_name="NIFTY", action="BUY_CALL", direction="CE", target_strike=25400.0,
        target_pts=30.0, sl_pts=15.0, setup_reason="LIFECYCLE_CANDIDATE",
        trade_phase="MIDDAY_REVERSAL", bar_time=dt_time(11, 35), is_active=True,
    )
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, boundary_ms // 300_000 - 1)
    token = "NSE_FO|45408"
    first = (boundary_ms + 1, 1)
    assert advisor._record_option_depth_order("NIFTY", day1, token, first)
    assert not advisor._record_option_depth_order("NIFTY", day1, token, first)
    assert not advisor._record_option_depth_order("NIFTY", day1, token, (boundary_ms, 99))

    # A new session clears both candidate metadata and prior token watermarks.
    advisor._rp2_session_dates["NIFTY"] = day1
    day2 = date(2026, 11, 19)
    assert advisor._record_option_depth_order("NIFTY", day2, token, (boundary_ms + 300_000, 1))
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._cached_rbfn_candidate_meta["NIFTY"] is None
    assert advisor._option_depth_watermarks["NIFTY"][token] == (day2, boundary_ms + 300_000, 1)

    # Explicit pre-reservation vetoes retain the candidate; terminal/unknown/accepted outcomes consume it.
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, boundary_ms // 300_000 - 1)
    transient_generation = advisor._cached_rbfn_candidate_meta["NIFTY"].generation
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == transient_generation
    assert advisor._consume_cached_rbfn_candidate_locked("NIFTY", transient_generation, "RESERVATION_UNKNOWN")
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._candidate_snapshot_locked("NIFTY")[0] is None


def _configure_production_mode5_entry(
    advisor: SentinelLiveStreamAdvisor,
    tmp_path: Path,
    monkeypatch,
    *,
    boundary: datetime,
    monotonic_base_ns: int,
    reservation_result: SimpleNamespace | None = None,
    reservation_exception: Exception | None = None,
    callback_exception: Exception | None = None,
    strike_oi_allowed: bool = True,
    direction: str = "CE",
    setup_reason: str = "RP1_UPPER_REVERSAL_CONFIRMED",
    trade_phase: str | None = None,
    triggering_reference_price: float | None = 24600.0,
):
    """Set deterministic local dependencies around the real option-depth entry path."""
    boundary_ms = int(boundary.timestamp() * 1000)
    wall_now_ms = boundary_ms + 10
    monotonic_clock = [monotonic_base_ns]
    monkeypatch.setattr(advisor_module, "_wall_clock_seconds", lambda: wall_now_ms / 1000.0)
    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", lambda: monotonic_clock[0])
    _seed_test_or_pair(advisor, "NIFTY", dt_time(boundary.hour, boundary.minute))
    ist = ZoneInfo("Asia/Kolkata")
    or_start = datetime.combine(boundary.date(), dt_time(9, 15), tzinfo=ist)
    or_end = datetime.combine(boundary.date(), dt_time(9, 44), tzinfo=ist)
    for index in ("NIFTY", "SENSEX"):
        advisor.or_evidence[index]["session_date"] = boundary.date().isoformat()
        advisor.or_evidence[index]["source_timestamp_ms"] = int(or_end.timestamp() * 1000)
        advisor.or_evidence[index]["available_at_ms"] = wall_now_ms - 1
        advisor.or_evidence[index]["coverage_start_ms"] = int(or_start.timestamp() * 1000)
        advisor.or_evidence[index]["coverage_end_ms"] = int(or_end.timestamp() * 1000)
    advisor.decision_trace_path = tmp_path / f"production-mode5-{boundary_ms}.jsonl"
    advisor.spots["NIFTY"] = 24000.0
    advisor.spots_ts_ms["NIFTY"] = boundary_ms
    advisor._rp2_session_dates["NIFTY"] = boundary.date()
    advisor.trade_lock_active = False
    advisor.wall_observers["NIFTY"] = None
    advisor.wall_gates["NIFTY"] = None
    advisor.adapter.get_all_depth = Mock(return_value={})
    advisor.evaluate_strike_oi = Mock(return_value=strike_oi_allowed)
    advisor.evaluate_nifty_frictional_hurdle = Mock(return_value=(True, "OK"))
    advisor.macro_gate.evaluate_alignment = Mock(return_value=(True, "OK"))
    advisor.vol_compression_gate.evaluate_compression = Mock(return_value=(True, "OK", None))
    advisor.confidence_scorer.evaluate_confidence = Mock(return_value=SimpleNamespace(
        is_actionable=True, total_score=90, grade="A", probable_win_rate_pct=70,
        sizing_recommendation="FULL",
    ))
    advisor.strike_resolver.resolve_target_strike = Mock(return_value=SimpleNamespace(
        target_strike=24100.0, moneyness="ITM_1",
    ))
    advisor.strike_resolver.is_contract_matching = Mock(return_value=True)
    advisor.passive_midpoint_queue.calculate_entry_fill = Mock(return_value=(100.0, 0.0, "MOCK"))
    advisor.apms["NIFTY"].is_cool_off_active = Mock(return_value=False)
    advisor.apms["NIFTY"].arm_and_enter = Mock(return_value=True)
    advisor.journal = Mock()
    advisor.automated_dispatcher = Mock()
    advisor.automated_dispatcher.reserve_entry_intent.side_effect = reservation_exception
    if reservation_result is not None:
        advisor.automated_dispatcher.reserve_entry_intent.side_effect = None
        advisor.automated_dispatcher.reserve_entry_intent.return_value = reservation_result
    if callback_exception is not None:
        advisor.automated_dispatcher.on_apm_entry.side_effect = callback_exception
    monkeypatch.setattr(advisor_module, "calculate_discrete_lots", lambda **kwargs: (1, "FULL"))
    monkeypatch.setattr(advisor_module, "get_exchange_lot_size", lambda index_name: 1)

    signal = CachedRBFNAuctionSignal(
        timestamp_ms=boundary_ms - 1,
        index_name="NIFTY",
        action="BUY_CALL" if direction == "CE" else "BUY_PUT",
        direction=direction,
        target_strike=24100.0,
        target_pts=30.0,
        sl_pts=20.0,
        setup_reason=setup_reason,
        trade_phase=trade_phase or {
            "RP1_UPPER_10M_EXPANSION_BREAKOUT": "MIDDAY_EXPANSION_BREAKOUT",
            "RP1_LOWER_10M_EXPANSION_BREAKDOWN": "MIDDAY_EXPANSION_BREAKDOWN",
        }.get(setup_reason, "MIDDAY_REVERSAL"),
        bar_time=dt_time(boundary.hour, boundary.minute),
        triggering_reference_price=triggering_reference_price,
        is_active=True,
    )
    epoch = boundary_ms // 300_000 - 1
    with advisor._lock:
        advisor._cache_rbfn_signal_locked("NIFTY", signal, epoch)
    candidate = advisor._cached_rbfn_candidate_meta["NIFTY"]
    mono_now_ns = monotonic_base_ns + 10_000_000
    monotonic_clock[0] = mono_now_ns
    option_suffix = "CE" if direction == "CE" else "PE"
    depth = _make_dummy_depth(
        token=f"NSE_FO|NIFTY26NOV24100{option_suffix}",
        symbol=f"NIFTY 24100 {option_suffix}",
        ts_ms=boundary_ms,
        ingress_ns=candidate.issued_monotonic_ns + 1_000_000,
        sequence_id=1,
        ingress_wall_utc=datetime.fromtimestamp(wall_now_ms / 1000.0, tz=timezone.utc).isoformat(),
    )
    return depth, signal, candidate.generation, wall_now_ms, mono_now_ns


def test_production_mode5_exact_bucket_candidate_is_blocked_once_before_dispatch(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "production-boundary.json"), enable_stdout=False)
    day = date(2026, 11, 18)
    boundary = datetime.combine(day, dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    accepted = SimpleNamespace(accepted=True, reason="RESERVED_PAPER", action="RESERVED", routed_mode="PAPER")
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=50_000_000_000,
        reservation_result=accepted,
    )
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike", staticmethod(
            lambda **kwargs: SimpleNamespace(target_strike=24100.0)
        ))
        advisor._evaluate_option_depth(depth)
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert len([r for r in _read_mode5_trace_records(advisor) if r.get("event_type") == "MODE5_POLICY_OBSERVATION"]) == 1


def test_mode5_rp_reference_changes_only_volatility_gate_displacement(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "rp-gate-inputs.json"), enable_stdout=False)
    boundary = datetime.combine(date(2026, 11, 18), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=51_000_000_000,
        reservation_result=SimpleNamespace(
            accepted=False, reason="test-terminal", action="VETOED_TEST", routed_mode="PAPER"
        ),
    )
    confidence_spy = Mock(return_value=SimpleNamespace(
        is_actionable=True, total_score=90, grade="A", probable_win_rate_pct=70,
        sizing_recommendation="FULL",
    ))
    volatility_spy = Mock(return_value=(True, "OK", 1.0))
    advisor.confidence_scorer.evaluate_confidence = confidence_spy
    advisor.vol_compression_gate.evaluate_compression = volatility_spy
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver,
        "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    advisor._evaluate_option_depth(depth)

    confidence_spy.assert_called_once()
    volatility_spy.assert_called_once()
    assert confidence_spy.call_args.kwargs["displacement_pts"] == 100.0
    assert volatility_spy.call_args.kwargs["recent_displacement_pts"] == 600.0


@pytest.mark.parametrize(
    ("setup_reason", "reference", "spot", "direction", "expected_veto", "expected_label"),
    [
        ("RP1_UPPER_REVERSAL_CONFIRMED", 24600.0, 24762.5, "CE", False, None),
        ("RP1_UPPER_REVERSAL_CONFIRMED", 24600.0, 24762.0, "CE", False, None),
        ("RP1_UPPER_REVERSAL_CONFIRMED", 24600.0, 24763.0, "CE", True, "DISTANCE_TO_BOUNDARY"),
        ("RP1_UPPER_10M_EXPANSION_BREAKOUT", 24600.0, 24643.0, "CE", False, None),
        ("RP1_UPPER_10M_EXPANSION_BREAKOUT", None, 24763.0, "CE", True, "MISSING_RP_BOUNDARY_REFERENCE"),
        ("RP1_UPPER_REVERSAL_CONFIRMED", None, 24763.0, "CE", True, "MISSING_RP_BOUNDARY_REFERENCE"),
        ("RP1_LOWER_10M_EXPANSION_BREAKDOWN", 25160.0, 25120.0, "PE", False, None),
        ("RP1_LOWER_10M_EXPANSION_BREAKDOWN", None, 25120.0, "PE", True, "MISSING_RP_BOUNDARY_REFERENCE"),
        ("RP1_LOWER_10M_EXPANSION_BREAKDOWN", math.nan, 25120.0, "PE", True, "MISSING_RP_BOUNDARY_REFERENCE"),
        ("RP1_LOWER_10M_EXPANSION_BREAKDOWN", math.inf, 25120.0, "PE", True, "MISSING_RP_BOUNDARY_REFERENCE"),
        ("RP2_UPPER_NEW_FADE_FAMILY", 24240.0, 24403.0, "CE", True, "UNKNOWN_RP_BOUNDARY_SETUP"),
    ],
)
def test_mode5_distance_label_is_diagnostic_and_never_veto_authority(
    tmp_path: Path,
    monkeypatch,
    setup_reason: str,
    reference: float | None,
    spot: float,
    direction: str,
    expected_veto: bool,
    expected_label: str | None,
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"distance-label-{setup_reason}-{spot}.json"),
        enable_stdout=False,
    )
    boundary = datetime.combine(date(2026, 11, 18), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor,
        tmp_path,
        monkeypatch,
        boundary=boundary,
        monotonic_base_ns=52_000_000_000,
        reservation_result=SimpleNamespace(
            accepted=False, reason="test-terminal", action="VETOED_TEST", routed_mode="PAPER"
        ),
        direction=direction,
        setup_reason=setup_reason,
        triggering_reference_price=reference,
    )
    expected_expansion_phase = {
        "RP1_UPPER_10M_EXPANSION_BREAKOUT": "MIDDAY_EXPANSION_BREAKOUT",
        "RP1_LOWER_10M_EXPANSION_BREAKDOWN": "MIDDAY_EXPANSION_BREAKDOWN",
    }.get(setup_reason)
    if expected_expansion_phase is not None:
        assert signal.trade_phase == expected_expansion_phase
    advisor.vol_compression_gate = advisor_module.VolatilityCompressionGate()
    advisor.spots["NIFTY"] = spot
    if expected_veto and expected_label == "MISSING_RP_BOUNDARY_REFERENCE":
        advisor.vol_compression_gate.evaluate_compression = Mock(return_value=(False, "EXHAUSTED_EXPANSION", None))
    monkeypatch.setattr(
        advisor_module.SentinelOptionStrikeResolver,
        "resolve_mode5_strike",
        staticmethod(lambda **kwargs: SimpleNamespace(target_strike=24100.0)),
    )

    advisor._evaluate_option_depth(depth)

    assert advisor.alerts_history
    alert = advisor.alerts_history[-1]
    assert alert.status_flag == "VETO_MODE5_SIZING_POLICY_UNVERIFIED"
    rows = _read_mode5_trace_records(advisor)
    observations = [row for row in rows if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert len(observations) == 1
    exhaustion = observations[0]["observations"]["exhaustion"]
    assert exhaustion["would_veto"] is expected_veto
    if expected_label is not None:
        assert expected_label in exhaustion["reason"]
    else:
        assert "DISTANCE_TO_BOUNDARY" not in exhaustion["reason"]
    assert not any(
        call.kwargs.get("veto_reason") == "VOLATILITY_EXHAUSTED"
        for call in advisor.journal.record_veto.call_args_list
    )
    assert observations[0]["candidate_id"] == advisor._mode5_candidate_id(
        "NIFTY", advisor._cached_rbfn_candidate_meta["NIFTY"].session_day, generation
    )


def test_production_mode5_queue_full_does_not_bypass_sizing_block(
    tmp_path: Path, monkeypatch
):
    """Telemetry saturation cannot bypass the Mode5 sizing-policy authorization block."""
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "production-queue-full.json"),
        enable_stdout=False,
        mode5_trace_queue_capacity=1,
        mode5_trace_max_record_bytes=2048,
    )
    boundary = datetime.combine(date(2026, 11, 18), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    accepted = SimpleNamespace(accepted=True, reason="RESERVED_PAPER", action="RESERVED", routed_mode="PAPER")
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=55_000_000_000,
        reservation_result=accepted,
    )

    writer_started = threading.Event()
    release_writer = threading.Event()
    original_append = advisor._append_decision_trace_record_locked

    def blocking_writer(serialized):
        writer_started.set()
        assert release_writer.wait(timeout=4)
        return original_append(serialized)

    advisor._append_decision_trace_record_locked = blocking_writer
    filler_key = advisor._mode5_trace_key(
        "NIFTY", generation, "QUEUE_CAPACITY_FILLER", depth.exchange_timestamp_ms
    )
    assert advisor._enqueue_mode5_trace_record(
        {
            "event_type": "MODE5_DECISION_TRACE",
            "index_name": "NIFTY",
            "action": "ABSTAIN",
            "reason": "QUEUE_CAPACITY_FILLER",
            "timestamp_ms": depth.exchange_timestamp_ms,
            "candidate_generation": generation,
        },
        dedup_key=filler_key,
    )
    assert writer_started.wait(timeout=2)
    queued_key = advisor._mode5_trace_key(
        "NIFTY", generation, "QUEUE_CAPACITY_QUEUED", depth.exchange_timestamp_ms
    )
    assert advisor._enqueue_mode5_trace_record(
        {
            "event_type": "MODE5_DECISION_TRACE",
            "index_name": "NIFTY",
            "action": "ABSTAIN",
            "reason": "QUEUE_CAPACITY_QUEUED",
            "timestamp_ms": depth.exchange_timestamp_ms,
            "candidate_generation": generation,
        },
        dedup_key=queued_key,
    )
    assert advisor.get_mode5_trace_health()["queue_depth"] == 1

    # A candidate-specific suppression occurs while saturated. It is dropped
    # as telemetry only; the still-valid candidate is then processed through
    # the real production entry route below.
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    lagging_depth = _make_dummy_depth(
        token=depth.token,
        symbol=depth.symbol,
        ts_ms=metadata.boundary_timestamp_ms - 1,
        ingress_ns=metadata.issued_monotonic_ns + 1,
    )
    assert not advisor._emit_mode5_quote_suppression(
        "NIFTY", depth.token, signal, metadata, lagging_depth,
        "MODE5_QUOTE_BEFORE_BAR_BOUNDARY", metadata.boundary_timestamp_ms,
    )
    assert advisor.get_mode5_trace_health()["queue_full_drops"] == 1

    monkeypatch.setattr(advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike", staticmethod(
        lambda **kwargs: SimpleNamespace(target_strike=24100.0)
    ))
    try:
        # Real option-depth processing remains fail-closed while telemetry is full.
        advisor._evaluate_option_depth(depth)
        advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
        advisor.automated_dispatcher.on_apm_entry.assert_not_called()
        advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
        assert advisor.cached_rbfn_signals["NIFTY"] is None
        assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "MODE5_SIZING_POLICY_UNVERIFIED"
        health = advisor.get_mode5_trace_health()
        assert health["queue_full_drops"] >= 1
        assert health["candidate_lifecycle_incomplete"] is True
        assert health["candidate_lifecycle_drops"] >= 1

        # A duplicate quote cannot re-arm or dispatch the consumed candidate.
        advisor._evaluate_option_depth(depth)
        advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
        advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    finally:
        release_writer.set()
        advisor.shutdown_mode5_trace_writer(timeout_sec=3)


def assert_candidate_consumed_before_callback(advisor, signal):
    assert not advisor._lock._is_owned()
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status in {
        "RESERVATION_ACCEPTED", "ENTRY_SUCCEEDED", "APM_ENTRY_RECORDED"
    }


def test_production_mode5_concurrent_duplicate_callbacks_terminalize_once(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "production-concurrent.json"), enable_stdout=False)
    boundary = datetime.combine(date(2026, 11, 18), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=60_000_000_000,
    )
    monkeypatch.setattr(advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike", staticmethod(
        lambda **kwargs: SimpleNamespace(target_strike=24100.0)
    ))
    barrier = threading.Barrier(2)
    errors = []

    def process_duplicate():
        try:
            barrier.wait(timeout=2)
            advisor._evaluate_option_depth(depth)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=process_duplicate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    records = _read_mode5_trace_records(advisor)
    terminal_rows = [row for row in records if row.get("event_type") == "MODE5_CANDIDATE_TERMINAL"]
    policy_rows = [row for row in records if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert len(terminal_rows) == len(policy_rows) == 1
    assert terminal_rows[0]["candidate_generation"] == generation
    assert terminal_rows[0]["terminal_reason"] == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert policy_rows[0]["candidate_generation"] == generation
    assert policy_rows[0]["authorization_block"] == "MODE5_SIZING_POLICY_UNVERIFIED"


def test_production_mode5_sizing_block_prevents_dispatch_before_handlers(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "production-sizing-block.json"), enable_stdout=False)
    boundary = datetime.combine(date(2026, 11, 18), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=70_000_000_000
    )
    monkeypatch.setattr(advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike", staticmethod(
        lambda **kwargs: SimpleNamespace(target_strike=24100.0)
    ))
    advisor._evaluate_option_depth(depth)
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert advisor.get_valid_cached_rbfn_signal("NIFTY") is None
    advisor._evaluate_option_depth(depth)
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()


def test_production_mode5_transient_pre_reservation_liquidity_veto_retains_candidate(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "production-transient-veto.json"), enable_stdout=False)
    boundary = datetime.combine(date(2026, 11, 18), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=80_000_000_000,
        strike_oi_allowed=False,
    )
    advisor._evaluate_option_depth(depth)
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == generation
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()


def test_production_mode5_prior_session_quote_after_rollover_preserves_new_candidate(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "production-prior-session.json"), enable_stdout=False)
    day2 = date(2026, 11, 19)
    boundary = datetime.combine(day2, dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, wall_now_ms, mono_now_ns = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary, monotonic_base_ns=90_000_000_000,
        strike_oi_allowed=False,
    )
    prior_ts = int(datetime.combine(day2 - timedelta(days=1), dt_time(10, 0), tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    prior_depth = _make_dummy_depth(
        token=depth.token, symbol=depth.symbol, ts_ms=prior_ts,
        ingress_ns=mono_now_ns - 1_000_000, sequence_id=2,
    )
    advisor._evaluate_option_depth(prior_depth)
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].generation == generation
    assert advisor._option_depth_watermarks["NIFTY"] == {}


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


@pytest.mark.parametrize(
    ("position_matches_quote", "expected_advisory"),
    [
        (True, "MATCHING_POSITION_MANAGED_THIS_QUOTE; ENTRY_BLOCKED"),
        (False, "ACTIVE_POSITION_OTHER_CONTRACT; ENTRY_BLOCKED"),
    ],
)
def test_active_position_advisory_identifies_exact_or_other_contract_without_reentry(
    tmp_path: Path, monkeypatch, position_matches_quote: bool, expected_advisory: str
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"position-advisory-{position_matches_quote}.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=101_000_000_000 + int(position_matches_quote) * 10_000_000,
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(
        opt_symbol=depth.symbol if position_matches_quote else "NIFTY 24000 PE",
        opt_token=depth.token if position_matches_quote else "OTHER-TOKEN",
    )
    apm.evaluate_tick = Mock()
    apm.arm_and_enter = Mock()
    advisor._evaluate_option_depth(depth)

    assert apm.evaluate_tick.call_count == int(position_matches_quote)
    apm.arm_and_enter.assert_not_called()
    assert advisor.alerts_history
    alert = advisor.alerts_history[-1]
    assert alert.status_flag == "VETO_CONCURRENT_POSITION"
    assert expected_advisory in alert.advisory


def test_quote_expiring_before_apm_update_cannot_manage_or_claim_exit(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "quote-expires-before-apm.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, initial_monotonic_ns = _configure_production_mode5_entry(
        advisor,
        tmp_path,
        monkeypatch,
        boundary=boundary,
        monotonic_base_ns=105_000_000_000,
    )
    max_age_ns = int(float(advisor_module.app_config.MAX_QUOTE_AGE_SEC) * 1_000_000_000)
    clock_values = (
        initial_monotonic_ns,
        depth.ingress_monotonic_ns + max_age_ns + 1,
    )
    clock_index = [0]

    def advance_clock():
        value = clock_values[min(clock_index[0], len(clock_values) - 1)]
        clock_index[0] += 1
        return value

    monkeypatch.setattr(advisor_module, "_monotonic_clock_ns", advance_clock)

    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    apm.evaluate_tick = Mock()
    apm.arm_and_enter = Mock()
    advisor.journal.record_exit = Mock()
    advisor.automated_dispatcher.on_apm_exit = Mock()
    advisor.automated_dispatcher.reserve_entry_intent = Mock()
    advisor.automated_dispatcher.on_apm_entry = Mock()
    advisor.record_veto = Mock(wraps=advisor.record_veto)

    advisor._evaluate_option_depth(depth)

    apm.evaluate_tick.assert_not_called()
    advisor.journal.record_exit.assert_not_called()
    advisor.automated_dispatcher.on_apm_exit.assert_not_called()
    advisor.automated_dispatcher.reserve_entry_intent.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    assert apm.state == advisor_module.STATE_IN_FLIGHT
    assert any(
        call.args[0] == "OPTION_DEPTH_TIMESTAMP"
        and str(call.args[1]).endswith("_BEFORE_APM_UPDATE")
        for call in advisor.record_veto.call_args_list
    )


def test_mode5_quote_change_during_final_or_diagnostic_retains_candidate(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-post-diagnostic-watermark.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=103_000_000_000,
        setup_reason="TEST_DIRECTIONAL_CONTINUATION",
        trade_phase="CONTINUOUS_STATE_MACHINE",
    )
    key = advisor._canonical_option_instrument_key("NIFTY", depth.token)
    assert key is not None
    original_validate = advisor._validate_mode5_or_pair
    calls = 0

    def advance_quote_watermark(*args, **kwargs):
        nonlocal calls
        result = original_validate(*args, **kwargs)
        calls += 1
        # The first pair is the initial quote checkpoint; advance the event
        # watermark during the final diagnostic checkpoint.
        if calls == 2:
            advisor._option_depth_watermarks["NIFTY"][key] = (
                date(2026, 11, 18), depth.exchange_timestamp_ms + 1, depth.sequence_id + 1
            )
        return result

    advisor._validate_mode5_or_pair = advance_quote_watermark
    advisor._evaluate_option_depth(depth)

    assert calls >= 2
    metadata = advisor._cached_rbfn_candidate_meta["NIFTY"]
    assert metadata.generation == generation
    assert metadata.status == "AVAILABLE"
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    records = _read_mode5_trace_records(advisor)
    assert not any(row.get("event_type") == "MODE5_POLICY_OBSERVATION" for row in records)
    assert any(
        row.get("reason") == "MODE5_CANDIDATE_STATE_AFTER_QUOTE_REJECTION"
        and row.get("details", {}).get("candidate_state") == "AVAILABLE"
        for row in records
    )


def test_superseded_quote_cannot_update_apm_or_authorize_candidate(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "superseded-apm-quote.json"),
        enable_stdout=False,
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, signal, generation, _, mono_now_ns = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=104_000_000_000,
        setup_reason="TEST_DIRECTIONAL_CONTINUATION",
        trade_phase="CONTINUOUS_STATE_MACHINE",
    )
    key = advisor._canonical_option_instrument_key("NIFTY", depth.token)
    assert key is not None
    quote_day = boundary.date()
    source_order = (depth.exchange_timestamp_ms, depth.sequence_id)
    advisor._option_depth_watermarks["NIFTY"][key] = (
        quote_day, source_order[0] + 1, source_order[1] + 1
    )
    apm = advisor.apms["NIFTY"]
    apm.state = advisor_module.STATE_IN_FLIGHT
    apm.payload = SimpleNamespace(opt_symbol=depth.symbol, opt_token=depth.token)
    apm.evaluate_tick = Mock()

    active, managed = advisor._manage_matching_position_from_quote(
        index_name="NIFTY", depth=depth,
        broker_instrument_key=key, spot=24_000.0, option_ltp=100.0,
        now_dt=boundary, quote_day=quote_day, instrument_key=key,
        source_order=source_order,
    )
    assert (active, managed) == (False, False)
    apm.evaluate_tick.assert_not_called()
    authorized, reason = advisor._final_candidate_authorization_locked(
        index_name="NIFTY", generation=generation, depth=depth,
        quote_day=quote_day, instrument_key=key, source_order=source_order,
        now_ns=mono_now_ns,
        wall_now_ms=depth.exchange_timestamp_ms + 10,
    )
    assert not authorized
    assert reason == "MODE5_QUOTE_NO_LONGER_ELIGIBLE"
    assert advisor.cached_rbfn_signals["NIFTY"] is signal
    assert advisor._cached_rbfn_candidate_meta["NIFTY"].status == "AVAILABLE"


def test_final_candidate_authorization_veto_is_not_reported_as_or_veto(
    tmp_path: Path, monkeypatch
):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "mode5-final-auth-reason.json"), enable_stdout=False
    )
    boundary = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    depth, _, _, _, _ = _configure_production_mode5_entry(
        advisor, tmp_path, monkeypatch, boundary=boundary,
        monotonic_base_ns=104_000_000_000,
    )
    monkeypatch.setattr(
        advisor_module, "mode5_overlays_are_diagnostic", lambda _strategy: False
    )
    advisor._final_candidate_authorization_locked = Mock(
        return_value=(False, "OPTION_DEPTH_SOURCE_STALE_OR_FUTURE")
    )
    advisor.record_veto = Mock(wraps=advisor.record_veto)

    advisor._evaluate_option_depth(depth)

    assert advisor.alerts_history
    alert = advisor.alerts_history[-1]
    assert alert.status_flag == "VETO_MODE5_FINAL_AUTHORIZATION"
    assert "OPTION_DEPTH_SOURCE_STALE_OR_FUTURE" in alert.advisory
    assert any(
        call.args[:1] == ("MODE5_FINAL_AUTHORIZATION",)
        and call.args[1:2] == ("OPTION_DEPTH_SOURCE_STALE_OR_FUTURE",)
        for call in advisor.record_veto.call_args_list
    )
    assert not any(call.args[:1] == ("MODE5_OR",) for call in advisor.record_veto.call_args_list)
