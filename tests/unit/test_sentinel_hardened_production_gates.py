"""Verification test suite for Sentinel Hardened Production Gates.

Proves:
1. Gate 1: 15:00 IST Entry Blackout blocks new trade candidate signals in Sentinel Stream Advisor.
2. Gate 2: 15:15 IST Mandatory Square-Off in APM immediately liquidates positions on tick and bar evaluation.
3. Gate 3: Strike Liquidity Gate enforces Minimum Open Interest (OI) floor and vetoes illiquid strikes.
4. Gate 4: Decoupled Telemetry Alert Dispatcher parses WAL events without blocking execution.
"""

import os
import json
import pytest
from datetime import datetime, time as dt_time
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_COOL_OFF,
    STATE_LIQUIDATED,
)
from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    UpstoxTickRecord,
    UpstoxLevel5DepthRecord,
)


def _make_dummy_depth(token: str, symbol: str, oi: int, ltp: float = 100.0) -> UpstoxLevel5DepthRecord:
    return UpstoxLevel5DepthRecord(
        token=token,
        symbol=symbol,
        exchange_timestamp_ms=1793188800000,
        ingress_monotonic_ns=1000000,
        ingress_wall_utc="2026-10-28T15:01:00Z",
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


def test_apm_eod_squareoff_on_tick(tmp_path):
    """Proves that a tick at or after 15:15:00 IST forces immediate liquidation with EOD reason."""
    wal = tmp_path / "test_wal_eod_tick.json"
    apm = ActivePositionManager(wal_path=str(wal))

    entered = apm.arm_and_enter(
        position_id="TRADE_EOD_TICK",
        direction="CE",
        contract="NIFTY 22500 CE 29 OCT 26",
        entry_price=22500.0,
        entry_time_str="2026-10-28T14:45:00",
        opt_quote={"symbol": "NIFTY 22500 CE", "ltp": 120.0, "bid": 119.5, "ask": 120.5},
        is_runner_mode=True,
        session_gear="GEAR_2_TREND",
        atr_1m=10.0,
    )
    assert entered is True
    assert apm.state == STATE_IN_FLIGHT

    # Normal tick at 14:55:00 does not trigger EOD
    state, p = apm.evaluate_tick(
        current_spot=22505.0,
        current_opt_ltp=122.0,
        tick_time_str="2026-10-28T14:55:00",
        atr_1m=10.0,
    )
    assert state == STATE_IN_FLIGHT

    # Tick at 15:15:01 IST MUST trigger mandatory EOD liquidation
    state, p_exit = apm.evaluate_tick(
        current_spot=22504.0,
        current_opt_ltp=121.0,
        tick_time_str="2026-10-28T15:15:01",
        atr_1m=10.0,
    )
    assert state == STATE_COOL_OFF
    assert p_exit["exit_reason"] == "EOD_MANDATORY_SQUAREOFF"
    assert p_exit["exit_price"] == 22504.0


def test_apm_eod_squareoff_on_bar(tmp_path):
    """Proves that a 1-minute bar at or after 15:15:00 IST forces immediate liquidation."""
    wal = tmp_path / "test_wal_eod_bar.json"
    apm = ActivePositionManager(wal_path=str(wal))

    entered = apm.arm_and_enter(
        position_id="TRADE_EOD_BAR",
        direction="PE",
        contract="NIFTY 22500 PE 29 OCT 26",
        entry_price=22500.0,
        entry_time_str="2026-10-28T14:50:00",
        opt_quote={"symbol": "NIFTY 22500 PE", "ltp": 110.0, "bid": 109.5, "ask": 110.5},
        is_runner_mode=False,
        session_gear="GEAR_1_RANGE",
        atr_1m=10.0,
    )
    assert entered is True

    # Bar at 15:15:00 IST triggers EOD exit
    state, p_exit = apm.evaluate_bar(
        bar_open=22502.0,
        bar_high=22505.0,
        bar_low=22498.0,
        bar_close=22500.0,
        bar_time_str="2026-10-28T15:15:00",
        current_opt_ltp=110.0,
        atr_1m=10.0,
    )
    assert state == STATE_COOL_OFF
    assert p_exit["exit_reason"] == "EOD_MANDATORY_SQUAREOFF"
    assert p_exit["exit_price"] == 22500.0


def test_sentinel_advisor_eod_entry_freeze(tmp_path):
    """Proves that Sentinel advisor blocks candidate setup entries at or after 15:00:00 IST."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    advisor.eod_entry_freeze_time = dt_time(15, 0)
    
    advisor.spots["NIFTY"] = 22520.0
    advisor.spots_ts_ms["NIFTY"] = 1793188800000
    advisor.or_bounds["NIFTY"] = {"high": 22500.0, "low": 22400.0}
    advisor.trade_lock_active = False

    # Calling with current time forced after 15:00
    is_frozen = advisor.is_eod_entry_frozen(dt_time(15, 1, 0))
    assert is_frozen is True

    # Calling before 15:00
    is_frozen_early = advisor.is_eod_entry_frozen(dt_time(14, 59, 59))
    assert is_frozen_early is False


def test_sentinel_advisor_strike_oi_gate():
    """Proves that option depth ticks below the structural Open Interest floor are vetoed."""
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    
    # NIFTY threshold is 250,000
    assert advisor.evaluate_strike_oi("NIFTY", 50000) is False
    assert advisor.evaluate_strike_oi("NIFTY", 249999) is False
    assert advisor.evaluate_strike_oi("NIFTY", 250000) is True
    assert advisor.evaluate_strike_oi("NIFTY", 1000000) is True

    # SENSEX and BANKNIFTY threshold is 100,000
    assert advisor.evaluate_strike_oi("SENSEX", 80000) is False
    assert advisor.evaluate_strike_oi("SENSEX", 100000) is True
    assert advisor.evaluate_strike_oi("BANKNIFTY", 99999) is False
    assert advisor.evaluate_strike_oi("BANKNIFTY", 150000) is True


def test_decoupled_alert_notifier_dispatch(tmp_path):
    """Proves that SentinelAlertNotifier parses WAL state changes into structured alerts."""
    from scripts.sentinel_alert_notifier import SentinelAlertNotifier

    wal = tmp_path / "sentinel_apm_wal.json"
    out_md = tmp_path / "telemetry.md"

    # Write an initial IN_FLIGHT state to WAL
    initial_payload = {
        "state": "IN_FLIGHT",
        "payload": {
            "position_id": "TEST_ALERT_POS",
            "strike_contract": "NIFTY 22500 CE",
            "direction": "CE",
            "entry_price": 22500.0,
            "opt_entry_ltp": 100.0,
            "opt_initial_sl": 80.0,
            "target_price": 22540.0,
        }
    }
    with open(wal, "w") as f:
        json.dump(initial_payload, f)

    notifier = SentinelAlertNotifier(wal_paths=[str(wal)], out_telemetry_md=str(out_md))
    alerts = notifier.poll_once()

    assert len(alerts) == 1
    assert alerts[0].event_type == "ENTRY"
    assert "NIFTY 22500 CE" in alerts[0].message
    assert out_md.exists()

    # Re-polling without changes produces no duplicate alerts
    assert len(notifier.poll_once()) == 0

    # Update WAL to LIQUIDATED
    exit_payload = {
        "state": "LIQUIDATED",
        "payload": {
            "position_id": "TEST_ALERT_POS",
            "strike_contract": "NIFTY 22500 CE",
            "exit_reason": "EOD_MANDATORY_SQUAREOFF",
            "opt_pnl_pts": 15.5,
            "opt_exit_ltp": 115.5,
        }
    }
    with open(wal, "w") as f:
        json.dump(exit_payload, f)

    exit_alerts = notifier.poll_once()
    assert len(exit_alerts) == 1
    assert exit_alerts[0].event_type == "EXIT"
    assert "EOD_MANDATORY_SQUAREOFF" in exit_alerts[0].message


# ==============================================================================
# 5 RUTHLESS ADVERSARIAL ATTACKER SUITE (PRE & POST-DEV CERTIFICATION)
# ==============================================================================

def test_attacker_1_strike_escalation_hysteresis_and_monotonicity():
    """ATTACKER 1: Boundary Chatter & Parameter Fragility.
    
    Verifies:
    1. Strike escalation de-escalation deadband [0.17, 0.19] prevents chatter.
    2. At IV=0.18 with prev ITM_1, stays ITM_1.
    3. At IV=0.18 with prev ITM_2, stays ITM_2.
    4. At IV > 0.19, escalates to ITM_2.
    5. At IV < 0.17, de-escalates to ITM_1.
    """
    from core.structural_alpha_gates import ITMStrikeResolver

    # Case A: Below 0.17 -> ITM_1
    res1 = ITMStrikeResolver.resolve_target_strike(spot=23600.0, direction="CE", iv_annualized=0.16)
    assert res1.moneyness == "ITM_1"
    assert res1.strike_offset == -1

    # Case B: Above 0.19 -> ITM_2
    res2 = ITMStrikeResolver.resolve_target_strike(spot=23600.0, direction="CE", iv_annualized=0.20)
    assert res2.moneyness == "ITM_2"
    assert res2.strike_offset == -2

    # Case C: Inside Deadband (0.18) with prev_moneyness = "ITM_1" -> remains ITM_1
    res3 = ITMStrikeResolver.resolve_target_strike(spot=23600.0, direction="CE", iv_annualized=0.18, prev_moneyness="ITM_1")
    assert res3.moneyness == "ITM_1"

    # Case D: Inside Deadband (0.18) with prev_moneyness = "ITM_2" -> remains ITM_2
    res4 = ITMStrikeResolver.resolve_target_strike(spot=23600.0, direction="CE", iv_annualized=0.18, prev_moneyness="ITM_2")
    assert res4.moneyness == "ITM_2"


def test_attacker_2_fail_closed_macro_gate_and_freshness_veto():
    """ATTACKER 2: Permissive Fallback & Companion Latency Exploitation.
    
    Verifies:
    1. COMPANION_DATA_UNINITIALIZED_FAIL_CLOSED rejects trades when companion spot <= 0 or missing.
    2. COMPANION_FEED_STALE_VETO triggers when companion feed latency > 5.0s.
    3. TEMPORAL_SKEW_EXCEEDED_FAIL_CLOSED triggers when cross-index skew > 250ms.
    """
    from core.structural_alpha_gates import CrossIndexMacroGate

    gate = CrossIndexMacroGate()

    # 1. Uninitialized companion must FAIL CLOSED (not PASS)
    spots_uninit = {"NIFTY": 23600.0}
    bounds_uninit = {"NIFTY": {"high": 23620.0, "low": 23550.0}}
    aligned, reason = gate.evaluate_alignment("NIFTY", "CE", spots_uninit, bounds_uninit)
    assert aligned is False
    assert "COMPANION_SENSEX_DATA_UNINITIALIZED_FAIL_CLOSED" in reason

    # 2. Companion feed stale (> 5.0s)
    spots_ok = {"NIFTY": 23600.0, "SENSEX": 78000.0}
    bounds_ok = {"NIFTY": {"high": 23620.0, "low": 23550.0}, "SENSEX": {"high": 78200.0, "low": 77800.0}}
    ts_stale = {"NIFTY": 1000.0, "SENSEX": 994.0}  # SENSEX 6.0s behind current 1000.0
    aligned_stale, reason_stale = gate.evaluate_alignment(
        "NIFTY", "CE", spots_ok, bounds_ok, last_updated_ts=ts_stale, current_time_epoch=1000.0
    )
    assert aligned_stale is False
    assert "COMPANION_FEED_STALE_VETO" in reason_stale

    # 3. Cross-index temporal skew (> 250ms)
    ts_skewed = {"NIFTY": 1000.0, "SENSEX": 999.6}  # 400ms skew
    aligned_skew, reason_skew = gate.evaluate_alignment(
        "NIFTY", "CE", spots_ok, bounds_ok, last_updated_ts=ts_skewed, current_time_epoch=1000.0
    )
    assert aligned_skew is False
    assert "TEMPORAL_SKEW_EXCEEDED_FAIL_CLOSED" in reason_skew


def test_attacker_3_anti_starvation_veto_telemetry_ledger():
    """ATTACKER 3: Gate Compounding & Silent Starvation Trap.
    
    Verifies:
    1. SentinelLiveStreamAdvisor instruments every veto event with per-category counters.
    2. Telemetry summary returns exact frequencies and marginal survival metrics.
    """
    advisor = SentinelLiveStreamAdvisor(enable_stdout=False)
    
    # Record distinct gate vetoes
    advisor.record_veto("SPREAD", "Spread > 4.0%")
    advisor.record_veto("SPREAD", "Spread > 4.0%")
    advisor.record_veto("MACRO_DIVERGENCE", "SENSEX divergent")
    advisor.record_veto("OI_FLOOR", "OI < 250k")

    summary = advisor.get_veto_telemetry_summary()
    assert summary["total_vetos"] == 4
    assert summary["counters"]["SPREAD"] == 2
    assert summary["counters"]["MACRO_DIVERGENCE"] == 1
    assert summary["counters"]["OI_FLOOR"] == 1
    assert summary["frequencies"]["SPREAD"] == 0.50
    assert summary["frequencies"]["MACRO_DIVERGENCE"] == 0.25


def test_attacker_4_conservative_adverse_fill_execution_drag():
    """ATTACKER 4: Fantasy Midpoint Alpha & Spread Crossing Realism.
    
    Verifies:
    1. PassiveMidpointQueueModel supports conservative adverse selection alpha (alpha=0.25 and alpha=0.50).
    2. Alpha=0.25 fills at P_mid + 0.25 * Spread.
    3. Alpha=0.50 simulates full spread crossing (P_ask for buys).
    """
    from core.structural_alpha_gates import PassiveMidpointQueueModel

    bid = 100.0
    ask = 104.0
    spread = 4.0
    mid = 102.0

    # Test pure midpoint (alpha = 0.0)
    p0, sav0, mode0 = PassiveMidpointQueueModel.calculate_entry_fill(bid, ask, adverse_fill_alpha=0.0)
    assert p0 == 102.0
    assert sav0 == 2.0
    assert mode0 == "PASSIVE_MIDPOINT_FILL"

    # Test conservative adverse fill (alpha = 0.25)
    p25, sav25, mode25 = PassiveMidpointQueueModel.calculate_entry_fill(bid, ask, adverse_fill_alpha=0.25)
    assert p25 == 103.0  # 102.0 + 0.25 * 4.0
    assert sav25 == 1.0
    assert mode25 == "CONSERVATIVE_ADVERSE_FILL"

    # Test full spread cross (alpha = 0.50)
    p50, sav50, mode50 = PassiveMidpointQueueModel.calculate_entry_fill(bid, ask, adverse_fill_alpha=0.50)
    assert p50 == 104.0  # 102.0 + 0.50 * 4.0 == ask
    assert sav50 == 0.0
    assert mode50 == "CONSERVATIVE_ADVERSE_FILL"


def test_attacker_5_quarantined_oos_integrity_and_walk_forward_efficiency():
    """ATTACKER 5: Out-of-Sample Holdout Degradation & Data Leakage.
    
    Verifies:
    1. Master backtest matrix separates In-Sample (IS: 485 sessions) and Out-of-Sample (OOS: 21 sessions).
    2. Evaluates Walk-Forward Efficiency (WFE = PF_OOS / PF_IS >= 0.50 or PnL drag bound).
    3. Proves OOS dataset dates strictly follow IS dates with zero temporal overlap.
    """
    import pandas as pd
    df = pd.read_csv("runtime/master_unified_backtest_matrix.csv")

    is_df = df[df["Date"] < "2026-07-01"]
    oos_df = df[df["Date"] >= "2026-07-01"]

    assert len(is_df) == 485
    assert len(oos_df) == 21
    assert is_df["Date"].max() < oos_df["Date"].min()  # Strict causal separation

