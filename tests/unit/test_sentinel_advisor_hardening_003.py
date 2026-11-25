"""
Unit Tests for OptionMate Sentinel Advisor Hardening 003
=========================================================
Specification: ARCH-SENTINEL-HARDENING-003

Validates the 6 acceptance gates (GATE-SENTINEL-07 to GATE-SENTINEL-12):
1. GATE-SENTINEL-07: Directional RP2 Boundary Retest Invalidation
   - Proves upper RP2 pierce tests upper boundary (rp2_upper), NOT lower boundary.
   - Proves lower RP2 pierce tests lower boundary (rp2_lower), NOT upper boundary.
2. GATE-SENTINEL-08: Incomplete Attribute Grid Deprecation
   - When reload encounters incomplete attributes (any None in td, r1_u, r2_u, r1_l, r2_l),
     immediately resets rbfn_grids_frozen[idx]=False and is_ground_truth=False.
3. GATE-SENTINEL-09: Zero-Timestamp Signal Eviction
   - Evicts cached RBFN signal when timestamp_ms <= 0, returning None immediately.
4. GATE-SENTINEL-10: Broker Position Exception Propagation
   - UpstoxBrokerAdapter.fetch_open_positions raises RuntimeError on broker failure
     instead of silently returning [].
5. GATE-SENTINEL-11: Unconfigured Broker Fail-Closed Reconciler
   - BrokerPositionReconciler fails closed when broker is None, returning
     (False, [], "UNCONFIGURED_BROKER...") and wal_reset_permitted=False.
6. GATE-SENTINEL-12: Webhook Auth Guard
   - TradingViewLevelReceiver rejects requests when require_auth=True and no auth configured.

Safety Invariants:
- read_only = True, is_order_action = False, broker_api_called = False, allowed_for_live_execution = False.
"""

from __future__ import annotations

import json
import math
import time
import copy
import threading
import os
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import URLError
from zoneinfo import ZoneInfo
import pytest

import core.sentinel_live_stream_advisor as advisor_module
from core.broker.upstox_broker_adapter import UpstoxBrokerAdapter
from core.reconciliation.broker_position_reconciler import BrokerPositionReconciler
from core.sentinel_live_stream_advisor import (
    CachedRBFNAuctionSignal,
    SentinelLiveStreamAdvisor,
)
from core.upstox_stream_broadcaster import UpstoxTickRecord
from core.upstox_stream_broadcaster import UpstoxLevel5DepthRecord
from core.webhooks.tradingview_level_receiver import TradingViewLevelReceiver
from strategies.optionmate_rbfn_strategy import OptionMateGrid


def _india_ts(session_day: date, bar_time: dt_time = dt_time(10, 0)) -> int:
    return int(datetime.combine(session_day, bar_time, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)


@pytest.fixture(autouse=True)
def _disable_constructor_network(monkeypatch):
    """Keep the existing constructor seed path offline in this unit module."""
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")


def _seed_complete_mode5_or_pair(advisor, index_name: str, session_day: date) -> None:
    """Provide a local deterministic OR fixture for tests of unrelated Mode5 behavior."""
    ist = ZoneInfo("Asia/Kolkata")
    start = datetime.combine(session_day, dt_time(9, 15), tzinfo=ist)
    end = datetime.combine(session_day, dt_time(9, 44), tzinfo=ist)
    companion = "SENSEX" if index_name == "NIFTY" else "NIFTY"
    for current in (index_name, companion):
        advisor.or_bounds[current] = {"high": 101.0, "low": 99.0}
        advisor.or_evidence[current] = {
            "session_date": session_day.isoformat(),
            "status": "COMPLETE",
            "source": "UPSTOX_V2_1M_EXACT_30",
            "source_timestamp_ms": int(end.timestamp() * 1000),
            "coverage_count": 30,
            "coverage_start_ms": int(start.timestamp() * 1000),
            "coverage_end_ms": int(end.timestamp() * 1000),
        }


def _completed_bar_clock(timestamp_ms: int) -> tuple[int, dt_time]:
    epoch = timestamp_ms // 300000
    next_boundary = datetime.fromtimestamp((epoch + 1) * 300, tz=ZoneInfo("Asia/Kolkata"))
    return epoch, next_boundary.time()


def _freeze_advisor_clock(monkeypatch, instant_ms: int) -> None:
    monkeypatch.setattr(advisor_module.time, "time", lambda: instant_ms / 1000.0)


def _spot_tick(ts_ms: int, price: float, seq: int) -> UpstoxTickRecord:
    return UpstoxTickRecord(
        token="Nifty 50", symbol="NIFTY", exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=seq, ingress_wall_utc="", sequence_id=seq,
        ltp=price, volume=1, open_interest=0, best_bid=0.0, best_ask=0.0,
    )


def _bucket_snapshot(bucket) -> tuple:
    return (
        bucket.bucket_epoch_min if hasattr(bucket, "bucket_epoch_min") else bucket.bucket_epoch_5min,
        bucket.open, bucket.high, bucket.low, bucket.close, bucket.volume,
        bucket.tick_count, bucket.last_timestamp_ms,
    )


def _router_snapshot(router) -> tuple:
    return (
        router.current_epoch,
        router.session_switch_count,
        router.last_dominant_regime,
        router.last_switch_epoch,
    )


def test_gate_sentinel_07_directional_rp2_boundary_retest(tmp_path: Path, monkeypatch):
    """GATE-SENTINEL-07: Upper RP2 pierce checks upper boundary retest; lower pierce checks lower boundary retest."""
    wal = tmp_path / "test_wal_rp2_retest.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "upper_rp2_decision_trace.jsonl"
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0
    grid = advisor.cached_rbfn_grids["NIFTY"]

    # Grid: TD = 24000, RP1 Upper = 24120, RP2 Upper = 24240, RP1 Lower = 23880, RP2 Lower = 23760
    # Simulate upper pierce before 10:30
    advisor.rp2_upper_pierced_before_1030["NIFTY"] = True
    advisor.rp2_lower_pierced_before_1030["NIFTY"] = False

    # Scenario A: Upper pierced, bar history stays above rp2_upper (low > rp2_upper).
    # Since low did NOT retest rp2_upper (any low <= rp2_upper is False), it should ABSTAIN (Trend Day Invalidation).
    # Feed 3 bars: all low > 24240 (e.g. 24250, 24260, 24270)
    session_day = date(2026, 11, 18)
    _seed_complete_mode5_or_pair(advisor, "NIFTY", session_day)
    _freeze_advisor_clock(monkeypatch, _india_ts(session_day, dt_time(11, 0)))
    for i, p in enumerate([24255.0, 24265.0, 24275.0]):
        source_ts = _india_ts(session_day, dt_time(10, 39 + i * 5, 59, 999000))
        source_epoch, close_time = _completed_bar_clock(source_ts)
        advisor._on_5m_bar_close(
            index_name="NIFTY",
            bar_open=p - 5.0,
            bar_high=p + 10.0,
            bar_low=p - 2.0,  # lowest is 24253 > 24240
            bar_close=p + 5.0,
            bar_volume=50000.0,
            bar_time=close_time,
            timestamp_ms=source_ts,
            epoch_5min=source_epoch,
        )

    sig = advisor.cached_rbfn_signals.get("NIFTY")
    assert sig is not None
    # Low never breached/retested rp2_upper (24240), so 10:30 invalidation remains active -> ABSTAIN
    assert sig.action == "ABSTAIN"
    assert sig.veto_reason == "10:30_RP2_PIERCING_TREND_DAY_INVALIDATION"

    # Scenario B: Bar pulls back and low retests rp2_upper (low <= 24240, but low is WAY above rp2_lower 23760)
    # With the bug, it checked low <= rp2_lower (23760), so a retest of rp2_upper would still be considered "no retest" and ABSTAIN.
    # With the fix, low <= rp2_upper (24240) satisfies the retest condition!
    # Let's verify by feeding a bar where low <= 24240:
    source_ts = _india_ts(session_day, dt_time(10, 54, 59, 999000))
    source_epoch, close_time = _completed_bar_clock(source_ts)
    advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24250.0,
        bar_high=24260.0,
        bar_low=24235.0,  # Retests rp2_upper (24240)
        bar_close=24245.0,
        bar_volume=60000.0,
        bar_time=close_time,
        timestamp_ms=source_ts,
        epoch_5min=source_epoch,
    )
    sig_retest = advisor.cached_rbfn_signals.get("NIFTY")
    assert sig_retest is not None
    # 10:30_RP2_PIERCING_TREND_DAY_INVALIDATION should NOT veto because retest occurred!
    assert sig_retest.veto_reason != "10:30_RP2_PIERCING_TREND_DAY_INVALIDATION"



