from __future__ import annotations

import json

from research.fill_quality_calibration import build_fill_quality_calibration_report


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_fill_quality_calibration_is_stable_for_repeated_input(tmp_path):
    fill_quality_path = tmp_path / "fill_quality.jsonl"
    perf_path = tmp_path / "execution_performance.jsonl"

    _write_jsonl(
        fill_quality_path,
        [
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "ts": "2026-03-19T09:20:00+05:30",
                "decision_mid": 12.0,
                "decision_spread": 1.0,
                "fill_price": 13.0,
                "slippage_vs_mid": 1.0,
                "qty": 25,
                "volume": 120,
                "depth_best": 10,
            },
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "ts": "2026-03-19T09:22:00+05:30",
                "decision_mid": 180.0,
                "decision_spread": 0.4,
                "fill_price": 180.1,
                "slippage_vs_mid": 0.1,
                "qty": 5,
                "volume": 25000,
                "depth_best": 600,
            },
        ],
    )
    _write_jsonl(
        perf_path,
        [
            {
                "event": "execution_performance_updated",
                "instrument": "NIFTY",
                "sample_size": 20,
                "fill_rate": 0.8,
            }
        ],
    )

    first = build_fill_quality_calibration_report(
        fill_quality_path=fill_quality_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=tmp_path / "missing_trade_updates.jsonl",
        execution_performance_path=perf_path,
    )
    second = build_fill_quality_calibration_report(
        fill_quality_path=fill_quality_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=tmp_path / "missing_trade_updates.jsonl",
        execution_performance_path=perf_path,
    )

    assert first == second


def test_thin_bucket_calibrates_worse_than_liquid_bucket(tmp_path):
    fill_quality_path = tmp_path / "fill_quality.jsonl"

    _write_jsonl(
        fill_quality_path,
        [
            {
                "trade_id": "T-THIN-1",
                "symbol": "NIFTY",
                "ts": "2026-03-19T09:20:00+05:30",
                "decision_mid": 12.0,
                "decision_spread": 1.2,
                "fill_price": 13.2,
                "slippage_vs_mid": 1.2,
                "qty": 50,
                "volume": 100,
                "depth_best": 8,
            },
            {
                "trade_id": "T-THIN-2",
                "symbol": "NIFTY",
                "ts": "2026-03-19T09:24:00+05:30",
                "decision_mid": 14.0,
                "decision_spread": 1.4,
                "fill_price": 15.1,
                "slippage_vs_mid": 1.1,
                "qty": 45,
                "volume": 140,
                "depth_best": 9,
            },
            {
                "trade_id": "T-LIQ-1",
                "symbol": "NIFTY",
                "ts": "2026-03-19T09:21:00+05:30",
                "decision_mid": 180.0,
                "decision_spread": 0.4,
                "fill_price": 180.1,
                "slippage_vs_mid": 0.1,
                "qty": 5,
                "volume": 25000,
                "depth_best": 600,
            },
            {
                "trade_id": "T-LIQ-2",
                "symbol": "NIFTY",
                "ts": "2026-03-19T09:23:00+05:30",
                "decision_mid": 190.0,
                "decision_spread": 0.5,
                "fill_price": 190.08,
                "slippage_vs_mid": 0.08,
                "qty": 6,
                "volume": 22000,
                "depth_best": 550,
            },
        ],
    )

    report = build_fill_quality_calibration_report(
        fill_quality_path=fill_quality_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=tmp_path / "missing_trade_updates.jsonl",
        execution_performance_path=tmp_path / "missing_execution_performance.jsonl",
    )

    rows = report["profiles"]["rows"]
    thin = next(row for row in rows if row["liquidity_bucket"] == "THIN")
    liquid = next(row for row in rows if row["liquidity_bucket"] == "LIQUID")

    assert thin["expected_fill_deviation"] > liquid["expected_fill_deviation"]
    assert thin["slippage_multiplier"] > liquid["slippage_multiplier"]


def test_missing_optional_history_degrades_gracefully(tmp_path):
    fill_quality_path = tmp_path / "fill_quality.jsonl"

    _write_jsonl(
        fill_quality_path,
        [
            {
                "trade_id": "T1",
                "symbol": "BANKNIFTY",
                "ts": "2026-03-19T14:10:00Z",
                "decision_mid": 110.0,
                "decision_spread": 0.8,
                "fill_price": 110.4,
                "slippage_vs_mid": 0.4,
                "qty": 3,
                "volume": 3000,
            }
        ],
    )

    report = build_fill_quality_calibration_report(
        fill_quality_path=fill_quality_path,
        trade_log_path=tmp_path / "missing_trade_log.jsonl",
        trade_updates_path=tmp_path / "missing_trade_updates.jsonl",
        execution_performance_path=tmp_path / "missing_execution_performance.jsonl",
    )

    assert report["profile_count"] == 1
    assert any(str(note).startswith("missing_optional_artifacts:") for note in report["notes"])
    assert "missing_depth_context_defaulted_to_volume_spread" in report["notes"]
