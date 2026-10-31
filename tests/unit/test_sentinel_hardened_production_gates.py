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