def test_gate_sentinel_07_lower_rp2_retest_is_symmetric(tmp_path: Path, monkeypatch):
    wal = tmp_path / "lower_rp2_retest.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "lower_rp2_decision_trace.jsonl"
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24000.0
    advisor.rp2_lower_pierced_before_1030["NIFTY"] = True
    advisor._rp2_session_dates["NIFTY"] = date(2026, 11, 18)
    lower = 23760.0

    session_day = date(2026, 11, 18)
    _seed_complete_mode5_or_pair(advisor, "NIFTY", session_day)
    _freeze_advisor_clock(monkeypatch, _india_ts(session_day, dt_time(11, 0)))
    for i, p in enumerate([lower - 25.0, lower - 20.0]):
        source_ts = _india_ts(session_day, dt_time(10, 39 + i * 5, 59, 999000))
        source_epoch, close_time = _completed_bar_clock(source_ts)
        sig = advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=p - 3, bar_high=p - 1, bar_low=p - 8,
            bar_close=p - 4, bar_volume=50000, bar_time=close_time,
            timestamp_ms=source_ts, epoch_5min=source_epoch,
        )
    assert sig is not None and sig.veto_reason == "10:30_RP2_PIERCING_TREND_DAY_INVALIDATION"

    source_ts = _india_ts(session_day, dt_time(10, 54, 59, 999000))
    source_epoch, close_time = _completed_bar_clock(source_ts)
    sig_retest = advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=lower - 8, bar_high=lower + 3, bar_low=lower - 10,
        bar_close=lower - 2, bar_volume=60000, bar_time=close_time,
        timestamp_ms=source_ts, epoch_5min=source_epoch,
    )
    assert sig_retest is not None
    assert sig_retest.veto_reason != "10:30_RP2_PIERCING_TREND_DAY_INVALIDATION"


def test_rp2_session_rollover_resets_both_direction_flags(tmp_path: Path):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "session.json"), enable_stdout=False)
    advisor._rp2_session_dates["NIFTY"] = date(2026, 11, 17)
    advisor.rp2_upper_pierced_before_1030["NIFTY"] = True
    advisor.rp2_lower_pierced_before_1030["NIFTY"] = True
    advisor.rp2_pierced_before_1030["NIFTY"] = True
    advisor.session_open_prices["NIFTY"] = 24000.0
    stale_grid = SimpleNamespace(is_ground_truth=True)
    advisor.cached_rbfn_grids["NIFTY"] = stale_grid
    advisor.rbfn_grids_frozen["NIFTY"] = True
    advisor._last_completed_5m_epoch["NIFTY"] = 123
    advisor._last_5m_timestamp_ms["NIFTY"] = 1794900000000
    advisor.cached_rbfn_signals["NIFTY"] = SimpleNamespace(action="BUY_CALL")
    advisor.bars_5m_history["NIFTY"].append({"high": 1})
    advisor.evaluated_5m_epochs["NIFTY"].add(1)
    assert advisor._reset_rp2_state_for_session("NIFTY", date(2026, 11, 18)) is True
    assert advisor.rp2_upper_pierced_before_1030["NIFTY"] is False
    assert advisor.rp2_lower_pierced_before_1030["NIFTY"] is False
    assert advisor.rp2_pierced_before_1030["NIFTY"] is False
    assert advisor.bars_5m_history["NIFTY"] == []
    assert advisor.evaluated_5m_epochs["NIFTY"] == set()
    assert advisor.session_open_prices["NIFTY"] == 0.0
    assert advisor.cached_rbfn_grids["NIFTY"] is None
    assert stale_grid.is_ground_truth is False
    assert advisor.rbfn_grids_frozen["NIFTY"] is False
    assert advisor.cached_rbfn_signals["NIFTY"] is None
    assert advisor._last_completed_5m_epoch["NIFTY"] == -1
    assert advisor._last_5m_timestamp_ms["NIFTY"] == 0
    assert advisor._reset_rp2_state_for_session("NIFTY", date(2026, 11, 18)) is False


def test_invalid_reload_root_deprecates_cached_grid_and_signal(tmp_path: Path):
    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "trace.jsonl"
    assert advisor.inject_optionmate_levels(
        "NIFTY", 24000, 24120, 24240, 23880, 23760,
        date_str=today_str,
    )
    advisor.cached_rbfn_signals["NIFTY"] = SimpleNamespace(action="BUY_CALL")
    levels_file = tmp_path / "levels.json"
    levels_file.write_text("[]", encoding="utf-8")
    result = advisor.check_and_reload_optionmate_levels(
        levels_path=levels_file, force=True, session_date=today_str
    )
    assert result == {}
    assert advisor.cached_rbfn_grids["NIFTY"] is None
    assert advisor.rbfn_grids_frozen["NIFTY"] is False
    assert advisor.cached_rbfn_signals["NIFTY"] is None


def test_missing_required_levels_abstain_without_heuristic_fallback(tmp_path: Path, monkeypatch):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "missing-levels-trace.jsonl"
    advisor.check_and_reload_optionmate_levels(
        levels_path=tmp_path / "absent.json", force=True, session_date=today.isoformat()
    )
    assert advisor._ground_truth_required["NIFTY"] is True
    ts = _india_ts(today)
    _freeze_advisor_clock(monkeypatch, _india_ts(today, dt_time(10, 5)))
    epoch, bar_time = _completed_bar_clock(ts)
    with patch.object(advisor, "_compute_rbfn_grid", side_effect=AssertionError("heuristic fallback")) as compute:
        signal = advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
            bar_close=24005, bar_volume=1, bar_time=bar_time,
            timestamp_ms=ts, epoch_5min=epoch,
        )
    assert signal is not None and signal.veto_reason == "GROUND_TRUTH_LEVELS_REQUIRED"
    compute.assert_not_called()


