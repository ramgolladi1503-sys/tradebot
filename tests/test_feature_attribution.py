from __future__ import annotations

import json

from research.feature_attribution import build_feature_attribution_report


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_predictive_feature_ranks_above_noisy_features(tmp_path):
    suggestions_path = tmp_path / "suggestions.jsonl"
    updates_path = tmp_path / "trade_updates.jsonl"

    suggestion_rows = []
    update_rows = []
    trend_values = [0.95, 0.88, 0.81, 0.20, 0.12, 0.05]
    momentum_values = [0.51, 0.23, 0.77, 0.24, 0.72, 0.49]
    pnls = [120.0, 80.0, 50.0, -40.0, -70.0, -110.0]

    for idx, (trend_score, momentum_score, pnl) in enumerate(zip(trend_values, momentum_values, pnls), start=1):
        trade_id = f"T{idx}"
        suggestion_rows.append(
            {
                "trade_id": trade_id,
                "symbol": "NIFTY",
                "timestamp": f"2026-03-19T14:0{idx}:00Z",
                "strategy_name": "CORE",
                "setup_type": "BREAKOUT",
                "regime": "TRENDING_UP" if pnl > 0 else "RANGE",
                "allocation_reason": "allocated",
                "trend_alignment_score": trend_score,
                "momentum_score": momentum_score,
                "liquidity_score": 0.55,
                "spread_score": 0.60,
            }
        )
        update_rows.append(
            {
                "trade_id": trade_id,
                "timestamp": f"2026-03-19T14:3{idx}:00Z",
                "realized_pnl": pnl,
            }
        )

    _write_jsonl(suggestions_path, suggestion_rows)
    _write_jsonl(updates_path, update_rows)

    report = build_feature_attribution_report(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )

    ranked = report["component_usefulness_ranked"]["rows"]
    assert ranked[0]["component"] == "trend_alignment_score"
    assert ranked[0]["usefulness_score"] >= ranked[1]["usefulness_score"]


def test_missing_component_columns_do_not_crash(tmp_path):
    suggestions_path = tmp_path / "suggestions.jsonl"
    updates_path = tmp_path / "trade_updates.jsonl"

    _write_jsonl(
        suggestions_path,
        [
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "timestamp": "2026-03-19T14:01:00Z",
                "strategy_name": "CORE",
            }
        ],
    )
    _write_jsonl(
        updates_path,
        [
            {
                "trade_id": "T1",
                "timestamp": "2026-03-19T14:31:00Z",
                "realized_pnl": 25.0,
            }
        ],
    )

    report = build_feature_attribution_report(
        suggestions_path=suggestions_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=updates_path,
    )

    rows = report["component_attribution_summary"]["rows"]
    assert len(rows) >= 8
    assert any(row["available_trade_count"] == 0 for row in rows)
    assert any(str(note).startswith("missing_components:") for note in report["notes"])
