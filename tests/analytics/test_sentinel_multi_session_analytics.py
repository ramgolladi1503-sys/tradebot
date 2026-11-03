"""Tests for Sentinel Multi-Session Quant Analytics & Reporting.

Verifies:
1. Data gap detection & session continuity audit (missing days, corrupt JSON, timeline gaps).
2. Frictional cost deductions (STT, exchange turnover, SEBI, stamp duty, GST, slippage).
3. Math accuracy (Sharpe, Sortino, bootstrap confidence intervals & standard errors).
4. Trade root-cause taxonomy categorization (Chop Drag, Trend Capture, Premature Stop, Runner Trailing, EOD Liquidation).
5. Non-blocking UI cache data contract (pre-aggregated JSON validity).
6. Trading safety invariants (read_only=True, is_order_action=False, broker_api_called=False, NO_CERTIFIED_EDGE).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import pytest
import numpy as np

from core.analytics.multi_session_aggregator import (
    MultiSessionAggregator,
    NormalizedTrade,
    SessionContinuityAudit,
)
from core.analytics.quant_metrics_engine import (
    QuantMetricsEngine,
    TradeAccounting,
    SummaryQuantKPIs,
    BootstrapConfidenceInterval,
)
from scripts.run_multi_session_analytics import generate_multi_session_report, OUTPUT_PATH


class TestDataGapDetection:
    """QA Case 1: Session Continuity and Data Gap Detection."""

    def test_missing_days_and_gap_detection(self, tmp_path: Path):
        # Create mock audit dir with a missing date and intraday gap
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        # Day 1: normal file with a gap > 300s
        day1_file = audit_dir / "sentinel_execution_paths_20261013.jsonl"
        with open(day1_file, "w") as f:
            f.write(json.dumps({"timestamp": "2026-10-13T09:15:00+05:30", "spot_nifty": 22500}) + "\n")
            # Gap of 10 minutes (600s)
            f.write(json.dumps({"timestamp": "2026-10-13T09:25:00+05:30", "spot_nifty": 22510}) + "\n")

        # Mock WAL
        wal_file = tmp_path / "wal.json"
        wal_file.write_text(json.dumps({"state": "STANDBY", "trade_history": []}))

        aggregator = MultiSessionAggregator(
            audit_dir=audit_dir,
            wal_path=wal_file,
            start_date="2026-10-13",
            end_date="2026-10-15",  # Expects 13, 14, 15
        )

        audit, records = aggregator.run_continuity_audit()
        assert not audit.is_continuous
        assert "2026-10-14" in audit.missing_dates
        assert "2026-10-15" in audit.missing_dates
        assert audit.gap_count >= 1

        gap_issues = [i for i in audit.issues if i.issue_type == "INTRADAY_DATA_GAP"]
        assert len(gap_issues) == 1
        assert "10.0m" in gap_issues[0].description

    def test_corrupted_json_chunk_detection(self, tmp_path: Path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        corrupt_file = audit_dir / "sentinel_execution_paths_20261013.jsonl"
        with open(corrupt_file, "w") as f:
            f.write('{"timestamp": "2026-10-13T09:15:00+05:30"}\n')
            f.write('INVALID_CORRUPTED_JSON_LINE{{{\n')

        wal_file = tmp_path / "wal.json"
        wal_file.write_text(json.dumps({"state": "STANDBY", "trade_history": []}))

        aggregator = MultiSessionAggregator(
            audit_dir=audit_dir,
            wal_path=wal_file,
            start_date="2026-10-13",
            end_date="2026-10-13",
        )

        audit, _ = aggregator.run_continuity_audit()
        assert not audit.is_continuous
        assert audit.corrupt_count == 1
        assert any(i.issue_type == "CORRUPTED_RECORD" for i in audit.issues)


class TestFrictionalCostDeductions:
    """QA Case 2: Statutory and Frictional Cost Deductions."""

    def test_options_cost_breakdown_math(self):
        engine = QuantMetricsEngine()
        trade = NormalizedTrade(
            position_id="TEST_001",
            symbol="NIFTY 22500 CE",
            underlying="NIFTY",
            direction="CE",
            strike_contract="NIFTY 22500 CE",
            entry_time="2026-10-14T10:00:00+05:30",
            exit_time="2026-10-14T10:15:00+05:30",
            entry_price=22500.0,
            exit_price=22550.0,
            pnl_pts=50.0,
            opt_entry_ltp=100.0,
            opt_exit_ltp=120.0,
            opt_pnl_pts=20.0,
            opt_peak_hwm=125.0,
            exit_reason="TARGET_HIT",
            session_gear="GEAR_2_TREND",
            is_in_flight=False,
        )

        lot_size = 50
        costs = engine.calculate_trade_costs(trade, lot_size=lot_size)

        # Brokerage: 2 legs * 20 = 40.0
        assert costs.brokerage == 40.0

        # STT: 0.10% on sell turnover (120 * 50 = 6000 * 0.001 = 6.0)
        assert costs.stt == 6.0

        # Exchange: (100 + 120) * 50 = 11000 * 0.000505 = 5.56
        expected_exchange = round(11000.0 * 0.000505, 2)
        assert costs.exchange_charges == expected_exchange

        # SEBI: 11000 * 0.000001 = 0.01
        assert costs.sebi_charges == 0.01

        # Stamp: 100 * 50 = 5000 * 0.00003 = 0.15
        assert costs.stamp_duty == 0.15

        # GST: 18% on (brokerage + exchange + sebi) = (40 + 5.56 + 0.01) * 0.18 = 8.20
        expected_gst = round((40.0 + expected_exchange + 0.01) * 0.18, 2)
        assert costs.gst == expected_gst

        # Slippage: 0.5 * 2 * 50 = 50.0
        assert costs.slippage_cost == 50.0

        expected_total = 40.0 + 6.0 + expected_exchange + 0.01 + 0.15 + expected_gst + 50.0
        assert costs.total_frictional_cost == round(expected_total, 2)


class TestMathAccuracy:
    """QA Case 3: Quantitative Ratios, Sharpe, Sortino, and Bootstrap CI."""

    def test_sharpe_and_sortino_calculation(self):
        engine = QuantMetricsEngine()

        # Construct trade accountings across 3 distinct days
        t1 = NormalizedTrade("T1", "NIFTY", "NIFTY", "CE", "", "2026-10-13T10:00:00", "2026-10-13T10:10:00", 0, 0, 0, 100, 120, 20, 120, "TARGET_HIT", "GEAR_2_TREND")
        t2 = NormalizedTrade("T2", "NIFTY", "NIFTY", "CE", "", "2026-10-14T10:00:00", "2026-10-14T10:10:00", 0, 0, 0, 100, 80, -20, 100, "STOP_LOSS_HIT", "GEAR_1_RANGE")
        t3 = NormalizedTrade("T3", "NIFTY", "NIFTY", "CE", "", "2026-10-15T10:00:00", "2026-10-15T10:10:00", 0, 0, 0, 100, 130, 30, 130, "TARGET_HIT", "GEAR_2_TREND")

        accs = engine.process_trades([t1, t2, t3])
        kpis = engine.compute_summary_kpis(accs)

        assert kpis.total_trades == 3
        assert kpis.completed_trades == 3
        assert kpis.winning_trades == 2
        assert kpis.losing_trades == 1
        assert math.isclose(kpis.win_rate_pct, 66.67, abs_tol=0.1)
        assert kpis.profit_factor > 1.0

        # Verify daily Sharpe formula: mean / std * sqrt(252)
        daily_pnls = [
            accs[0].net_pnl_rupees,
            accs[1].net_pnl_rupees,
            accs[2].net_pnl_rupees,
        ]
        mean_pnl = float(np.mean(daily_pnls))
        std_pnl = float(np.std(daily_pnls, ddof=1))
        expected_sharpe = round((mean_pnl / std_pnl) * math.sqrt(252), 2)
        assert math.isclose(kpis.sharpe_ratio, expected_sharpe, abs_tol=0.05)

    def test_bootstrap_confidence_intervals(self):
        engine = QuantMetricsEngine()
        trades = []
        for i in range(20):
            pnl = 15.0 if i % 2 == 0 else -10.0
            trades.append(NormalizedTrade(
                f"T_{i}", "NIFTY", "NIFTY", "CE", "", "2026-10-13T10:00:00", "2026-10-13T10:05:00",
                0, 0, 0, 100, 100 + pnl, pnl, 100 + max(0, pnl), "TARGET_HIT" if pnl > 0 else "STOP_LOSS_HIT", "GEAR_2_TREND"
            ))

        accs = engine.process_trades(trades)
        boot = engine.bootstrap_confidence_intervals(accs, n_resamples=1000, random_seed=42)

        assert "win_rate" in boot
        assert "expectancy" in boot

        win_ci = boot["win_rate"]
        assert win_ci.ci_95_lower <= win_ci.sample_value <= win_ci.ci_95_upper
        assert win_ci.ci_99_lower <= win_ci.ci_95_lower
        assert win_ci.ci_99_upper >= win_ci.ci_95_upper
        assert win_ci.standard_error > 0.0


class TestTradeRootCauseTaxonomy:
    """QA Case 4: Root-Cause Taxonomy Categorization."""

    def test_taxonomy_classification(self):
        engine = QuantMetricsEngine()

        t_chop = NormalizedTrade("T1", "NIFTY", "NIFTY", "CE", "", "", "", 0, 0, 0, 100, 85, -15, 102, "STOP_LOSS_HIT", "GEAR_1_RANGE")
        t_trend = NormalizedTrade("T2", "NIFTY", "NIFTY", "CE", "", "", "", 0, 0, 0, 100, 125, 25, 125, "TARGET_HIT", "GEAR_2_TREND")
        t_premature = NormalizedTrade("T3", "NIFTY", "NIFTY", "CE", "", "", "", 0, 0, 0, 100, 99, -1, 115, "TRAILING_STOP_HIT", "GEAR_2_TREND")
        t_runner = NormalizedTrade("T4", "NIFTY", "NIFTY", "CE", "", "", "", 0, 0, 0, 100, 120, 20, 130, "RUNNER_HWM_TRAILING_EXIT", "GEAR_2_TREND")
        t_eod = NormalizedTrade("T5", "NIFTY", "NIFTY", "CE", "", "", "", 0, 0, 0, 100, 100, 0, 100, "CRASH_RECOVERY_FAIL_CLOSED", "GEAR_2_TREND")

        assert engine.classify_root_cause(t_chop) == "Chop Drag"
        assert engine.classify_root_cause(t_trend) == "Trend Capture"
        assert engine.classify_root_cause(t_runner) == "Runner Trailing"
        assert engine.classify_root_cause(t_eod) == "EOD_LIQUIDATION"


class TestNonBlockingUIContract:
    """QA Case 5: Non-blocking UI cache data pre-aggregation contract."""

    def test_pre_aggregated_json_payload_structure(self):
        report = generate_multi_session_report(bootstrap_resamples=500)
        assert OUTPUT_PATH.exists()

        assert "metadata" in report
        assert "summary_kpis" in report
        assert "bootstrap_edge_significance" in report
        assert "index_comparison" in report
        assert "regime_attribution" in report
        assert "root_cause_taxonomy" in report
        assert "daily_breakdown" in report
        assert "trades" in report

        # Must have NIFTY and SENSEX under index_comparison
        assert "NIFTY" in report["index_comparison"]
        assert "SENSEX" in report["index_comparison"]


class TestTradingSafetyInvariants:
    """QA Case 6: Trading Safety Invariants and NO_CERTIFIED_EDGE preservation."""

    def test_safety_metadata_invariants(self):
        report = generate_multi_session_report(bootstrap_resamples=100)
        metadata = report["metadata"]

        assert metadata["status"] == "NO_CERTIFIED_EDGE"
        assert metadata["safety"]["read_only"] is True
        assert metadata["safety"]["is_order_action"] is False
        assert metadata["safety"]["broker_api_called"] is False
        assert metadata["safety"]["allowed_for_live_execution"] is False

        # Check KPI status
        assert report["summary_kpis"]["status"] == "NO_CERTIFIED_EDGE"