def test_valid_same_session_reload_recovers_after_missing_levels(tmp_path: Path, monkeypatch):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    today_str = today.isoformat()
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "valid-levels-trace.jsonl"
    advisor.check_and_reload_optionmate_levels(
        levels_path=tmp_path / "absent.json", force=True, session_date=today_str
    )
    levels = tmp_path / "levels.json"
    levels.write_text(json.dumps({"NIFTY": {
        "date": today_str, "trend_decider": 24000.0, "rp1_upper": 24120.0,
        "rp2_upper": 24240.0, "rp1_lower": 23880.0, "rp2_lower": 23760.0,
        "spot_open": 24000.0,
    }}), encoding="utf-8")
    result = advisor.check_and_reload_optionmate_levels(
        levels_path=levels, force=True, session_date=today_str
    )
    assert result["NIFTY"] is True
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    _seed_complete_mode5_or_pair(advisor, "NIFTY", today)
    ts = _india_ts(today)
    _freeze_advisor_clock(monkeypatch, _india_ts(today, dt_time(10, 5)))
    epoch, bar_time = _completed_bar_clock(ts)
    with patch.object(advisor, "_compute_rbfn_grid", side_effect=AssertionError("recomputed valid grid")) as compute:
        signal = advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
            bar_close=24005, bar_volume=1, bar_time=bar_time,
            timestamp_ms=ts, epoch_5min=epoch,
        )
    assert signal is not None and signal.veto_reason != "GROUND_TRUTH_LEVELS_REQUIRED"
    compute.assert_not_called()


def test_never_opted_in_path_retains_legacy_heuristic(tmp_path: Path, monkeypatch):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "legacy-trace.jsonl"
    advisor.seed_prior_day_levels("NIFTY", pdh=24100.0, pdl=23900.0, pdc=24000.0, atr_20=160.0)
    assert advisor._ground_truth_required["NIFTY"] is False
    _seed_complete_mode5_or_pair(advisor, "NIFTY", today)
    original = advisor._compute_rbfn_grid
    ts = _india_ts(today)
    _freeze_advisor_clock(monkeypatch, _india_ts(today, dt_time(10, 5)))
    epoch, bar_time = _completed_bar_clock(ts)
    with patch.object(advisor, "_compute_rbfn_grid", wraps=original) as compute:
        advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
            bar_close=24005, bar_volume=1, bar_time=bar_time,
            timestamp_ms=ts, epoch_5min=epoch,
        )
    compute.assert_called_once()


def test_stale_prior_session_levels_preserve_valid_current_grid(tmp_path: Path):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    today_str = today.isoformat()
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "stale-level-trace.jsonl"
    assert advisor.inject_optionmate_levels(
        "NIFTY", 24000, 24120, 24240, 23880, 23760, date_str=today_str
    )
    grid = advisor.cached_rbfn_grids["NIFTY"]
    signal = SimpleNamespace(action="BUY_CALL")
    advisor.cached_rbfn_signals["NIFTY"] = signal
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps({"NIFTY": {
        "date": (today - timedelta(days=1)).isoformat(),
        "trend_decider": 24000, "rp1_upper": 24120, "rp2_upper": 24240,
        "rp1_lower": 23880, "rp2_lower": 23760,
    }}), encoding="utf-8")
    result = advisor.check_and_reload_optionmate_levels(
        levels_path=stale, force=True, session_date=today_str
    )
    assert result["NIFTY"] is False
    assert advisor.cached_rbfn_grids["NIFTY"] is grid
    assert advisor.rbfn_grids_frozen["NIFTY"] is True and grid.is_ground_truth is True
    assert advisor.cached_rbfn_signals["NIFTY"] is signal


def test_spot_timestamp_rejects_duplicate_or_decreasing_before_mutation(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.trade_lock_active = False
    timestamp_ms = int(datetime(2026, 11, 18, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    _freeze_advisor_clock(monkeypatch, timestamp_ms)
    assert advisor._update_spot("NIFTY", 24000.0, timestamp_ms) is True
    original_spot = advisor.spots["NIFTY"]
    original_spot_timestamp = advisor.spots_ts_ms["NIFTY"]
    assert advisor._update_spot("NIFTY", 23900.0, timestamp_ms) is False
    assert advisor._update_spot("NIFTY", 23900.0, timestamp_ms - 1) is False
    assert advisor.spots["NIFTY"] == original_spot
    assert advisor.spots_ts_ms["NIFTY"] == original_spot_timestamp


def test_stale_recognized_spot_tick_is_full_aggregation_noop(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "stale-tick-trace.jsonl"
    ts_ms = _india_ts(date(2026, 11, 18), dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, ts_ms)
    advisor.on_tick(_spot_tick(ts_ms, 24000.0, 1))

    router = advisor.regime_routers["NIFTY"]
    before = (
        advisor.spots["NIFTY"], advisor.spots_ts_ms["NIFTY"],
        _bucket_snapshot(advisor.bar_buckets["NIFTY"]),
        _bucket_snapshot(advisor.bar_buckets_5m["NIFTY"]),
        advisor._last_spot_timestamp_ms["NIFTY"],
        advisor._last_5m_timestamp_ms["NIFTY"],
        advisor._last_completed_5m_epoch["NIFTY"],
        frozenset(advisor.evaluated_5m_epochs["NIFTY"]),
        _router_snapshot(router),
    )
    advisor.on_tick(_spot_tick(ts_ms, 23900.0, 2))  # exact duplicate timestamp
    after = (
        advisor.spots["NIFTY"], advisor.spots_ts_ms["NIFTY"],
        _bucket_snapshot(advisor.bar_buckets["NIFTY"]),
        _bucket_snapshot(advisor.bar_buckets_5m["NIFTY"]),
        advisor._last_spot_timestamp_ms["NIFTY"],
        advisor._last_5m_timestamp_ms["NIFTY"],
        advisor._last_completed_5m_epoch["NIFTY"],
        frozenset(advisor.evaluated_5m_epochs["NIFTY"]),
        _router_snapshot(router),
    )
    assert after == before


def test_concurrent_spot_updates_serialize_to_latest_timestamp(tmp_path: Path, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "wal.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "concurrent-tick-trace.jsonl"
    base_ts = _india_ts(date(2026, 11, 18), dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, base_ts)
    barrier = threading.Barrier(3)

    def send(ts_ms: int, price: float, seq: int) -> None:
        barrier.wait()
        advisor.on_tick(_spot_tick(ts_ms, price, seq))

    older = threading.Thread(target=send, args=(base_ts, 24000.0, 1))
    newer = threading.Thread(target=send, args=(base_ts + 1000, 24001.0, 2))
    older.start()
    newer.start()
    barrier.wait()
    older.join()
    newer.join()

    assert advisor._last_spot_timestamp_ms["NIFTY"] == base_ts + 1000
    assert advisor.spots_ts_ms["NIFTY"] == base_ts + 1000
    assert advisor.spots["NIFTY"] == 24001.0
    assert advisor.bar_buckets["NIFTY"].last_timestamp_ms == base_ts + 1000
    assert advisor.bar_buckets_5m["NIFTY"].last_timestamp_ms == base_ts + 1000


@pytest.mark.parametrize("candidate_kind", [
    "duplicate_timestamp_epoch",
    "same_epoch_later_timestamp",
    "decreasing_timestamp_epoch",
    "prior_session",
])
def test_rejected_bar_candidates_preserve_state(tmp_path: Path, candidate_kind: str, monkeypatch):
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / f"{candidate_kind}.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / f"{candidate_kind}-trace.jsonl"
    today = date(2026, 11, 18)
    _seed_complete_mode5_or_pair(advisor, "NIFTY", today)
    ts = _india_ts(today, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, _india_ts(today, dt_time(10, 10)))
    epoch, bar_time = _completed_bar_clock(ts)
    advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
        bar_close=24005, bar_volume=1, bar_time=bar_time,
        timestamp_ms=ts, epoch_5min=epoch,
    )
    grid = advisor.cached_rbfn_grids["NIFTY"]
    signal = advisor.cached_rbfn_signals["NIFTY"]
    before = (
        advisor._last_5m_timestamp_ms["NIFTY"], advisor._last_completed_5m_epoch["NIFTY"],
        tuple(dict(row) for row in advisor.bars_5m_history["NIFTY"]),
        grid, advisor.rbfn_grids_frozen["NIFTY"], signal,
        advisor.session_open_prices["NIFTY"], advisor._rp2_session_dates["NIFTY"],
    )
    if candidate_kind == "duplicate_timestamp_epoch":
        candidate_ts, candidate_epoch = ts, epoch
    elif candidate_kind == "same_epoch_later_timestamp":
        candidate_ts, candidate_epoch = ts + 1000, epoch
    elif candidate_kind == "decreasing_timestamp_epoch":
        candidate_ts, candidate_epoch = ts - 300000, epoch - 1
    else:
        candidate_ts = _india_ts(today - timedelta(days=1), dt_time(10, 0))
        candidate_epoch, candidate_bar_time = _completed_bar_clock(candidate_ts)
    if candidate_kind != "prior_session":
        _, candidate_bar_time = _completed_bar_clock(candidate_ts)
    result = advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=23900, bar_high=23910, bar_low=23890,
        bar_close=23905, bar_volume=2, bar_time=candidate_bar_time,
        timestamp_ms=candidate_ts, epoch_5min=candidate_epoch,
    )
    after = (
        advisor._last_5m_timestamp_ms["NIFTY"], advisor._last_completed_5m_epoch["NIFTY"],
        tuple(dict(row) for row in advisor.bars_5m_history["NIFTY"]),
        advisor.cached_rbfn_grids["NIFTY"], advisor.rbfn_grids_frozen["NIFTY"],
        advisor.cached_rbfn_signals["NIFTY"], advisor.session_open_prices["NIFTY"],
        advisor._rp2_session_dates["NIFTY"],
    )
    assert result is None
    assert after[:3] == before[:3]
    assert after[3] is before[3]
    assert after[4] == before[4]
    assert after[5] is before[5]
    assert after[6:] == before[6:]


def test_future_clock_skew_exact_bound_and_just_over_rejected_before_mutation(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(advisor_module.app_config, "MAX_CLOCK_SKEW_SEC", 5.0)
    day = date(2026, 11, 18)
    now_ms = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, now_ms)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")

    spot_advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "spot-skew.json"), enable_stdout=False)
    spot_advisor.trade_lock_active = False
    assert spot_advisor._update_spot("NIFTY", 24000, now_ms + 5000) is True
    spot_snapshot = (
        spot_advisor.spots["NIFTY"], spot_advisor.spots_ts_ms["NIFTY"],
        spot_advisor._last_spot_timestamp_ms["NIFTY"],
    )
    assert spot_advisor._update_spot("NIFTY", 23900, now_ms + 5001) is False
    assert (
        spot_advisor.spots["NIFTY"], spot_advisor.spots_ts_ms["NIFTY"],
        spot_advisor._last_spot_timestamp_ms["NIFTY"],
    ) == spot_snapshot

    bar_advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "bar-skew.json"), enable_stdout=False)
    bar_advisor.decision_trace_path = tmp_path / "bar-skew-trace.jsonl"
    _seed_complete_mode5_or_pair(bar_advisor, "NIFTY", date(2026, 11, 18))
    exact_ts = now_ms + 5000
    exact_epoch, exact_time = _completed_bar_clock(exact_ts)
    assert bar_advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
        bar_close=24005, bar_volume=1, bar_time=exact_time,
        timestamp_ms=exact_ts, epoch_5min=exact_epoch,
    ) is not None
    bar_snapshot = (
        bar_advisor._last_5m_timestamp_ms["NIFTY"],
        bar_advisor._last_completed_5m_epoch["NIFTY"],
        tuple(dict(row) for row in bar_advisor.bars_5m_history["NIFTY"]),
        bar_advisor.cached_rbfn_signals["NIFTY"],
    )
    over_ts = now_ms + 5001
    over_epoch, over_time = _completed_bar_clock(over_ts)
    assert bar_advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=23900, bar_high=23910, bar_low=23890,
        bar_close=23905, bar_volume=1, bar_time=over_time,
        timestamp_ms=over_ts, epoch_5min=over_epoch,
    ) is None
    assert (
        bar_advisor._last_5m_timestamp_ms["NIFTY"],
        bar_advisor._last_completed_5m_epoch["NIFTY"],
        tuple(dict(row) for row in bar_advisor.bars_5m_history["NIFTY"]),
        bar_advisor.cached_rbfn_signals["NIFTY"],
    ) == bar_snapshot


