from __future__ import annotations

import json

from research.regime_analysis import build_regime_analysis
from research.setup_expectancy import build_setup_expectancy_report
from research.time_bucket_analysis import build_time_bucket_analysis


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_setup_expectancy_calculates_expected_metrics(tmp_path):
    suggestions_path = tmp_path / "suggestions.jsonl"
    updates_path = tmp_path / "trade_updates.jsonl"

    _write_jsonl(
        suggestions_path,
        [
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T13:50:00Z",
                "strategy_name": "CORE",
                "setup_type": "BREAKOUT",
                "regime": "TRENDING_UP",
                "allocation_reason": "allocated",
            },
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T15:00:00Z",
                "strategy_name": "CORE",
                "setup_type": "PULLBACK",
                "regime": "RANGE",
                "allocation_reason": "deferred_slot_cap",
            },
            {
                "trade_id": "T3",
                "symbol": "BANKNIFTY",
                "timestamp": "2026-03-19T14:20:00Z",
                "strategy_name": "ZERO_HERO",
                "setup_type": "MEAN_REVERSION",
                "regime": "VOLATILE",
            },
        ],
    )
    _write_jsonl(
        updates_path,
        [
            {"trade_id": "T1", "timestamp": "2026-03-19T14:30:00Z", "realized_pnl": 100.0, "outcome_label": "WIN"},
            {"trade_id": "T2", "timestamp": "2026-03-19T15:20:00Z", "realized_pnl": -50.0, "outcome_label": "LOSS"},
            {"trade_id": "T3", "timestamp": "2026-03-19T14:40:00Z", "realized_pnl": 20.0, "outcome_label": "WIN"},
        ],
    )

    report = build_setup_expectancy_report(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )

    assert report["trade_count"] == 3
    assert report["expectancy"] == 23.333333
    assert report["win_rate"] == 0.666667
    assert report["avg_win"] == 60.0
    assert report["avg_loss"] == -50.0


def test_grouping_outputs_are_stable(tmp_path):
    suggestions_path = tmp_path / "suggestions.jsonl"
    updates_path = tmp_path / "trade_updates.jsonl"

    _write_jsonl(
        suggestions_path,
        [
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T13:50:00Z",
                "strategy_name": "CORE",
                "setup_type": "BREAKOUT",
                "regime": "TRENDING_UP",
                "allocation_reason": "allocated",
            },
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T15:00:00Z",
                "strategy_name": "CORE",
                "setup_type": "PULLBACK",
                "regime": "RANGE",
                "allocation_reason": "deferred_slot_cap",
            },
        ],
    )
    _write_jsonl(
        updates_path,
        [
            {"trade_id": "T1", "timestamp": "2026-03-19T14:30:00Z", "realized_pnl": 100.0},
            {"trade_id": "T2", "timestamp": "2026-03-19T15:20:00Z", "realized_pnl": -50.0},
        ],
    )

    first = build_regime_analysis(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )
    second = build_regime_analysis(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )

    assert first == second
    assert [row["bucket"] for row in first["performance_by_regime"]["rows"]] == ["RANGE", "TRENDING_UP"]


def test_missing_optional_columns_degrade_gracefully(tmp_path):
    suggestions_path = tmp_path / "suggestions.jsonl"
    updates_path = tmp_path / "trade_updates.jsonl"

    _write_jsonl(
        suggestions_path,
        [
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "strategy_name": "CORE",
            }
        ],
    )
    _write_jsonl(
        updates_path,
        [
            {"trade_id": "T1", "timestamp": "2026-03-19T14:30:00Z", "realized_pnl": 10.0},
        ],
    )

    setup_report = build_setup_expectancy_report(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )
    regime_report = build_regime_analysis(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )
    time_report = build_time_bucket_analysis(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )

    assert setup_report["performance_by_setup_type"]["rows"][0]["bucket"] == "UNKNOWN"
    assert regime_report["performance_by_regime"]["rows"][0]["bucket"] == "UNKNOWN"
    assert "missing_regime_tags_defaulted_to_UNKNOWN" in regime_report["notes"]
    assert time_report["performance_by_time_bucket"]["rows"][0]["bucket"] == "UNKNOWN"
    assert "missing_timestamps_defaulted_to_UNKNOWN" in time_report["notes"]
