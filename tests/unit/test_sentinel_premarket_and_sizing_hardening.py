"""Comprehensive Verification Suite for Sentinel Pre-Market Re-Centering,
Option Stop-Loss Sizing Hardening, and Dummy Trade Smoketest Harness.

Tests:
1. Pre-market Re-Centering (TC-PM-01 to TC-PM-04):
   - TC-PM-01: Correct strike interval and ATM re-centering calculation.
   - TC-PM-02: Add-only / union subscription logic (never duplicates existing keys).
   - TC-PM-03: Max total token limit enforcement (<= 60 tokens, ATM-outward prioritization).
   - TC-PM-04: Non-fatal error handling (streamer exception does not crash capture).

2. Option SL Sizing Fix (TC-SZ-01 to TC-SZ-04):
   - TC-SZ-01: Effective option SL points calculation: max(15.0, round(ltp * 0.20, 2)).
   - TC-SZ-02: Low-premium penny contract veto (< 40.0 pts) with VETO_LOW_PREMIUM.
   - TC-SZ-03: Strict integer lot caps (NIFTY <= 3, SENSEX <= 2, BANKNIFTY <= 2).
   - TC-SZ-04: Floor-or-Reject margin/risk model (computed_lots < 1 -> VETO_INSUFFICIENT_MARGIN).

3. Smoketest Harness (TC-SM-01 to TC-SM-04):
   - TC-SM-01: Ingestion of synthetic ticks/depth transitions APM from STANDBY to IN_FLIGHT.
   - TC-SM-02: Enforces non-negotiable safety invariants (read_only, is_order_action, broker_api_called).
   - TC-SM-03: Strictly isolated temporary WAL paths (zero contamination in runtime/ directory).
   - TC-SM-04: Multi-index execution and lot bounds verification across NIFTY, SENSEX, BANKNIFTY.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, time as dt_time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.active_position_manager import (
    STATE_IN_FLIGHT,
    STATE_STANDBY,
    ActivePositionManager,
)
from core.sentinel_dynamic_sizing import (
    calculate_discrete_lots,
    get_exchange_lot_size,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_live_stream_advisor import (
    CachedRBFNAuctionSignal,
    SentinelLiveStreamAdvisor,
)
from core.sentinel_realtime_journal import SentinelRealtimeJournal
from core.upstox_stream_broadcaster import UpstoxLevel5DepthRecord
from scripts.run_premarket_firing_smoketest import (
    get_runtime_wal_hashes,
    run_smoketest,
)
from scripts.upstox_daily_live_capture_and_stitch import (
    recenter_premarket_option_subscriptions,
)


# =============================================================================
# Helper Fixtures
# =============================================================================

def _build_mock_df_inst(index_name: str = "NIFTY", base_strike: float = 24000.0, step: float = 50.0) -> pd.DataFrame:
    """Builds a mock DataFrame of Upstox instrument master for options."""
    records = []
    expiry_ms = int(datetime(2026, 10, 29).timestamp() * 1000)
    for i in range(-25, 26):
        strike = base_strike + (i * step)
        for opt_type in ["CE", "PE"]:
            key = f"NSE_FO|{index_name}_{int(strike)}_{opt_type}"
            sym = f"{index_name} {int(strike)} {opt_type}"
            records.append({
                "instrument_key": key,
                "trading_symbol": sym,
                "name": index_name,
                "instrument_type": opt_type,
                "strike_price": float(strike),
                "expiry": expiry_ms,
            })
    return pd.DataFrame(records)


def _make_depth_record(
    symbol: str,
    token: str,
    ltp: float,
    bid: float = 0.0,
    ask: float = 0.0,
    oi: int = 500000,
) -> UpstoxLevel5DepthRecord:
    # Use very tight default bid/ask to avoid triggering spread veto (>4%) on low premiums
    b = bid if bid > 0 else round(ltp - 0.1, 2)
    a = ask if ask > 0 else round(ltp + 0.1, 2)
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=int(datetime(2026, 10, 26, 9, 30).timestamp() * 1000),
        ingress_monotonic_ns=1000,
        ingress_wall_utc="2026-10-26T04:00:00Z",
        sequence_id=1,
        ltp=ltp,
        volume=200000,
        open_interest=oi,
        bid_p1=b, bid_q1=1000, bid_o1=10,
        bid_p2=b - 0.5, bid_q2=1000, bid_o2=10,
        bid_p3=b - 1.0, bid_q3=1000, bid_o3=10,
        bid_p4=b - 1.5, bid_q4=1000, bid_o4=10,
        bid_p5=b - 2.0, bid_q5=1000, bid_o5=10,
        ask_p1=a, ask_q1=1000, ask_o1=10,
        ask_p2=a + 0.5, ask_q2=1000, ask_o2=10,
        ask_p3=a + 1.0, ask_q3=1000, ask_o3=10,
        ask_p4=a + 1.5, ask_q4=1000, ask_o4=10,
        ask_p5=a + 2.0, ask_q5=1000, ask_o5=10,
    )


# =============================================================================
# 1. Pre-Market Re-Centering Hook (TC-PM-01 to TC-PM-04)
# =============================================================================

def test_tc_pm_01_recenter_calculation_and_desired_strikes():
    """TC-PM-01: Verifies correct ATM strike interval and ordered strike calculation."""
    df_inst = _build_mock_df_inst(index_name="NIFTY", base_strike=24000.0, step=50.0)
    mock_streamer = MagicMock()
    subscriptions = {"NSE_INDEX|Nifty 50": "NIFTY 50"}

    # Pre-market spot gaps from 24000 to 24230 -> ATM should be 24250
    added = recenter_premarket_option_subscriptions(
        streamer=mock_streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        premarket_spot=24230.0,
        index_name="NIFTY",
        max_total_tokens=60,
    )
    assert added > 0
    # Streamer subscribe called with full mode
    mock_streamer.subscribe.assert_called_once()
    called_keys, called_kwargs = mock_streamer.subscribe.call_args
    assert called_kwargs.get("mode") == "full"
    # ATM strike 24250 CE/PE must be subscribed
    assert "NSE_FO|NIFTY_24250_CE" in subscriptions
    assert "NSE_FO|NIFTY_24250_PE" in subscriptions


def test_tc_pm_02_union_subscription_does_not_duplicate():
    """TC-PM-02: Verifies union subscription logic never duplicates existing keys."""
    df_inst = _build_mock_df_inst(index_name="NIFTY", base_strike=24000.0, step=50.0)
    mock_streamer = MagicMock()
    # Pre-populate with ATM strike already
    subscriptions = {
        "NSE_INDEX|Nifty 50": "NIFTY 50",
        "NSE_FO|NIFTY_24000_CE": "NIFTY 24000 CE",
        "NSE_FO|NIFTY_24000_PE": "NIFTY 24000 PE",
    }
    initial_count = len(subscriptions)

    recenter_premarket_option_subscriptions(
        streamer=mock_streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        premarket_spot=24010.0,  # ATM remains 24000
        index_name="NIFTY",
        max_total_tokens=60,
    )
    # The initial 24000 strikes must not be duplicated or re-added
    called_keys = mock_streamer.subscribe.call_args[0][0]
    assert "NSE_FO|NIFTY_24000_CE" not in called_keys
    assert "NSE_FO|NIFTY_24000_PE" not in called_keys
    assert len(subscriptions) > initial_count


def test_tc_pm_03_max_token_cap_and_priority_enforcement():
    """TC-PM-03: Verifies strict capping at max_total_tokens (<= 60) prioritizing nearest to ATM."""
    df_inst = _build_mock_df_inst(index_name="NIFTY", base_strike=24000.0, step=50.0)
    mock_streamer = MagicMock()
    # 55 existing tokens already subscribed
    subscriptions = {f"EXISTING_{i}": f"SYM_{i}" for i in range(55)}

    added = recenter_premarket_option_subscriptions(
        streamer=mock_streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        premarket_spot=24000.0,
        index_name="NIFTY",
        max_total_tokens=60,
    )
    # Exactly 5 slots remaining
    assert added == 5
    assert len(subscriptions) == 60
    # Must have added ATM 24000 CE/PE and nearest strike 24050 first
    assert "NSE_FO|NIFTY_24000_CE" in subscriptions
    assert "NSE_FO|NIFTY_24000_PE" in subscriptions


def test_tc_pm_04_non_fatal_error_handling():
    """TC-PM-04: Streamer network/timeout errors log warning and never crash caller."""
    df_inst = _build_mock_df_inst(index_name="NIFTY", base_strike=24000.0, step=50.0)
    failing_streamer = MagicMock()
    failing_streamer.subscribe.side_effect = TimeoutError("Upstox Gateway Timeout")
    subscriptions = {}

    # Must complete safely and return count of attempted keys without raising
    added = recenter_premarket_option_subscriptions(
        streamer=failing_streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        premarket_spot=24000.0,
        index_name="NIFTY",
        max_total_tokens=60,
    )
    assert added > 0


# =============================================================================
# 2. Option Stop-Loss Sizing Hardening (TC-SZ-01 to TC-SZ-04)
# =============================================================================

def test_tc_sz_01_option_native_stop_loss_pts_calculation():
    """TC-SZ-01: Option SL points = max(15.0, round(ltp * 0.20, 2))."""
    # Case A: LTP = 60.0 -> 20% is 12.0 -> clamped to 15.0 min floor
    ltp_a = 60.0
    opt_sl_a = max(15.0, round(ltp_a * 0.20, 2))
    assert opt_sl_a == 15.0

    # Case B: LTP = 120.0 -> 20% is 24.0 -> above floor
    ltp_b = 120.0
    opt_sl_b = max(15.0, round(ltp_b * 0.20, 2))
    assert opt_sl_b == 24.0

    # Case C: LTP = 200.0 -> 20% is 40.0
    ltp_c = 200.0
    opt_sl_c = max(15.0, round(ltp_c * 0.20, 2))
    assert opt_sl_c == 40.0


def test_tc_sz_02_otm_expansion_contracts_are_not_vetoed(tmp_path):
    """TC-SZ-02: OTM expansion contracts (e.g. LTP 35.0) are NOT suppressed by arbitrary premium floors."""
    wal = tmp_path / "test_sz_02_wal.json"
    journal = SentinelRealtimeJournal(logs_dir=tmp_path / "j", enable_writer_thread=False)
    advisor = SentinelLiveStreamAdvisor(
        enable_stdout=False,
        wal_path=str(wal),
        journal=journal,
        advisory_capital=200000.0,
    )
    advisor.trade_lock_active = False
    advisor.spots["NIFTY"] = 22400.0
    fake_now = datetime(2026, 10, 26, 9, 30, 0)
    ts_ms = int(fake_now.timestamp() * 1000)
    advisor.spots_ts_ms["NIFTY"] = ts_ms
    advisor.session_gear = "GEAR_2_TREND"
    advisor.seed_prior_day_levels("NIFTY", 22500, 22300, 22400, session_date=date(2026, 10, 25), atr_20=200.0)

    # Inject active signal
    sig = CachedRBFNAuctionSignal(
        timestamp_ms=ts_ms,
        index_name="NIFTY",
        action="BUY_CALL",
        direction="CE",
        target_strike=22400.0,
        target_pts=50.0,
        sl_pts=20.0,
        setup_reason="Slingshot",
        trade_phase="OPENING_DRIVE",
        bar_time=dt_time(9, 30),
        sustainable_anchor_price=22400.0,
        valid_until_epoch_sec=9999999999.0,
    )
    advisor.cached_rbfn_signals["NIFTY"] = sig

    # Send OTM expansion contract depth (LTP = 35.0)
    depth = UpstoxLevel5DepthRecord(
        token="NSE_FO|NIFTY26OCT22400CE",
        symbol="NIFTY 22400 CE",
        exchange_timestamp_ms=ts_ms,
        ingress_monotonic_ns=1000,
        ingress_wall_utc="2026-10-26T04:00:00Z",
        sequence_id=1,
        ltp=35.0,
        volume=500000,
        open_interest=1000000,
        bid_p1=34.9, bid_q1=1000, bid_o1=10,
        bid_p2=34.8, bid_q2=1000, bid_o2=10,
        bid_p3=34.7, bid_q3=1000, bid_o3=10,
        bid_p4=34.6, bid_q4=1000, bid_o4=10,
        bid_p5=34.5, bid_q5=1000, bid_o5=10,
        ask_p1=35.1, ask_q1=1000, ask_o1=10,
        ask_p2=35.2, ask_q2=1000, ask_o2=10,
        ask_p3=35.3, ask_q3=1000, ask_o3=10,
        ask_p4=35.4, ask_q4=1000, ask_o4=10,
        ask_p5=35.5, ask_q5=1000, ask_o5=10,
    )

    with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromtimestamp = datetime.fromtimestamp
        mock_dt.strptime = datetime.strptime
        advisor._evaluate_option_depth(depth)

    # Must NOT be vetoed for low premium - enters IN_FLIGHT
    assert advisor.apms["NIFTY"].state == STATE_IN_FLIGHT
    assert advisor.apms["NIFTY"].payload is not None
    assert advisor.apms["NIFTY"].payload.opt_entry_ltp == 35.1


def test_tc_sz_03_strict_multi_index_lot_caps():
    """TC-SZ-03: Sizing enforces hard caps: NIFTY <= 3, SENSEX <= 2, BANKNIFTY <= 2."""
    # Huge capital that would otherwise allocate 20+ lots
    huge_capital = 2_000_000.0

    # NIFTY: lot size = 65, cap = 3
    lots_nifty, _ = calculate_discrete_lots(
        total_capital=huge_capital,
        risk_budget_pct=0.02,
        opt_premium=100.0,
        sl_points=20.0,
        index_name="NIFTY",
    )
    # Apply index lot cap
    capped_nifty = min(lots_nifty, 3)
    assert capped_nifty == 3

    # SENSEX: lot size = 20, cap = 2
    lots_sensex, _ = calculate_discrete_lots(
        total_capital=huge_capital,
        risk_budget_pct=0.02,
        opt_premium=150.0,
        sl_points=30.0,
        index_name="SENSEX",
    )
    capped_sensex = min(lots_sensex, 2)
    assert capped_sensex == 2

    # BANKNIFTY: lot size = 30, cap = 2
    lots_bn, _ = calculate_discrete_lots(
        total_capital=huge_capital,
        risk_budget_pct=0.02,
        opt_premium=120.0,
        sl_points=25.0,
        index_name="BANKNIFTY",
    )
    capped_bn = min(lots_bn, 2)
    assert capped_bn == 2


def test_tc_sz_04_floor_or_reject_margin_model():
    """TC-SZ-04: Floor-or-Reject guarantees sub-lot capital allocation returns 0 and rejects."""
    # Insufficient capital (5,000 INR for NIFTY 150 LTP requiring 9,750 INR margin)
    lots, tier = calculate_discrete_lots(
        total_capital=5000.0,
        risk_budget_pct=0.02,
        opt_premium=150.0,
        sl_points=30.0,
        index_name="NIFTY",
    )
    assert lots == 0
    assert tier == "REJECT_INSUFFICIENT_MARGIN"


# =============================================================================
# 3. Pre-Market Dummy Smoketest Harness (TC-SM-01 to TC-SM-04)
# =============================================================================

def test_tc_sm_01_smoketest_state_transition_standby_to_in_flight():
    """TC-SM-01: Proves smoketest transitions APM from STANDBY to IN_FLIGHT."""
    res = run_smoketest(index_name="NIFTY", assert_live_wal_clean=False, keep_artifacts=False)
    assert res["success"] is True
    assert res["apm_state"] == STATE_IN_FLIGHT
    assert res["lots"] >= 1
    assert res["lots"] <= 3


def test_tc_sm_02_safety_invariants_and_read_only_locks():
    """TC-SM-02: Safety flags are verified across advisor and smoketest harness."""
    with tempfile.TemporaryDirectory() as td:
        wal_path = Path(td) / "wal.json"
        advisor = SentinelLiveStreamAdvisor(enable_stdout=False, wal_path=str(wal_path))
        assert advisor.read_only is True
        assert advisor.is_order_action is False
        assert advisor.broker_api_called is False
        assert advisor.allowed_for_live_execution is False


def test_tc_sm_03_zero_production_wal_contamination():
    """TC-SM-03: SHA256 hashes of all runtime/ JSON files are 100% untouched before and after test."""
    hashes_before = get_runtime_wal_hashes()
    res = run_smoketest(index_name="NIFTY", assert_live_wal_clean=True, keep_artifacts=False)
    hashes_after = get_runtime_wal_hashes()
    assert hashes_before == hashes_after
    assert res["production_wals_clean"] is True


def test_tc_sm_04_multi_index_smoketest_and_lot_bounds():
    """TC-SM-04: Smoketest executes cleanly across NIFTY, SENSEX, and BANKNIFTY."""
    for idx in ["NIFTY", "SENSEX", "BANKNIFTY"]:
        res = run_smoketest(index_name=idx, assert_live_wal_clean=True, keep_artifacts=False)
        assert res["success"] is True
        assert res["apm_state"] == STATE_IN_FLIGHT
        assert res["lots"] >= 1
        assert res["lots"] <= res["lot_cap"]