def test_completed_bar_epoch_and_next_ist_boundary_contract(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    first_ts = _india_ts(day, dt_time(10, 4, 59, 999000))
    second_ts = _india_ts(day, dt_time(10, 5, 0))
    _freeze_advisor_clock(monkeypatch, _india_ts(day, dt_time(10, 10)))
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "bar-boundary.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "bar-boundary-trace.jsonl"
    _seed_complete_mode5_or_pair(advisor, "NIFTY", day)

    for timestamp_ms in (first_ts, second_ts):
        epoch, bar_time = _completed_bar_clock(timestamp_ms)
        assert advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
            bar_close=24005, bar_volume=1, bar_time=bar_time,
            timestamp_ms=timestamp_ms, epoch_5min=epoch,
        ) is not None
        assert advisor._last_5m_timestamp_ms["NIFTY"] == timestamp_ms
        assert advisor._last_completed_5m_epoch["NIFTY"] == timestamp_ms // 300000

    before = (
        advisor._last_5m_timestamp_ms["NIFTY"], advisor._last_completed_5m_epoch["NIFTY"],
        tuple(dict(row) for row in advisor.bars_5m_history["NIFTY"]),
        advisor.cached_rbfn_signals["NIFTY"],
    )
    mismatched_ts = second_ts + 1000
    actual_epoch, actual_time = _completed_bar_clock(mismatched_ts)
    assert advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=23900, bar_high=23910, bar_low=23890,
        bar_close=23905, bar_volume=1, bar_time=actual_time,
        timestamp_ms=mismatched_ts, epoch_5min=actual_epoch + 1,
    ) is None
    assert advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=23900, bar_high=23910, bar_low=23890,
        bar_close=23905, bar_volume=1, bar_time=actual_time,
        timestamp_ms=mismatched_ts, epoch_5min=actual_epoch,
    ) is None
    assert (
        advisor._last_5m_timestamp_ms["NIFTY"], advisor._last_completed_5m_epoch["NIFTY"],
        tuple(dict(row) for row in advisor.bars_5m_history["NIFTY"]),
        advisor.cached_rbfn_signals["NIFTY"],
    ) == before


def test_ist_session_decisions_are_host_timezone_independent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    day = date(2026, 11, 17)
    ts_ms = _india_ts(day, dt_time(9, 30))
    _freeze_advisor_clock(monkeypatch, ts_ms)
    advisors = [
        SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "tz-utc.json"), enable_stdout=False),
        SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "tz-ist.json"), enable_stdout=False),
    ]
    original_tz = os.environ.get("TZ")
    try:
        results = []
        for advisor, tz in zip(advisors, ("UTC", "Asia/Kolkata")):
            os.environ["TZ"] = tz
            time.tzset()
            advisor.trade_lock_active = True
            assert advisor._update_spot("NIFTY", 24000, ts_ms) is True
            results.append((
                advisor.or_bounds["NIFTY"]["high"], advisor.or_bounds["NIFTY"]["low"],
                advisor.trade_lock_active,
            ))
        assert results[0] == results[1] == (24000.0, 24000.0, True)
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()


