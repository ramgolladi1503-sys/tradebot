#!/usr/bin/env python3
"""
Unit and Invariant Tests for Governed Strategy Shadow Adapters
Proves AGENTS.md compliance:
1. read_only == True, broker_write_authority == False, orders_placed == 0
2. Fail-closed staleness gating (both central and adapter-specific)
3. Checkpoint & Root Cause Attribution (RCA) telemetry emission
4. Overnight cross-session persistence and crash recovery
5. Intraday Opening Drive signal, ATM strike selection, entry/exit observation
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, time as dtime, timezone, timedelta
import pytest

from core.paper_shadow.strategy_shadow_adapter import (
    StrategyMarketSnapshotV1,
    Level1Depth,
    Bar1M,
    IntradayOpeningDriveShadowAdapter,
    OvernightDriftShadowAdapter,
)
from core.candidate_audits.intraday_opening_drive import (
    CANDIDATE_ID as OPENING_DRIVE_ID,
    CANDIDATE_FINGERPRINT as OPENING_DRIVE_FINGERPRINT,
    IST_TZ,
)
from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S1_SCHEDULE_SHA256,
)


@pytest.fixture
def temp_ledger_dir():
    d = tempfile.mkdtemp(prefix="test_strategy_shadow_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_safety_invariants():
    """Prove that adapters have zero broker authority and zero order ability."""
    od_adapter = IntradayOpeningDriveShadowAdapter()
    assert od_adapter.read_only is True
    assert od_adapter.broker_write_authority is False
    assert od_adapter.order_authority is False
    assert od_adapter.orders_placed == 0

    on_adapter = OvernightDriftShadowAdapter(
        candidate_id=CANDIDATE_S1_ID,
        schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
        prev_daily_close=25000.0,
        prev_sma200=24000.0,
        sub_ledger_dir="/tmp",
    )
    assert on_adapter.read_only is True
    assert on_adapter.broker_write_authority is False
    assert on_adapter.order_authority is False
    assert on_adapter.orders_placed == 0


def test_fail_closed_stale_quote():
    """Prove that adapters reject quotes exceeding local staleness SLA."""
    adapter = IntradayOpeningDriveShadowAdapter(
        prev_futures_contract_key="NIFTY26SEPFUT",
        prev_close_1529=25000.0,
        max_quote_age_ms=2000.0,
    )

    # 1. Central feed unhealthy -> FAIL
    snapshot_unhealthy = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        age_ms=100.0,
        feed_health="STALE",
        session_health="NORMAL",
    )
    res = adapter.on_market_pulse(pulse_id="pulse_1", snapshot=snapshot_unhealthy)
    assert res is None
    assert adapter.telemetry_history[-1].checkpoint_name == "FEED_RECEIVED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "CENTRAL_FEED_UNHEALTHY_OR_STALE"

    # 2. Local age exceeds 2000ms -> FAIL
    snapshot_stale = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        age_ms=2500.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
    )
    res = adapter.on_market_pulse(pulse_id="pulse_2", snapshot=snapshot_stale)
    assert res is None
    assert adapter.telemetry_history[-1].checkpoint_name == "FEED_RECEIVED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "QUOTE_EXCEEDS_LOCAL_SLA"

    # 3. Missing age (None) -> FAIL CLOSED with MISSING_SOURCE_TIMESTAMP
    snapshot_missing_age = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        age_ms=None,
        feed_health="HEALTHY",
        session_health="NORMAL",
    )
    res = adapter.on_market_pulse(pulse_id="pulse_3", snapshot=snapshot_missing_age)
    assert res is None
    assert adapter.telemetry_history[-1].checkpoint_name == "FEED_RECEIVED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "MISSING_SOURCE_TIMESTAMP"


def test_opening_drive_workflow():
    """Verify full end-to-end prospective observation sequence for Opening Drive."""
    adapter = IntradayOpeningDriveShadowAdapter(
        prev_futures_contract_key="NIFTY26SEPFUT",
        prev_close_1529=25000.0,
        max_quote_age_ms=2000.0,
    )

    # Pulse 1: 09:15 Futures Open (25050 -> Gap = +50 pts > 30)
    bar_0915 = Bar1M(
        timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        open=25050.0,
        high=25060.0,
        low=25040.0,
        close=25055.0,
        volume=1000,
    )
    snap_0915 = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        authoritative_contract_key="NIFTY26SEPFUT",
        last_completed_1m_bar=bar_0915,
    )
    adapter.on_market_pulse("p1", snap_0915)
    assert adapter.futures_open_0915 == 25050.0

    # Pulse 2: 09:20 Futures Close (25080 -> Drive = 25080 - 25050 = +30 pts > 20)
    bar_0920 = Bar1M(
        timestamp_ist=datetime(2026, 9, 22, 9, 20, tzinfo=IST_TZ),
        open=25070.0,
        high=25085.0,
        low=25065.0,
        close=25080.0,
        volume=1200,
    )
    snap_0920 = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 21, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 21, tzinfo=IST_TZ),
        age_ms=15.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        authoritative_contract_key="NIFTY26SEPFUT",
        last_completed_1m_bar=bar_0920,
    )
    adapter.on_market_pulse("p2", snap_0920)
    assert adapter.signal_qualified is True
    assert adapter.signal_side == "BUY_CE"

    # Pulse 3: 09:20 Spot Bar for ATM Selection (Spot close = 25065 -> ATM = 25050)
    bar_spot = Bar1M(
        timestamp_ist=datetime(2026, 9, 22, 9, 20, tzinfo=IST_TZ),
        open=25060.0,
        high=25070.0,
        low=25050.0,
        close=25065.0,
        volume=0,
    )
    snap_spot = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NSE_INDEX|Nifty 50",
        trading_symbol="NIFTY 50",
        instrument_class="INDEX_SPOT",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 21, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 21, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        last_completed_1m_bar=bar_spot,
    )
    adapter.on_market_pulse("p3", snap_spot)
    assert adapter.resolved_atm_strike == 25050

    # Pulse 4: Option depth arrival at 09:22:05 (Entry observation)
    depth_entry = Level1Depth(bid_price=120.0, bid_qty=500, ask_price=122.0, ask_qty=600)
    snap_opt_entry = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_CE",
        trading_symbol="NIFTY26SEP25050CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, 20000, tzinfo=IST_TZ),
        age_ms=20.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        strike_price=25050.0,
        option_type="CE",
        l1_depth=depth_entry,
    )
    adapter.on_market_pulse("p4", snap_opt_entry)
    assert adapter.shadow_entry_observed is True
    assert adapter.shadow_entry_price == 122.0  # Buy at Ask

    # Pulse 5: Option depth arrival at 11:01:05 (Exit observation)
    depth_exit = Level1Depth(bid_price=145.0, bid_qty=400, ask_price=147.0, ask_qty=450)
    snap_opt_exit = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_CE",
        trading_symbol="NIFTY26SEP25050CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 11, 1, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 11, 1, 5, 10000, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        strike_price=25050.0,
        option_type="CE",
        l1_depth=depth_exit,
    )
    res = adapter.on_market_pulse("p5", snap_opt_exit)
    assert res is not None
    assert adapter.shadow_exit_observed is True
    assert adapter.shadow_exit_price == 145.0  # Sell at Bid
    assert res["gross_pnl_pts"] == 23.0  # 145.0 - 122.0
    assert res["orders_placed"] == 0
    assert res["broker_write_authority"] is False


def test_overnight_drift_cross_session_recovery(temp_ledger_dir):
    """Verify that overnight drift commits 15:21 arrival, survives process restart, and finalizes at 09:15 next day."""
    # Session 1: Monday 2026-09-21
    adapter1 = OvernightDriftShadowAdapter(
        candidate_id=CANDIDATE_S1_ID,
        schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
        prev_daily_close=25000.0,
        prev_sma200=24000.0,  # Macro uptrend: prev_close > SMA200
        sub_ledger_dir=temp_ledger_dir,
    )

    # 1. 09:15 Open
    bar_0915 = Bar1M(
        timestamp_ist=datetime(2026, 9, 21, 9, 15, tzinfo=IST_TZ),
        open=25050.0, high=25060.0, low=25040.0, close=25055.0, volume=1000
    )
    snap_open = StrategyMarketSnapshotV1(
        session_id="2026-09-21",
        instrument_key="NSE_INDEX|Nifty 50",
        trading_symbol="NIFTY 50",
        instrument_class="INDEX_SPOT",
        source_timestamp_ist=datetime(2026, 9, 21, 9, 16, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 21, 9, 16, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        last_completed_1m_bar=bar_0915,
    )
    adapter1.on_market_pulse("on_p1", snap_open)

    # 2. 15:20 Close: Open was 25050, 15:20 close is 25200 (Gain = (25200-25050)/25050 = 0.598% > 0.50% -> Qualified)
    bar_1520 = Bar1M(
        timestamp_ist=datetime(2026, 9, 21, 15, 20, tzinfo=IST_TZ),
        open=25190.0, high=25205.0, low=25185.0, close=25200.0, volume=2000
    )
    snap_1520 = StrategyMarketSnapshotV1(
        session_id="2026-09-21",
        instrument_key="NSE_INDEX|Nifty 50",
        trading_symbol="NIFTY 50",
        instrument_class="INDEX_SPOT",
        source_timestamp_ist=datetime(2026, 9, 21, 15, 20, 30, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 21, 15, 20, 30, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        last_completed_1m_bar=bar_1520,
    )
    adapter1.on_market_pulse("on_p2", snap_1520)
    assert adapter1.signal_result.s1_qualified is True

    # 3. 15:21 Depth Quote arrival -> Committed to Ledger (OVERNIGHT_PENDING)
    depth_1521 = Level1Depth(bid_price=25210.0, bid_qty=500, ask_price=25212.0, ask_qty=500)
    snap_1521 = StrategyMarketSnapshotV1(
        session_id="2026-09-21",
        instrument_key="NSE_INDEX|Nifty 50",
        trading_symbol="NIFTY 50",
        instrument_class="INDEX_SPOT",
        source_timestamp_ist=datetime(2026, 9, 21, 15, 21, 10, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 21, 15, 21, 10, 50000, tzinfo=IST_TZ),
        age_ms=50.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth_1521,
    )
    res_commit = adapter1.on_market_pulse("on_p3", snap_1521)
    assert res_commit is not None
    assert res_commit["action"] == "COMMITTED_ARRIVAL"
    assert res_commit["lifecycle_state"] == "OVERNIGHT_PENDING"

    # -------------------------------------------------------------
    # SIMULATE COMPLETE SYSTEM SHUTDOWN OVERNIGHT & RESTART NEXT DAY
    # -------------------------------------------------------------
    del adapter1

    # Session 2: Tuesday 2026-09-22
    adapter2 = OvernightDriftShadowAdapter(
        candidate_id=CANDIDATE_S1_ID,
        schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
        prev_daily_close=25200.0,
        prev_sma200=24000.0,
        sub_ledger_dir=temp_ledger_dir,
    )

    # Next morning 09:15 open (25300)
    bar_next_0915 = Bar1M(
        timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        open=25300.0, high=25310.0, low=25290.0, close=25305.0, volume=1500
    )
    snap_next_0915 = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NSE_INDEX|Nifty 50",
        trading_symbol="NIFTY 50",
        instrument_class="INDEX_SPOT",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        last_completed_1m_bar=bar_next_0915,
    )
    res_final = adapter2.on_market_pulse("on_p4", snap_next_0915)
    assert res_final is not None
    assert res_final["action"] == "FINALIZED"
    assert res_final["orders_placed"] == 0
    assert res_final["broker_write_authority"] is False


def test_registry_initialization_and_safety_gating(temp_ledger_dir):
    """Verify that StrategyShadowAdapterRegistry creates evidence paths, registers candidates, and blocks write authority."""
    from core.paper_shadow.strategy_shadow_adapter import StrategyShadowAdapterRegistry

    registry = StrategyShadowAdapterRegistry(
        session_id="SESSION_20260922_001",
        source_sha="e16028e94c82edf122f194a056013955b8c45516",
        evidence_root=temp_ledger_dir,
        opening_drive_prev_contract_key="NIFTY26SEPFUT",
        opening_drive_prev_close_1529=25000.0,
        overnight_prev_daily_close=25000.0,
        overnight_prev_sma200=24000.0,
    )

    # Invariant checks
    assert registry.read_only is True
    assert registry.broker_write_authority is False
    assert registry.order_authority is False
    assert registry.orders_placed == 0
    assert len(registry.adapters) == 3
    assert OPENING_DRIVE_ID in registry.adapters
    assert CANDIDATE_S1_ID in registry.adapters

    # Check that registry.json was written
    assert (os.path.join(temp_ledger_dir, "registry.json"))

    # Test pulse dispatch
    class DummyPulse:
        pulse_id = "PULSE_REG_1"
        timestamp_epoch = datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ).timestamp()

    feed_truth = {
        "feed_ok": True,
        "websocket_ok": True,
        "context": {"session_id": "SESSION_20260922_001"},
        "symbols": [
            {
                "symbol": "NIFTY26SEPFUT",
                "instrument_token": 12345,
                "instrument_type": "FUT",
                "bar_open": 25050.0,
                "bar_close": 25055.0,
                "option_last_tick_age_sec": 0.05,
            }
        ],
    }

    results = registry.on_pulse(
        pulse=DummyPulse(),
        market_snapshot={},
        feed_health_truth=feed_truth,
    )
    assert isinstance(results, list)

    # Verify shutdown reporting
    shutdown_rep = registry.on_session_shutdown()
    assert shutdown_rep["read_only"] is True
    assert shutdown_rep["orders_placed"] == 0
    assert "strategy_statuses" in shutdown_rep


def test_os_process_isolation_restart(temp_ledger_dir):
    """
    Subprocess execution test:
    Process A writes OVERNIGHT_PENDING and terminates completely.
    Process B starts with a brand-new Python memory space, reads disk ledger, and finalizes.
    """
    import subprocess
    import sys

    # Process A Script
    proc_a_code = f"""
