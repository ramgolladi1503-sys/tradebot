"""Unit and regression tests for scripts/run_daily_sentinel_analytics.py.

Verifies Gate 3, 4, 5 requirements:
1. Calendar validation (rejects weekends and exchange holidays).
2. Broker 15:15 RMS auto-square-off cap (forces exit at 15:15:00 on late holding counterfactuals).
3. Rolling 100 trade pooling and per-index breakdown computation.
4. Execution report generation (Markdown & JSON output).
5. Non-negotiable trading safety invariants.
"""

import json
from datetime import date
from pathlib import Path
import pytest

from core.analytics.multi_session_aggregator import NormalizedTrade
from scripts.run_daily_sentinel_analytics import (
    is_market_trading_day,
    apply_1515_rms_square_off_cap,
    compute_rolling_metrics,
    run_daily_sentinel_analytics,
)
from core.analytics.quant_metrics_engine import QuantMetricsEngine


def test_calendar_validation_rejects_weekends_and_holidays():
    """Gate 3: Validate calendar rejection of weekend and exchange holiday."""
    # Weekend (Sunday 2026-10-25)
    is_trading, reason = is_market_trading_day(date(2026, 10, 25))
    assert is_trading is False
    assert reason == "MARKET_CLOSED_WEEKEND"

    # NSE F&O Holiday (e.g. 2026-10-02 Mahatma Gandhi Jayanti)
    is_trading, reason = is_market_trading_day(date(2026, 10, 2))
    assert is_trading is False
    assert reason == "MARKET_CLOSED_HOLIDAY"

    # Active trading session (Monday 2026-10-26)
    is_trading, reason = is_market_trading_day(date(2026, 10, 26))
    assert is_trading is True
    assert reason == "TRADING_SESSION"


def test_broker_1515_rms_squareoff_cap():
    """Gate 5: Trades with exit > 15:15:00 or MARKET_CLOSE_AUTO_SQUAREOFF are capped at 15:15:00."""
    t1 = NormalizedTrade(
        position_id="TRADE_LATE_1",
        symbol="NIFTY 22600 CE",
        underlying="NIFTY",
        direction="CE",
        strike_contract="NIFTY 22600 CE",
        entry_time="2026-10-26T15:00:00",
        exit_time="2026-10-26T15:30:00",
        entry_price=22600.0,
        exit_price=22650.0,
        pnl_pts=50.0,
        opt_entry_ltp=100.0,
        opt_exit_ltp=120.0,
        opt_pnl_pts=20.0,
        opt_peak_hwm=125.0,
        exit_reason="MARKET_CLOSE_AUTO_SQUAREOFF",
        session_gear="GEAR_2_TREND",
        is_in_flight=False,
    )
    t2 = NormalizedTrade(
        position_id="TRADE_NORMAL_2",
        symbol="NIFTY 22600 CE",
        underlying="NIFTY",
        direction="CE",
        strike_contract="NIFTY 22600 CE",
        entry_time="2026-10-26T10:00:00",
        exit_time="2026-10-26T10:30:00",
        entry_price=22600.0,
        exit_price=22620.0,
        pnl_pts=20.0,
        opt_entry_ltp=100.0,
        opt_exit_ltp=110.0,
        opt_pnl_pts=10.0,
        opt_peak_hwm=115.0,
        exit_reason="RUNNER_HWM_TRAILING_EXIT",
        session_gear="GEAR_2_TREND",
        is_in_flight=False,
    )

    capped = apply_1515_rms_square_off_cap([t1, t2])
    assert len(capped) == 2

    # t1 should be capped at 15:15:00
    assert capped[0].exit_time == "2026-10-26T15:15:00"
    assert capped[0].exit_reason == "BROKER_1515_RMS_SQUAREOFF"

    # t2 should remain unchanged
    assert capped[1].exit_time == "2026-10-26T10:30:00"
    assert capped[1].exit_reason == "RUNNER_HWM_TRAILING_EXIT"


def test_rolling_100_trades_pooling_and_slices():
    """Gate 5: Rolling 100 trade pooling and per-index breakdown."""
    engine = QuantMetricsEngine()
    test_trades = []
    # Create 120 simulated trades across NIFTY, BANKNIFTY, SENSEX
    for i in range(120):
        idx = "NIFTY" if i % 3 == 0 else ("BANKNIFTY" if i % 3 == 1 else "SENSEX")
        pnl = 10.0 if i % 2 == 0 else -5.0
        t = NormalizedTrade(
            position_id=f"T_{i:03d}",
            symbol=f"{idx} STRIKE CE",
            underlying=idx,
            direction="CE",
            strike_contract=f"{idx} STRIKE CE",
            entry_time=f"2026-10-15T10:{i%60:02d}:00",
            exit_time=f"2026-10-15T10:{i%60:02d}:30",
            entry_price=20000.0,
            exit_price=20010.0,
            pnl_pts=10.0,
            opt_entry_ltp=100.0,
            opt_exit_ltp=100.0 + pnl,
            opt_pnl_pts=pnl,
            opt_peak_hwm=100.0 + max(0.0, pnl),
            exit_reason="TRAIL_EXIT",
            session_gear="GEAR_2_TREND",
            is_in_flight=False,
        )
        test_trades.append(t)

    accountings = engine.process_trades(test_trades)
    rolling = compute_rolling_metrics(accountings, window=100)

    assert rolling["window_target"] == 100
    assert rolling["pooled"]["sample_size"] == 100
    assert "NIFTY" in rolling["per_index"]
    assert "BANKNIFTY" in rolling["per_index"]
    assert "SENSEX" in rolling["per_index"]
    # Check that KPI fields exist
    kpis = rolling["pooled"]["kpis"]
    assert "win_rate_pct" in kpis
    assert "net_pnl_rupees" in kpis
    assert "profit_factor" in kpis


def test_daily_sentinel_analytics_end_to_end(tmp_path):
    """Run daily sentinel analytics end-to-end and verify JSON & Markdown reports."""
    out_md = tmp_path / "DAILY_REPORT.md"
    out_json = tmp_path / "DAILY_REPORT.json"

    res = run_daily_sentinel_analytics(
        target_date="2026-10-26",
        output_md=out_md,
        output_json=out_json,
        force=True,
    )

    assert out_md.exists()
    assert out_json.exists()

    with open(out_json, "r") as f:
        data = json.load(f)

    meta = data["metadata"]
    assert meta["safety"]["read_only"] is True
    assert meta["safety"]["is_order_action"] is False
    assert meta["safety"]["broker_1515_rms_capped"] is True
    assert "daily_summary" in data
    assert "rolling_100_trades" in data