def test_india_local_date_transition_resets_only_current_index_opening_range(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    transition_ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, transition_ts)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "or-rollover.json"), enable_stdout=False)
    advisor.trade_lock_active = False
    advisor._rp2_session_dates["NIFTY"] = day - timedelta(days=1)
    advisor._rp2_session_dates["SENSEX"] = day - timedelta(days=1)
    advisor.or_bounds["NIFTY"] = {"high": 24050.0, "low": 23950.0}
    advisor.or_bounds["SENSEX"] = {"high": 81000.0, "low": 80800.0}
    advisor.or_bounds["BANKNIFTY"] = {"high": 48000.0, "low": 47800.0}
    advisor.active_range_high = 24050.0
    advisor.active_range_low = 23950.0

    assert advisor._update_spot("NIFTY", 24010, transition_ts) is True
    assert advisor.or_bounds["NIFTY"] == {"high": -math.inf, "low": math.inf}
    assert advisor.active_range_high == -math.inf and advisor.active_range_low == math.inf
    assert advisor.or_bounds["SENSEX"] == {"high": 81000.0, "low": 80800.0}
    assert advisor.or_bounds["BANKNIFTY"] == {"high": 48000.0, "low": 47800.0}


def test_same_session_spot_does_not_clear_nifty_active_range(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    current_ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, current_ts)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "same-session.json"), enable_stdout=False)
    advisor.trade_lock_active = False
    advisor._rp2_session_dates["NIFTY"] = day
    advisor.or_evidence["NIFTY"] = {"session_date": day.isoformat(), "status": "COMPLETE"}
    advisor.or_bounds["NIFTY"] = {"high": 24050.0, "low": 23950.0}
    advisor.active_range_high = 24050.0
    advisor.active_range_low = 23950.0

    assert advisor._update_spot("NIFTY", 24010, current_ts) is True
    assert advisor.active_range_high == 24050.0
    assert advisor.active_range_low == 23950.0
    assert advisor.or_bounds["NIFTY"] == {"high": 24050.0, "low": 23950.0}


@pytest.mark.parametrize(("index_name", "spot", "bounds"), [
    ("SENSEX", 81000.0, {"high": 81000.0, "low": 80800.0}),
    ("BANKNIFTY", 48000.0, {"high": 48000.0, "low": 47800.0}),
])
def test_non_nifty_rollover_preserves_nifty_active_range(
    tmp_path: Path,
    monkeypatch,
    index_name: str,
    spot: float,
    bounds: dict[str, float],
):
    day = date(2026, 11, 18)
    transition_ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, transition_ts)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / f"{index_name.lower()}-rollover.json"), enable_stdout=False)
    advisor.trade_lock_active = False
    advisor._rp2_session_dates[index_name] = day - timedelta(days=1)
    advisor.or_bounds[index_name] = dict(bounds)
    advisor.active_range_high = 24050.0
    advisor.active_range_low = 23950.0

    assert advisor._update_spot(index_name, spot, transition_ts) is True
    assert advisor.or_bounds[index_name] == {"high": -math.inf, "low": math.inf}
    assert advisor.active_range_high == 24050.0
    assert advisor.active_range_low == 23950.0


@pytest.mark.parametrize(("index_name", "instrument_key"), [
    ("NIFTY", "NSE_FO|45408"),
    ("NIFTY", "NSE_FO|NIFTY26NOV24150CE"),
    ("BANKNIFTY", "NSE_FO|BANKNIFTY_52000_PE"),
    ("BANKNIFTY", "NSE_FO|45408"),
    ("SENSEX", "BSE_FO|81400PE"),
    ("SENSEX", "BSE_FO|SENSEX26NOV81400CE"),
])
def test_canonical_option_instrument_keys_are_accepted(index_name: str, instrument_key: str):
    assert SentinelLiveStreamAdvisor._canonical_option_instrument_key(index_name, instrument_key) == instrument_key


@pytest.mark.parametrize(("index_name", "instrument_key"), [
    ("NIFTY", "NSE_FO|"),
    ("NIFTY", "BSE_FO|45408"),
    ("SENSEX", "NSE_FO|81400PE"),
    ("NIFTY", "NSE_FO|A B"),
    ("NIFTY", "NSE_FO|A|B"),
    ("NIFTY", "NSE_FO|ＡＢＣ"),
    ("NIFTY", "NIFTY 24150 CE"),
    ("NIFTY", "NSE_FO|BANKNIFTY_52000_PE"),
    ("BANKNIFTY", "NSE_FO|NIFTY26NOV24150CE"),
    ("SENSEX", "BSE_FO|NIFTY26NOV24150CE"),
])
def test_malformed_option_instrument_keys_are_rejected(index_name: str, instrument_key: str):
    assert SentinelLiveStreamAdvisor._canonical_option_instrument_key(index_name, instrument_key) is None


@pytest.mark.parametrize(("display_symbol", "expected_index"), [
    ("NIFTY 27000 CE 29 DEC 26", "NIFTY"),
    ("BANKNIFTY 52000 PE 29 DEC 26", "BANKNIFTY"),
    ("SENSEX 81400 CE 29 DEC 26", "SENSEX"),
    ("NIFTY 25400 CE", "NIFTY"),
])
def test_option_display_symbol_resolves_only_supported_index_prefixes(display_symbol: str, expected_index: str):
    assert SentinelLiveStreamAdvisor._resolve_option_index_from_display_symbol(display_symbol) == expected_index


@pytest.mark.parametrize("display_symbol", [
    "OTHERINDEX 24150 CE",
    "NIFTYFPI 27000 CE 29 DEC 26",
    "SENSEX50 81400 CE 29 DEC 26",
    "NIFTY26NOV24150CE",
])
def test_unsupported_display_symbol_boundaries_fail_closed(display_symbol: str):
    assert SentinelLiveStreamAdvisor._resolve_option_index_from_display_symbol(display_symbol) is None


@pytest.mark.parametrize(("display_symbol", "instrument_key", "apm_index"), [
    ("OTHERINDEX 24150 CE", "NSE_FO|45408", "NIFTY"),
    ("NIFTYFPI 27000 CE 29 DEC 26", "NSE_FO|45408", "NIFTY"),
    ("SENSEX50 81400 CE 29 DEC 26", "BSE_FO|81400PE", "SENSEX"),
])
def test_unknown_option_symbol_with_valid_key_is_vetoed_before_dispatch(
    tmp_path: Path,
    monkeypatch,
    display_symbol: str,
    instrument_key: str,
    apm_index: str,
):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "unknown-option-symbol.json"), enable_stdout=False)
    dispatcher = Mock()
    advisor.automated_dispatcher = dispatcher
    advisor.apms[apm_index].state = "EXIT_PENDING"

    advisor._evaluate_option_depth(SimpleNamespace(
        token=instrument_key,
        symbol=display_symbol,
    ))

    assert advisor.veto_counters["UNKNOWN_OPTION_UNDERLYING_SYMBOL"] == 1
    assert advisor.apms[apm_index].state == "EXIT_PENDING"
    dispatcher.on_apm_entry.assert_not_called()
    dispatcher.on_apm_exit.assert_not_called()


@pytest.mark.parametrize(("display_symbol", "instrument_key"), [
    ("NIFTY 25400 CE", "NSE_FO|BANKNIFTY_52000_PE"),
    ("BANKNIFTY 52000 PE", "NSE_FO|NIFTY26NOV24150CE"),
    ("SENSEX 81400 CE", "BSE_FO|NIFTY26NOV24150CE"),
])
def test_symbolic_key_underlying_mismatch_vetoes_before_dispatch(
    tmp_path: Path,
    monkeypatch,
    display_symbol: str,
    instrument_key: str,
):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "symbol-key-mismatch.json"), enable_stdout=False)
    dispatcher = Mock()
    advisor.automated_dispatcher = dispatcher
    advisor.apms["NIFTY"].state = "EXIT_PENDING"

    advisor._evaluate_option_depth(SimpleNamespace(token=instrument_key, symbol=display_symbol))

    assert advisor.veto_counters["BROKER_INSTRUMENT_KEY"] == 1
    assert advisor.apms["NIFTY"].state == "EXIT_PENDING"
    dispatcher.on_apm_entry.assert_not_called()
    dispatcher.on_apm_exit.assert_not_called()