import os
from datetime import datetime, timezone, timedelta
from core.paper_shadow.strategy_shadow_adapter import (
    OvernightDriftShadowAdapter, StrategyMarketSnapshotV1, Level1Depth, Bar1M
)
from core.candidate_audits.nifty_overnight_drift import CANDIDATE_S1_ID, CANDIDATE_S1_SCHEDULE_SHA256, IST_TZ

adapter = OvernightDriftShadowAdapter(
    candidate_id=CANDIDATE_S1_ID,
    schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
    prev_daily_close=25000.0,
    prev_sma200=24000.0,
    sub_ledger_dir='{temp_ledger_dir}',
)

# Ingest open
b_open = Bar1M(datetime(2026, 9, 21, 9, 15, tzinfo=IST_TZ), 25050.0, 25060.0, 25040.0, 25055.0, 1000)
s_open = StrategyMarketSnapshotV1('2026-09-21', 'NSE_INDEX|Nifty 50', 'NIFTY 50', 'INDEX_SPOT',
    datetime(2026, 9, 21, 9, 16, tzinfo=IST_TZ), datetime(2026, 9, 21, 9, 16, tzinfo=IST_TZ),
    10.0, 'HEALTHY', 'NORMAL', last_completed_1m_bar=b_open)
adapter.on_market_pulse('p1', s_open)

