from __future__ import annotations

import json

from core.edge_baseline_audit import (
    build_edge_baseline_report,
    normalize_edge_record,
    save_edge_baseline_report,
)


def _record(
    *,
    strategy_family: str = "orb",
    regime: str = "trend",
    direction_family: str = "bullish",
    final_score: float = 0.8,
    realized_r_multiple: float = 1.0,
    simulated_pnl: float = 100.0,
    slippage_cost: float = 5.0,
    exit_reason: str = "TARGET_HIT",
    timestamp: str = "2026-05-20T09:15:00+00:00",
) -> dict:
    return {
        "timestamp": timestamp,
        "strategy_family": strategy_family,
        "regime": regime,
        "direction_family": direction_family,
        "final_score": final_score,
        "realized_r_multiple": realized_r_multiple,
        "simulated_pnl": simulated_pnl,
        "slippage_cost": slippage_cost,
        "exit_reason": exit_reason,
    }


def test_normalize_edge_record_maps_score_bucket_and_terminal_status():
    row = normalize_edge_record(
        _record(
            final_score=82.0,
            exit_reason="STOP_HIT",
            realized_r_multiple=-1.0,
            simulated_pnl=-50.0,
        )
    )

    assert row["strategy_family"] == "orb"
    assert row["regime"] == "trend"
    assert row["direction"] == "bullish"
    assert row["score"] == 0.82
    assert row["score_bucket"] == "0.75-1.00"
    assert row["terminal_status"] == "stopped"
    assert row["terminal_status_valid"] is True
    assert row["is_win"] is False


def test_build_edge_baseline_report_groups_by_family_regime_direction_and_score_bucket():
    report = build_edge_baseline_report(
        [
            _record(
                strategy_family="orb",
                regime="trend",
                direction_family="bullish",
                final_score=0.8,
                realized_r_multiple=1.5,
                simulated_pnl=100.0,
                slippage_cost=10.0,
                exit_reason="TARGET_HIT",
                timestamp="2026-05-20T09:15:00+00:00",
            ),
            _record(
                strategy_family="orb",
                regime="trend",
                direction_family="bullish",
                final_score=0.7,
                realized_r_multiple=-1.0,
                simulated_pnl=-50.0,
                slippage_cost=5.0,
                exit_reason="STOP_HIT",
                timestamp="2026-05-20T09:20:00+00:00",
            ),
        ]
    )

    assert report["source"]["read_only"] is True
    assert report["grouping"] == "strategy_family x regime x direction x score_bucket"
    groups = {
        (row["strategy_family"], row["regime"], row["direction"], row["score_bucket"]): row
        for row in report["groups"]
    }

    high = groups[("orb", "trend", "bullish", "0.75-1.00")]
    mid = groups[("orb", "trend", "bullish", "0.50-0.75")]

    assert high["sample_count"] == 1
    assert high["win_rate"] == 1.0
    assert high["average_r"] == 1.5
    assert high["median_r"] == 1.5
    assert high["slippage_adjusted_pnl"] == 90.0
    assert high["max_drawdown"] == 0.0

    assert mid["sample_count"] == 1
    assert mid["win_rate"] == 0.0
    assert mid["average_r"] == -1.0
    assert mid["median_r"] == -1.0
    assert mid["slippage_adjusted_pnl"] == -55.0
    assert mid["max_drawdown"] == 55.0


def test_score_bucket_validation_requires_high_bucket_to_outperform_mid_bucket():
    report = build_edge_baseline_report(
        [
            _record(final_score=0.8, realized_r_multiple=1.0, simulated_pnl=100.0, slippage_cost=5.0, exit_reason="TARGET_HIT"),
            _record(final_score=0.85, realized_r_multiple=0.8, simulated_pnl=70.0, slippage_cost=5.0, exit_reason="TARGET_HIT"),
            _record(final_score=0.6, realized_r_multiple=-0.5, simulated_pnl=-30.0, slippage_cost=5.0, exit_reason="STOP_HIT"),
            _record(final_score=0.65, realized_r_multiple=0.2, simulated_pnl=10.0, slippage_cost=5.0, exit_reason="TIMED_EXIT"),
        ]
    )

    comparison = report["score_bucket_validation"]["comparison"]

    assert comparison["comparable"] is True
    assert comparison["average_r_outperforms_mid"] is True
    assert comparison["win_rate_outperforms_mid"] is True
    assert comparison["slippage_adjusted_pnl_outperforms_mid"] is True
    assert comparison["scoring_predictive_on_available_data"] is True


def test_score_bucket_validation_exposes_non_predictive_scores():
    report = build_edge_baseline_report(
        [
            _record(final_score=0.9, realized_r_multiple=-1.0, simulated_pnl=-100.0, slippage_cost=10.0, exit_reason="STOP_HIT"),
            _record(final_score=0.6, realized_r_multiple=1.0, simulated_pnl=100.0, slippage_cost=10.0, exit_reason="TARGET_HIT"),
        ]
    )

    comparison = report["score_bucket_validation"]["comparison"]

    assert comparison["comparable"] is True
    assert comparison["average_r_outperforms_mid"] is False
    assert comparison["win_rate_outperforms_mid"] is False
    assert comparison["slippage_adjusted_pnl_outperforms_mid"] is False
    assert comparison["scoring_predictive_on_available_data"] is False


def test_journal_integrity_flags_unknown_terminal_status():
    report = build_edge_baseline_report(
        [
            {
                "strategy_family": "vwap_trend",
                "regime": "range",
                "direction_family": "bearish",
                "final_score": 0.4,
                "realized_r_multiple": 0.0,
                "simulated_pnl": 0.0,
            }
        ]
    )

    assert report["journal_integrity"]["total_records"] == 1
    assert report["journal_integrity"]["invalid_terminal_status_records"] == 1
    assert report["journal_integrity"]["terminal_status_counts"] == {"unknown": 1}


def test_strategy_family_filter_supports_one_family_validation():
    report = build_edge_baseline_report(
        [
            _record(strategy_family="orb", final_score=0.8),
            _record(strategy_family="vwap_trend", final_score=0.8),
        ],
        strategy_family_filter="orb",
    )

    assert report["filters"]["strategy_family"] == "orb"
    assert report["journal_integrity"]["analyzed_records"] == 1
    assert {row["strategy_family"] for row in report["groups"]} == {"orb"}


def test_save_edge_baseline_report_writes_json_atomically(tmp_path):
    report = build_edge_baseline_report([_record()])
    path = tmp_path / "edge_report.json"

    saved = save_edge_baseline_report(report, path=path)

    assert saved == path
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["version"] == report["version"]
    assert loaded["source"]["read_only"] is True