@pytest.mark.parametrize("apm_state", ["STANDBY", "IN_FLIGHT", "EXIT_PENDING"])
def test_invalid_instrument_key_vetoes_before_entry_or_exit_dispatch(tmp_path: Path, monkeypatch, apm_state: str):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / f"key-veto-{apm_state}.json"), enable_stdout=False)
    dispatcher = Mock()
    advisor.automated_dispatcher = dispatcher
    advisor.apms["NIFTY"].state = apm_state
    depth = SimpleNamespace(token="NIFTY 24150 CE", symbol="NIFTY 24150 CE")

    advisor._evaluate_option_depth(depth)

    assert advisor.apms["NIFTY"].state == apm_state
    assert advisor.veto_counters["BROKER_INSTRUMENT_KEY"] == 1
    dispatcher.on_apm_entry.assert_not_called()
    dispatcher.on_apm_exit.assert_not_called()

def test_gate_sentinel_08_incomplete_attribute_grid_deprecation(tmp_path: Path, monkeypatch):
    """GATE-SENTINEL-08: Incomplete level attributes immediately unfreeze grid and clear is_ground_truth."""
    wal = tmp_path / "test_wal_incomplete.json"
    levels_file = tmp_path / "optionmate_daily_levels.json"
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    today_str = today.isoformat()

    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "incomplete-levels-trace.jsonl"

    # First inject valid levels via JSON reload
    valid_payload = {
        "NIFTY": {
            "date": today_str,
            "trend_decider": 24000.0,
            "rp1_upper": 24120.0,
            "rp2_upper": 24240.0,
            "rp1_lower": 23880.0,
            "rp2_lower": 23760.0,
            "spot_open": 24000.0,
        }
    }
    levels_file.write_text(json.dumps(valid_payload))
    res_init = advisor.check_and_reload_optionmate_levels(levels_path=levels_file, force=True, session_date=today_str)
    assert res_init["NIFTY"] is True
    assert res_init["SENSEX"] is False
    assert res_init["BANKNIFTY"] is False
    grid = advisor.cached_rbfn_grids["NIFTY"]
    assert advisor.rbfn_grids_frozen["NIFTY"] is True
    assert getattr(grid, "is_ground_truth", False) is True

    # Create OptionMate file with missing attribute (e.g. rp2_upper is None)
    incomplete_payload = {
        "NIFTY": {
            "date": today_str,
            "trend_decider": 24000.0,
            "rp1_upper": 24120.0,
            "rp2_upper": None,  # INCOMPLETE!
            "rp1_lower": 23880.0,
            "rp2_lower": 23760.0,
            "spot_open": 24000.0,
        }
    }
    levels_file.write_text(json.dumps(incomplete_payload))

    results = advisor.check_and_reload_optionmate_levels(levels_path=levels_file, force=True, session_date=today_str)
    assert results.get("NIFTY") is False
    assert advisor.rbfn_grids_frozen["NIFTY"] is False
    assert getattr(grid, "is_ground_truth", False) is False
    assert advisor._ground_truth_required["NIFTY"] is True
    ts = _india_ts(today)
    _freeze_advisor_clock(monkeypatch, _india_ts(today, dt_time(10, 5)))
    epoch, bar_time = _completed_bar_clock(ts)
    with patch.object(advisor, "_compute_rbfn_grid", side_effect=AssertionError("heuristic fallback")) as compute:
        signal = advisor._on_5m_bar_close(
            index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
            bar_close=24005, bar_volume=1, bar_time=bar_time,
            timestamp_ms=ts, epoch_5min=epoch,
        )
    assert signal is not None and signal.veto_reason == "GROUND_TRUTH_LEVELS_REQUIRED"
    compute.assert_not_called()


def test_gate_sentinel_09_zero_timestamp_eviction(tmp_path: Path):
    """GATE-SENTINEL-09: Signals with timestamp_ms <= 0 are immediately evicted."""
    wal = tmp_path / "test_wal_zero_ts.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)

    zero_ts_sig = CachedRBFNAuctionSignal(
        timestamp_ms=0,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="UP",
        target_strike=24100.0,
        target_pts=50.0,
        sl_pts=25.0,
        setup_reason="TEST_ZERO_TS",
        trade_phase="MODE_5_BREAKOUT",
        bar_time=dt_time(10, 0),
        is_active=True,
    )
    advisor.cached_rbfn_signals["NIFTY"] = zero_ts_sig

    cached = advisor.get_valid_cached_rbfn_signal("NIFTY", current_timestamp_ms=1793193000000, ttl_seconds=300.0)
    assert cached is None
    assert advisor.cached_rbfn_signals.get("NIFTY") is None

    # Test negative timestamp as well
    neg_ts_sig = CachedRBFNAuctionSignal(
        timestamp_ms=-100,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="UP",
        target_strike=24100.0,
        target_pts=50.0,
        sl_pts=25.0,
        setup_reason="TEST_NEG_TS",
        trade_phase="MODE_5_BREAKOUT",
        bar_time=dt_time(10, 0),
        is_active=True,
    )
    advisor.cached_rbfn_signals["NIFTY"] = neg_ts_sig
    cached_neg = advisor.get_valid_cached_rbfn_signal("NIFTY", current_timestamp_ms=1793193000000, ttl_seconds=300.0)
    assert cached_neg is None
    assert advisor.cached_rbfn_signals.get("NIFTY") is None


def test_gate_sentinel_10_broker_position_exception_propagation():
    """GATE-SENTINEL-10: UpstoxBrokerAdapter.fetch_open_positions raises RuntimeError on failure."""
    adapter = UpstoxBrokerAdapter(access_token="fake_token")
    # Inject a transport failure without opening a socket or contacting a service.
    with patch("core.broker.upstox_broker_adapter.urllib.request.urlopen", side_effect=URLError("mocked timeout")):
        with pytest.raises(RuntimeError) as exc_info:
            adapter.fetch_open_positions()

    assert "Broker position fetch failed" in str(exc_info.value)


def test_gate_sentinel_11_unconfigured_broker_fail_closed(tmp_path: Path):
    """GATE-SENTINEL-11: Reconciler fails closed when broker adapter is None."""
    reconciler = BrokerPositionReconciler(broker=None)

    # 1. fetch_broker_positions returns success=False and unconfigured message
    success, positions, err_msg = reconciler.fetch_broker_positions()
    assert success is False
    assert positions == []
    assert "UNCONFIGURED_BROKER" in (err_msg or "")

    # 2. reconcile_before_wal_reset returns wal_reset_permitted=False
    wal_file = tmp_path / "dummy_wal.json"
    wal_file.write_text("{}")
    res = reconciler.reconcile_before_wal_reset(wal_path=wal_file, index_name="NIFTY")
    assert res.wal_reset_permitted is False
    assert res.status == "UNCONFIGURED_BROKER"
    assert "BLOCKED_FAIL_CLOSED" in res.message