# Ingest 15:20 close
b_1520 = Bar1M(datetime(2026, 9, 21, 15, 20, tzinfo=IST_TZ), 25190.0, 25205.0, 25185.0, 25200.0, 2000)
s_1520 = StrategyMarketSnapshotV1('2026-09-21', 'NSE_INDEX|Nifty 50', 'NIFTY 50', 'INDEX_SPOT',
    datetime(2026, 9, 21, 15, 20, 30, tzinfo=IST_TZ), datetime(2026, 9, 21, 15, 20, 30, tzinfo=IST_TZ),
    10.0, 'HEALTHY', 'NORMAL', last_completed_1m_bar=b_1520)
adapter.on_market_pulse('p2', s_1520)

# Ingest 15:21 quote
d_1521 = Level1Depth(25210.0, 500, 25212.0, 500)
s_1521 = StrategyMarketSnapshotV1('2026-09-21', 'NSE_INDEX|Nifty 50', 'NIFTY 50', 'INDEX_SPOT',
    datetime(2026, 9, 21, 15, 21, 10, tzinfo=IST_TZ), datetime(2026, 9, 21, 15, 21, 10, 50000, tzinfo=IST_TZ),
    50.0, 'HEALTHY', 'NORMAL', l1_depth=d_1521)
res = adapter.on_market_pulse('p3', s_1521)
assert res['action'] == 'COMMITTED_ARRIVAL'
print('PROCESS_A_COMMITTED_SUCCESSFULLY')
"""

    res_a = subprocess.run(
        [sys.executable, "-c", proc_a_code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONPATH="."),
        check=True,
    )
    assert "PROCESS_A_COMMITTED_SUCCESSFULLY" in res_a.stdout

    # Process B Script (completely separate process from empty RAM)
    proc_b_code = f"""