def test_gate_sentinel_12_webhook_auth_guard():
    """Reject a webhook when no authentication secret or passphrase is configured."""
    receiver = TradingViewLevelReceiver(secret_key=None, passphrase=None, require_auth=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "index": "NIFTY",
        "date": today_str,
        "trend_decider": 24000.0,
        "rp1_upper": 24120.0,
        "rp2_upper": 24240.0,
        "rp1_lower": 23880.0,
        "rp2_lower": 23760.0,
    }
    res = receiver.process_webhook(raw_body=payload, session_date=today_str)
    assert res["success"] is False
    assert res["error"] == "AUTHENTICATION_REQUIRED: No webhook secret or passphrase configured"
    assert res["persisted"] is False


def test_safety_invariants_hardening_003(tmp_path: Path):
    """Verify safety invariants are strictly maintained across all modules."""
    reconciler = BrokerPositionReconciler()
    res = reconciler.reconcile_before_wal_reset(wal_path=str(tmp_path / "dummy_wal.json"))
    assert res.read_only is True
    assert res.is_order_action is False
    assert res.allowed_for_live_execution is False

    receiver = TradingViewLevelReceiver()
    assert receiver.storage_path is not None


def _v2_or_candles(session_day: date) -> list[list[object]]:
    ist = ZoneInfo("Asia/Kolkata")
    start = datetime.combine(session_day, dt_time(9, 15), tzinfo=ist)
    return [
        [(start + timedelta(minutes=minute)).isoformat(), 100.0, 101.0, 99.0, 100.0, 1]
        for minute in range(30)
    ]


def test_mode5_or_v2_seed_requires_exact_aware_same_session_coverage(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    candles = _v2_or_candles(day)
    parsed = SentinelLiveStreamAdvisor._parse_complete_v2_or_candles(candles, day)
    assert parsed is not None
    assert parsed["coverage_count"] == 30
    assert parsed["high"] == 101.0 and parsed["low"] == 99.0

    incomplete = candles[:-1]
    duplicate = candles + [list(candles[0])]
    naive = [list(row) for row in candles]
    naive[0][0] = "2026-11-18T09:15:00"
    malformed_ohlc = [list(row) for row in candles]
    malformed_ohlc[0][2] = float("nan")
    stale = candles + [[
        datetime.combine(day - timedelta(days=1), dt_time(9, 15), tzinfo=ZoneInfo("Asia/Kolkata")).isoformat(),
        100.0, 101.0, 99.0, 100.0, 1,
    ]]
    for candidate in (incomplete, duplicate, naive, malformed_ohlc, stale):
        assert SentinelLiveStreamAdvisor._parse_complete_v2_or_candles(candidate, day) is None

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.combine(day, dt_time(10, 0), tzinfo=tz)

    monkeypatch.setattr(advisor_module, "datetime", FrozenDateTime)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "unit-test-token")
    response = SimpleNamespace(status_code=200, json=lambda: {"data": {"candles": candles}})
    with patch("requests.get", return_value=response) as get:
        advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "or-seed.json"), enable_stdout=False)
    assert get.call_count == 3
    assert {call.args[0] for call in get.call_args_list} == {
        "https://api.upstox.com/v2/historical-candle/intraday/NSE_INDEX%7CNifty%2050/1minute",
        "https://api.upstox.com/v2/historical-candle/intraday/NSE_INDEX%7CNifty%20Bank/1minute",
        "https://api.upstox.com/v2/historical-candle/intraday/BSE_INDEX%7CSENSEX/1minute",
    }
    for index_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert advisor.or_evidence[index_name]["status"] == "COMPLETE"
        assert advisor.or_evidence[index_name]["coverage_count"] == 30
        complete_boundary = _india_ts(day, dt_time(10, 0))
        assert advisor._validate_mode5_or_evidence(
            index_name, complete_boundary, complete_boundary
        )[0] is True


def test_mode5_or_later_rows_are_validated_but_excluded_from_bounds():
    day = date(2026, 11, 18)
    candles = _v2_or_candles(day)
    later_ts = datetime.combine(day, dt_time(9, 45), tzinfo=ZoneInfo("Asia/Kolkata")).isoformat()
    parsed = SentinelLiveStreamAdvisor._parse_complete_v2_or_candles(
        candles + [[later_ts, 100.0, 999.0, 99.0, 100.0, 1]], day
    )
    assert parsed is not None and parsed["high"] == 101.0 and parsed["low"] == 99.0
    for invalid in (True, "999"):
        later = [later_ts, 100.0, invalid, 99.0, 100.0, 1]
        assert SentinelLiveStreamAdvisor._parse_complete_v2_or_candles(candles + [later], day) is None


def _configure_mode5_depth_entry_test(advisor, tmp_path: Path, day: date, timestamp_ms: int):
    _seed_complete_mode5_or_pair(advisor, "NIFTY", day)
    advisor.decision_trace_path = tmp_path / f"entry-lock-{timestamp_ms}.jsonl"
    advisor.spots["NIFTY"] = 24000.0
    advisor.spots_ts_ms["NIFTY"] = timestamp_ms
    advisor._rp2_session_dates["NIFTY"] = day
    advisor.wall_observers["NIFTY"] = None
    advisor.wall_gates["NIFTY"] = None
    advisor.adapter.get_all_depth = Mock(return_value={})
    advisor.evaluate_strike_oi = Mock(return_value=True)
    advisor.evaluate_nifty_frictional_hurdle = Mock(return_value=(True, "OK"))
    advisor.macro_gate.evaluate_alignment = Mock(return_value=(True, "OK"))
    advisor.vol_compression_gate.evaluate_compression = Mock(return_value=(True, "OK", None))
    advisor.confidence_scorer.evaluate_confidence = Mock(return_value=SimpleNamespace(
        is_actionable=True, total_score=90, grade="A", probable_win_rate_pct=70,
        sizing_recommendation="FULL",
    ))
    advisor.passive_midpoint_queue.calculate_entry_fill = Mock(return_value=(100.0, 0.0, "MOCK"))
    advisor.strike_resolver.resolve_target_strike = Mock(return_value=SimpleNamespace(
        target_strike=24100.0, moneyness="ATM",
    ))
    advisor.strike_resolver.is_contract_matching = Mock(return_value=True)
    advisor.apms["NIFTY"].is_cool_off_active = Mock(return_value=False)
    advisor.apms["NIFTY"].arm_and_enter = Mock(return_value=True)
    advisor.journal.record_execution = Mock()
    advisor.automated_dispatcher = Mock()
    advisor.get_valid_cached_rbfn_signal = Mock(return_value=CachedRBFNAuctionSignal(
        timestamp_ms=timestamp_ms, index_name="NIFTY", action="BUY_CALL", direction="CE",
        target_strike=24100.0, target_pts=30.0, sl_pts=20.0,
        setup_reason="MODE5_CONTINUATION", trade_phase="CONTINUOUS_STATE_MACHINE",
        bar_time=dt_time(10, 0), is_active=True,
    ))
    depth = UpstoxLevel5DepthRecord(
        token="NSE_FO|NIFTY26NOV24100CE", symbol="NIFTY 24100 CE",
        exchange_timestamp_ms=timestamp_ms, ingress_monotonic_ns=1, ingress_wall_utc="",
        sequence_id=1, ltp=100.0, volume=1, open_interest=10000,
        bid_p1=99.0, bid_q1=1, bid_o1=1, bid_p2=98.0, bid_q2=1, bid_o2=1,
        bid_p3=97.0, bid_q3=1, bid_o3=1, bid_p4=96.0, bid_q4=1, bid_o4=1,
        bid_p5=95.0, bid_q5=1, bid_o5=1,
        ask_p1=101.0, ask_q1=1, ask_o1=1, ask_p2=102.0, ask_q2=1, ask_o2=1,
        ask_p3=103.0, ask_q3=1, ask_o3=1, ask_p4=104.0, ask_q4=1, ask_o4=1,
        ask_p5=105.0, ask_q5=1, ask_o5=1,
    )
    return depth


def test_mode5_or_recheck_blocks_apm_after_session_rollover(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, ts)
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "rollover-entry.json"), enable_stdout=False)
    depth = _configure_mode5_depth_entry_test(advisor, tmp_path, day, ts)
    validate = advisor._validate_mode5_or_pair
    calls = 0

    def roll_between_checks(index_name, decision_timestamp_ms, completed_bar_boundary_ms=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            advisor._reset_rp2_state_for_session("NIFTY", day + timedelta(days=1))
        return validate(index_name, decision_timestamp_ms, completed_bar_boundary_ms)

    advisor._validate_mode5_or_pair = roll_between_checks
    with patch.object(advisor_module, "calculate_discrete_lots", return_value=(1, "FULL")), \
            patch.object(advisor_module, "get_exchange_lot_size", return_value=1), \
            patch.object(advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike", return_value=SimpleNamespace(target_strike=24100.0)):
        advisor._evaluate_option_depth(depth)
    assert calls >= 2
    advisor.apms["NIFTY"].arm_and_enter.assert_not_called()
    advisor.automated_dispatcher.on_apm_entry.assert_not_called()
    assert advisor.alerts_history[-1].status_flag == "VETO_MODE5_OR"
    assert advisor.alerts_history[-1].advisory == "WAIT (MODE5_OR_UNVERIFIED)"


def test_mode5_dispatch_occurs_after_advisor_lock_is_released(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, ts)
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "unlocked-dispatch.json"), enable_stdout=False)
    depth = _configure_mode5_depth_entry_test(advisor, tmp_path, day, ts)
    def assert_unlocked(**kwargs):
        assert not advisor._lock._is_owned()
    advisor.automated_dispatcher.on_apm_entry.side_effect = assert_unlocked
    with patch.object(advisor_module, "calculate_discrete_lots", return_value=(1, "FULL")), \
            patch.object(advisor_module, "get_exchange_lot_size", return_value=1), \
            patch.object(advisor_module.SentinelOptionStrikeResolver, "resolve_mode5_strike", return_value=SimpleNamespace(target_strike=24100.0)):
        advisor._evaluate_option_depth(depth)
    advisor.apms["NIFTY"].arm_and_enter.assert_called_once()
    advisor.automated_dispatcher.on_apm_entry.assert_called_once()


def test_mode5_or_partial_is_causal_and_expires_at_shock_end(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    event_ts = _india_ts(day, dt_time(9, 20))
    _freeze_advisor_clock(monkeypatch, event_ts)
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "partial-or.json"), enable_stdout=False)
    assert advisor._update_spot("NIFTY", 24000.0, event_ts)
    assert advisor._update_spot("SENSEX", 81000.0, event_ts)
    assert advisor._validate_mode5_or_pair("NIFTY", event_ts, event_ts)[0] is True
    assert advisor._validate_mode5_or_evidence("NIFTY", event_ts - 1, event_ts)[0] is True
    ts_0945 = _india_ts(day, dt_time(9, 45))
    assert advisor._validate_mode5_or_pair("NIFTY", ts_0945, ts_0945)[1] == "MODE5_TARGET_OR_COMPLETE_REQUIRED"


def test_mode5_bar_abstains_before_history_mutation_without_valid_or(tmp_path: Path, monkeypatch):
    day = date(2026, 11, 18)
    ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, _india_ts(day, dt_time(10, 5)))
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / "or-veto.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "or-veto-trace.jsonl"
    epoch, bar_time = _completed_bar_clock(ts)
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=24000, bar_high=24010, bar_low=23990,
        bar_close=24005, bar_volume=1, bar_time=bar_time,
        timestamp_ms=ts, epoch_5min=epoch,
    )
    assert signal is not None and signal.action == "ABSTAIN"
    assert signal.veto_reason == "MODE5_TARGET_OR_BOUNDS_INVALID"
    assert len(advisor.bars_5m_history["NIFTY"]) == 1  # raw observation retained
    assert advisor.bars_5m_strategy_history["NIFTY"] == []  # vetoed bar cannot feed patterns
    advisor._mode5_trace_queue.join()
    records = [json.loads(line) for line in (tmp_path / "or-veto-trace.jsonl").read_text().splitlines()]
    decision_records = [record for record in records if record.get("event_type") == "MODE5_DECISION_TRACE"]
    assert decision_records[-1]["reason"] == signal.veto_reason


@pytest.mark.parametrize("trade_phase", ["OPENING_DRIVE", "CONTINUOUS_STATE_MACHINE"])
def test_mode5_depth_gate_checks_companion_or_before_dispatch(tmp_path: Path, monkeypatch, trade_phase: str):
    day = date(2026, 11, 18)
    ts = _india_ts(day, dt_time(10, 0))
    _freeze_advisor_clock(monkeypatch, ts)
    advisor = SentinelLiveStreamAdvisor(wal_path=str(tmp_path / f"depth-or-{trade_phase}.json"), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / f"depth-or-{trade_phase}.jsonl"
    _seed_complete_mode5_or_pair(advisor, "NIFTY", day)
    advisor.or_bounds["SENSEX"] = {"high": 81010.0, "low": 80990.0}
    advisor.or_evidence["SENSEX"] = {
        "session_date": day.isoformat(), "status": "PARTIAL",
        "source": "UPSTOX_TICK_PARTIAL", "source_timestamp_ms": _india_ts(day, dt_time(9, 20)),
        "coverage_count": 0, "coverage_start_ms": 0, "coverage_end_ms": 0,
    }
    advisor.spots["NIFTY"] = 24000.0
    advisor.spots_ts_ms["NIFTY"] = ts
    dispatcher = Mock()
    advisor.automated_dispatcher = dispatcher
    signal = CachedRBFNAuctionSignal(
        timestamp_ms=ts, index_name="NIFTY", action="BUY_CALL", direction="CE",
        target_strike=24100, target_pts=30, sl_pts=20,
        setup_reason="TEST_MODE5", trade_phase=trade_phase, bar_time=dt_time(10, 0),
        is_active=True,
    )
    advisor.get_valid_cached_rbfn_signal = Mock(return_value=signal)
    depth = UpstoxLevel5DepthRecord(
        token="NSE_FO|NIFTY26NOV24100CE", symbol="NIFTY 24100 CE",
        exchange_timestamp_ms=ts, ingress_monotonic_ns=1, ingress_wall_utc="",
        sequence_id=1, ltp=100.0, volume=1, open_interest=10000,
        bid_p1=99.0, bid_q1=1, bid_o1=1, bid_p2=98.0, bid_q2=1, bid_o2=1,
        bid_p3=97.0, bid_q3=1, bid_o3=1, bid_p4=96.0, bid_q4=1, bid_o4=1,
        bid_p5=95.0, bid_q5=1, bid_o5=1,
        ask_p1=101.0, ask_q1=1, ask_o1=1, ask_p2=102.0, ask_q2=1, ask_o2=1,
        ask_p3=103.0, ask_q3=1, ask_o3=1, ask_p4=104.0, ask_q4=1, ask_o4=1,
        ask_p5=105.0, ask_q5=1, ask_o5=1,
    )
    advisor._evaluate_option_depth(depth)
    dispatcher.assert_not_called()
    assert "MODE5_COMPANION_OR_COMPLETE_REQUIRED" in (tmp_path / f"depth-or-{trade_phase}.jsonl").read_text()