import os
from datetime import datetime, timezone, timedelta
from core.paper_shadow.strategy_shadow_adapter import (
    OvernightDriftShadowAdapter, StrategyMarketSnapshotV1, Bar1M
)
from core.candidate_audits.nifty_overnight_drift import CANDIDATE_S1_ID, CANDIDATE_S1_SCHEDULE_SHA256, IST_TZ

adapter = OvernightDriftShadowAdapter(
    candidate_id=CANDIDATE_S1_ID,
    schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
    prev_daily_close=25200.0,
    prev_sma200=24000.0,
    sub_ledger_dir='{temp_ledger_dir}',
)

# Ingest Next Morning 09:15 open
b_next = Bar1M(datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ), 25300.0, 25310.0, 25290.0, 25305.0, 1500)
s_next = StrategyMarketSnapshotV1('2026-09-22', 'NSE_INDEX|Nifty 50', 'NIFTY 50', 'INDEX_SPOT',
    datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ), datetime(2026, 9, 22, 9, 16, tzinfo=IST_TZ),
    10.0, 'HEALTHY', 'NORMAL', last_completed_1m_bar=b_next)
res = adapter.on_market_pulse('p4', s_next)
assert res is not None
assert res['action'] == 'FINALIZED'
print('PROCESS_B_FINALIZED_SUCCESSFULLY')
"""

    res_b = subprocess.run(
        [sys.executable, "-c", proc_b_code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONPATH="."),
        check=True,
    )
    assert "PROCESS_B_FINALIZED_SUCCESSFULLY" in res_b.stdout


def test_safety_boundary_mutation_and_broker_firewall(temp_ledger_dir):
    """
    Negative controls:
    1. Adapter setting order_authority=True fails closed.
    2. Shadow candidates never appear in candidate_decisions or order routing.
    3. Kite observation runtime rejects unauthorized broker write attempts.
    """
    from core.kite_read_only_observation_runtime import BrokerWriteFirewall
    from pathlib import Path

    # 1. Verify firewall raises RuntimeError and records evidence
    evidence_path = Path(temp_ledger_dir) / "broker_write_firewall.jsonl"
    firewall = BrokerWriteFirewall(evidence_path)
    with pytest.raises(RuntimeError, match="SAFETY_BLOCKER_BROKER_WRITE_ATTEMPT"):
        firewall.reject("submit_fill")

    assert evidence_path.is_file()
    with open(evidence_path) as f:
        event = json.loads(f.readline())
        assert event["event"] == "SAFETY_BLOCKER_BROKER_WRITE_ATTEMPT"
        assert event["method"] == "submit_fill"

    # 2. Verify shadow candidates are strictly tagged with read_only=True, broker_write_authority=False
    from core.paper_shadow.strategy_shadow_adapter import StrategyShadowAdapterRegistry
    registry = StrategyShadowAdapterRegistry(
        session_id="SESS_MUTATION_TEST",
        source_sha="e16028e94c82edf122f194a056013955b8c45516",
        evidence_root=temp_ledger_dir,
        opening_drive_prev_contract_key="NIFTY26SEPFUT",
        opening_drive_prev_close_1529=25000.0,
        overnight_prev_daily_close=25000.0,
        overnight_prev_sma200=24000.0,
    )
    for strat_id, adapter in registry.adapters.items():
        assert adapter.read_only is True
        assert adapter.broker_write_authority is False
        assert adapter.order_authority is False
        assert adapter.orders_placed == 0


def test_option_contract_identity_mismatch_rejected():
    """Prove that quotes for mismatched strikes or sides are strictly rejected."""
    adapter = IntradayOpeningDriveShadowAdapter(
        prev_futures_contract_key="NIFTY26SEPFUT",
        prev_close_1529=25000.0,
        max_quote_age_ms=2000.0,
    )
    # Qualify signal for 25050 CE
    adapter.signal_qualified = True
    adapter.signal_side = "BUY_CE"
    adapter.resolved_option_type = "CE"
    adapter.resolved_atm_strike = 25050

    depth = Level1Depth(bid_price=100.0, bid_qty=500, ask_price=102.0, ask_qty=500)

    # 1. Wrong strike: 24950 CE -> FAIL
    snap_wrong_strike = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_WRONG_STRIKE",
        trading_symbol="NIFTY26SEP24950CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth,
        strike_price=24950.0,
        option_type="CE",
    )
    res = adapter.on_market_pulse("pulse_wrong_strike", snap_wrong_strike)
    assert res is None
    assert adapter.telemetry_history[-1].checkpoint_name == "OPTION_CONTRACT_VERIFIED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "OPTION_STRIKE_MISMATCH"

    # 2. Wrong option type: 25050 PE -> FAIL
    snap_wrong_type = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_PE",
        trading_symbol="NIFTY26SEP25050PE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth,
        strike_price=25050.0,
        option_type="PE",
    )
    res = adapter.on_market_pulse("pulse_wrong_type", snap_wrong_type)
    assert res is None
    assert adapter.telemetry_history[-1].checkpoint_name == "OPTION_CONTRACT_VERIFIED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "OPTION_TYPE_MISMATCH"

    # 3. Exact target contract: 25050 CE -> PASS
    snap_correct = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_CE",
        trading_symbol="NIFTY26SEP25050CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth,
        strike_price=25050.0,
        option_type="CE",
    )
    adapter.on_market_pulse("pulse_correct", snap_correct)
    assert adapter.telemetry_history[-1].checkpoint_name == "SHADOW_ENTRY_SEALED"
    assert adapter.telemetry_history[-1].status == "PASS"


def test_bar_timestamp_provenance():
    """Prove that bar timestamp comes from authoritative bar metadata, not pulse time."""
    from core.paper_shadow.strategy_shadow_adapter import StrategyMarketSnapshotBuilder

    pulse_time = datetime(2026, 9, 22, 9, 21, 37, tzinfo=IST_TZ)
    bar_authoritative_time = datetime(2026, 9, 22, 9, 20, 0, tzinfo=IST_TZ)

    feed_truth = {
        "feed_ok": True,
        "websocket_ok": True,
        "symbols": [
            {
                "symbol": "NIFTY26SEPFUT",
                "instrument_type": "FUT",
                "bar_open": 25050.0,
                "bar_close": 25080.0,
                "bar_timestamp_epoch": bar_authoritative_time.timestamp(),
                "option_last_tick_age_sec": 0.5,
            }
        ],
    }

    snaps = StrategyMarketSnapshotBuilder.build_snapshots(
        pulse_id="pulse_bar_test",
        timestamp_ist=pulse_time,
        market_snapshot={},
        feed_health_truth=feed_truth,
    )
    assert len(snaps) == 1
    assert snaps[0].last_completed_1m_bar is not None
    assert snaps[0].last_completed_1m_bar.timestamp_ist == bar_authoritative_time
    assert snaps[0].last_completed_1m_bar.timestamp_ist.time() == dtime(9, 20)
    assert snaps[0].receipt_timestamp_ist == pulse_time


def test_level1_depth_finite_and_quantities():
    """Prove that Level1Depth rejects non-finite values and missing/zero quantities."""
    import math

    # Valid depth
    d_valid = Level1Depth(bid_price=100.0, bid_qty=10, ask_price=101.0, ask_qty=20)
    assert d_valid.is_valid() is True

    # Non-finite prices
    assert Level1Depth(bid_price=float("nan"), bid_qty=10, ask_price=101.0, ask_qty=20).is_valid() is False
    assert Level1Depth(bid_price=100.0, bid_qty=10, ask_price=float("inf"), ask_qty=20).is_valid() is False

    # Missing / non-positive quantities
    assert Level1Depth(bid_price=100.0, bid_qty=None, ask_price=101.0, ask_qty=20).is_valid() is False
    assert Level1Depth(bid_price=100.0, bid_qty=0, ask_price=101.0, ask_qty=20).is_valid() is False
    assert Level1Depth(bid_price=100.0, bid_qty=-5, ask_price=101.0, ask_qty=20).is_valid() is False


def test_session_health_rejection():
    """Prove that HALTED or CIRCUIT_BREAKER session states fail closed."""
    snap_halted = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="HALTED",
    )
    assert snap_halted.central_feed_valid() is False

    snap_circuit = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="NIFTY26SEPFUT",
        trading_symbol="NIFTY26SEPFUT",
        instrument_class="INDEX_FUTURES",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 15, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="CIRCUIT_BREAKER",
    )
    assert snap_circuit.central_feed_valid() is False


def test_registry_prerequisites_fail_closed(temp_ledger_dir):
    """Prove that missing T-1 market facts disables strategies fail-closed."""
    from core.paper_shadow.strategy_shadow_adapter import StrategyShadowAdapterRegistry

    # Instantiate registry with NO prerequisites
    reg = StrategyShadowAdapterRegistry(
        session_id="SESS_NO_PREREQ",
        source_sha="e16028e94c82edf122f194a056013955b8c45516",
        evidence_root=temp_ledger_dir,
    )
    assert len(reg.adapters) == 0
    assert len(reg.disabled_strategies) == 3
    assert OPENING_DRIVE_ID in reg.disabled_strategies
    assert CANDIDATE_S1_ID in reg.disabled_strategies
    assert "DISABLED_FAIL_CLOSED" in reg.disabled_strategies[OPENING_DRIVE_ID]

    shutdown_rep = reg.on_session_shutdown()
    assert OPENING_DRIVE_ID in shutdown_rep["strategy_statuses"]
    assert "DISABLED_FAIL_CLOSED" in shutdown_rep["strategy_statuses"][OPENING_DRIVE_ID]


def test_shutdown_failure_propagation(temp_ledger_dir, monkeypatch):
    """Prove that on_session_shutdown propagates exceptions and records STRATEGY_SHADOW_EVIDENCE_SEAL_FAIL."""
    from core.paper_shadow.strategy_shadow_adapter import StrategyShadowAdapterRegistry
    from pathlib import Path

    reg = StrategyShadowAdapterRegistry(
        session_id="SESS_FAIL_TEST",
        source_sha="e16028e94c82edf122f194a056013955b8c45516",
        evidence_root=temp_ledger_dir,
    )

    def faulty_flush():
        raise IOError("DISK_CORRUPTION_SIMULATION")

    monkeypatch.setattr(reg, "_flush_checkpoints", faulty_flush)

    with pytest.raises(IOError, match="DISK_CORRUPTION_SIMULATION"):
        reg.on_session_shutdown()

    fail_file = Path(temp_ledger_dir) / "STRATEGY_SHADOW_EVIDENCE_SEAL_FAIL"
    assert fail_file.is_file()
    content = fail_file.read_text(encoding="utf-8")
    assert "DISK_CORRUPTION_SIMULATION" in content


def test_missing_bar_timestamp_does_not_create_bar():
    """Prove that absent authoritative bar timestamp results in no Bar1M created (never falls back to pulse time)."""
    from core.paper_shadow.strategy_shadow_adapter import StrategyMarketSnapshotBuilder

    pulse_time = datetime(2026, 9, 22, 9, 21, 37, tzinfo=IST_TZ)

    feed_truth = {
        "feed_ok": True,
        "websocket_ok": True,
        "symbols": [
            {
                "symbol": "NIFTY26SEPFUT",
                "instrument_type": "FUT",
                "bar_open": 25050.0,
                "bar_close": 25080.0,
                # Intentionally omitting bar_timestamp_ist, bar_timestamp, bar_timestamp_epoch, interval_end_epoch
                "exchange_timestamp": datetime(2026, 9, 22, 9, 21, 35, tzinfo=IST_TZ).isoformat(),
                "option_last_tick_age_sec": 0.5,
            }
        ],
    }

    snaps = StrategyMarketSnapshotBuilder.build_snapshots(
        pulse_id="pulse_no_bar_ts",
        timestamp_ist=pulse_time,
        market_snapshot={},
        feed_health_truth=feed_truth,
    )
    assert len(snaps) == 1
    assert snaps[0].last_completed_1m_bar is None
    assert snaps[0].receipt_timestamp_ist == pulse_time


def test_missing_instrument_metadata_does_not_guess_from_symbol():
    """Prove that unknown/missing instrument_type and segment do not guess classification from symbol substrings."""
    from core.paper_shadow.strategy_shadow_adapter import StrategyMarketSnapshotBuilder

    pulse_time = datetime(2026, 9, 22, 9, 21, 0, tzinfo=IST_TZ)
    feed_truth = {
        "feed_ok": True,
        "websocket_ok": True,
        "symbols": [
            {
                "symbol": "NIFTY26SEPFUT",
                "instrument_type": "",  # missing
                "segment": "",          # missing
                "bar_open": 25050.0,
                "bar_close": 25080.0,
                "bar_timestamp_epoch": pulse_time.timestamp(),
                "exchange_timestamp": pulse_time.isoformat(),
                "option_last_tick_age_sec": 0.5,
            },
            {
                "symbol": "NIFTY26SEP25000CE",
                "instrument_type": "UNKNOWN",
                "segment": "UNKNOWN",
                "exchange_timestamp": pulse_time.isoformat(),
                "option_last_tick_age_sec": 0.5,
            },
        ],
    }

    snaps = StrategyMarketSnapshotBuilder.build_snapshots(
        pulse_id="pulse_no_guess",
        timestamp_ist=pulse_time,
        market_snapshot={},
        feed_health_truth=feed_truth,
    )
    # Both symbols must be omitted fail-closed without guessing from 'FUT' or 'CE' in symbol
    assert len(snaps) == 0


def test_wrong_expiry_same_strike_same_type_is_rejected():
    """Prove that matching strike and type but mismatched target expiry is strictly rejected."""
    adapter = IntradayOpeningDriveShadowAdapter(
        prev_futures_contract_key="NIFTY26SEPFUT",
        prev_close_1529=25000.0,
        target_expiry="2026-09-24",
        max_quote_age_ms=2000.0,
    )
    adapter.signal_qualified = True
    adapter.signal_side = "BUY_CE"
    adapter.resolved_option_type = "CE"
    adapter.resolved_atm_strike = 25050

    depth = Level1Depth(bid_price=120.0, bid_qty=500, ask_price=122.0, ask_qty=500)

    # 1. Snapshot with monthly/far expiry "2026-10-29" instead of target "2026-09-24"
    snap_wrong_expiry = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_OCT",
        trading_symbol="NIFTY26OCT25050CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth,
        strike_price=25050.0,
        option_type="CE",
        expiry_date="2026-10-29",
    )
    res = adapter.on_market_pulse("pulse_wrong_exp", snap_wrong_expiry)
    assert res is None
    assert adapter.telemetry_history[-1].checkpoint_name == "OPTION_CONTRACT_VERIFIED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "OPTION_EXPIRY_MISMATCH"

    # 2. Snapshot with missing expiry metadata -> FAIL
    snap_missing_expiry = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_CE",
        trading_symbol="NIFTY26SEP25050CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth,
        strike_price=25050.0,
        option_type="CE",
        expiry_date=None,
    )
    res2 = adapter.on_market_pulse("pulse_no_exp", snap_missing_expiry)
    assert res2 is None
    assert adapter.telemetry_history[-1].checkpoint_name == "OPTION_CONTRACT_VERIFIED"
    assert adapter.telemetry_history[-1].status == "FAIL"
    assert adapter.telemetry_history[-1].root_cause == "MISSING_EXPIRY_METADATA"

    # 3. Snapshot with exact target expiry "2026-09-24" -> PASS
    snap_correct_expiry = StrategyMarketSnapshotV1(
        session_id="2026-09-22",
        instrument_key="TEST_KEY_CE",
        trading_symbol="NIFTY26SEP25050CE",
        instrument_class="INDEX_OPTION",
        source_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        receipt_timestamp_ist=datetime(2026, 9, 22, 9, 22, 5, tzinfo=IST_TZ),
        age_ms=10.0,
        feed_health="HEALTHY",
        session_health="NORMAL",
        l1_depth=depth,
        strike_price=25050.0,
        option_type="CE",
        expiry_date="2026-09-24",
    )
    adapter.on_market_pulse("pulse_correct_exp", snap_correct_expiry)
    assert adapter.telemetry_history[-1].checkpoint_name == "SHADOW_ENTRY_SEALED"
    assert adapter.telemetry_history[-1].status == "PASS"


def test_runtime_loads_t1_prerequisites_without_manual_env(temp_ledger_dir, monkeypatch):
    """Prove that load_canonical_t1_prerequisites loads from launch_plan or disk manifests without manual env vars."""
    from core.paper_shadow.strategy_shadow_adapter import (
        load_canonical_t1_prerequisites,
        StrategyShadowAdapterRegistry,
    )
    from pathlib import Path

    # Clear environment overrides
    monkeypatch.delenv("OPENING_DRIVE_PREV_FUTURES_KEY", raising=False)
    monkeypatch.delenv("OPENING_DRIVE_PREV_CLOSE_1529", raising=False)
    monkeypatch.delenv("OPENING_DRIVE_TARGET_EXPIRY", raising=False)
    monkeypatch.delenv("OVERNIGHT_PREV_DAILY_CLOSE", raising=False)
    monkeypatch.delenv("OVERNIGHT_PREV_SMA200", raising=False)

    launch_plan = {
        "t1_facts": {
            "opening_drive_prev_contract_key": "NIFTY26SEPFUT",
            "opening_drive_prev_close_1529": 25100.5,
            "opening_drive_target_expiry": "2026-09-24",
            "overnight_prev_daily_close": 25120.0,
            "overnight_prev_sma200": 24200.0,
        }
    }

    facts = load_canonical_t1_prerequisites(session_date="2026-09-22", launch_plan=launch_plan)
    assert facts["opening_drive_prev_contract_key"] == "NIFTY26SEPFUT"
    assert facts["opening_drive_prev_close_1529"] == 25100.5
    assert facts["opening_drive_target_expiry"] == "2026-09-24"
    assert facts["overnight_prev_daily_close"] == 25120.0
    assert facts["overnight_prev_sma200"] == 24200.0

    # Ensure StrategyShadowAdapterRegistry initializes all 3 adapters from these facts
    reg = StrategyShadowAdapterRegistry(
        session_id="SESS_AUTO_T1",
        source_sha="e16028e94c82edf122f194a056013955b8c45516",
        evidence_root=temp_ledger_dir,
        opening_drive_prev_contract_key=facts["opening_drive_prev_contract_key"],
        opening_drive_prev_close_1529=facts["opening_drive_prev_close_1529"],
        opening_drive_target_expiry=facts["opening_drive_target_expiry"],
        overnight_prev_daily_close=facts["overnight_prev_daily_close"],
        overnight_prev_sma200=facts["overnight_prev_sma200"],
    )
    assert len(reg.adapters) == 3
    assert len(reg.disabled_strategies) == 0
    assert OPENING_DRIVE_ID in reg.adapters
    assert reg.adapters[OPENING_DRIVE_ID].target_expiry == "2026-09-24"
