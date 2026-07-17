from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.ai_certification import EvidenceCertification, StrategyVerdict, certify_bundle
from core.ai_certification.exporter import export_option_replay_wfa_bundle


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _trade(index: int) -> dict:
    signal = pd.Timestamp("2026-07-01T09:15:00+05:30") + pd.Timedelta(minutes=index * 2)
    entry = signal + pd.Timedelta(minutes=1)
    exit_ts = entry + pd.Timedelta(minutes=1)
    return {
        "side": "BUY",
        "feature_cutoff_ts": signal.isoformat(),
        "signal_ts": signal.isoformat(),
        "earliest_entry_ts": entry.isoformat(),
        "entry_ts": entry.isoformat(),
        "exit_ts": exit_ts.isoformat(),
        "hold_minutes": 1.0,
        "entry_quote_side": "ask",
        "exit_quote_side": "bid",
        "entry_bid": 99.0,
        "entry_ask": 100.0,
        "exit_bid": 100.0,
        "exit_ask": 101.0,
        "exit_fill_source": "quote_side",
        "gross_pnl_value": 1.0,
        "total_costs": 2.0,
        "net_pnl_value": -1.0,
        "ambiguity_count": 0,
    }


def _decision(index: int) -> dict:
    signal = pd.Timestamp("2026-07-01T09:15:00+05:30") + pd.Timedelta(minutes=index * 2)
    return {
        "feature_cutoff_ts": signal.isoformat(),
        "signal_ts": signal.isoformat(),
        "earliest_entry_ts": (signal + pd.Timedelta(minutes=1)).isoformat(),
    }


def test_exported_wfa_bundle_certifies_without_modifying_engine_outputs(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "wfa"
    validation = source / "validation"
    dataset = tmp_path / "strict_option.csv"
    dataset.write_text("frozen strict replay source", encoding="utf-8")
    trades = [_trade(index) for index in range(100)]
    decisions = [_decision(index) for index in range(100)]
    summary = {
        "diagnostics": {"proxy_exit_mark_rows": 0},
        "certification_blockers": [],
    }
    _write_json(validation / "summary.json", summary)
    _write_json(validation / "trade_journal.json", trades)
    _write_json(validation / "decision_samples.json", decisions)
    report = {
        "engine_module": "core.option_backtest.engine.OptionBacktestEngine",
        "frozen_config": {
            "base_config": {
                "symbol": "NIFTY26JUL25000CE",
                "data_path": str(dataset),
                "research_mode": "REAL_EXECUTABLE_RESEARCH",
                "timezone": "Asia/Kolkata",
                "max_hold_minutes": 30,
                "bar_interval_minutes": 1,
                "cost_config": {"version": "phase3_v1"},
            }
        },
        "frozen_config_hash": "c" * 64,
        "run_id": "strict-wfa-001",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "partition_plan": {
            "effective_boundary_minutes": 30,
            "partitions": {
                "train": {
                    "raw_start": "2026-01-01T09:15:00+05:30",
                    "raw_end": "2026-03-01T15:30:00+05:30",
                },
                "validation": {
                    "raw_start": "2026-03-02T09:15:00+05:30",
                    "raw_end": "2026-04-01T15:30:00+05:30",
                },
                "holdout": {
                    "raw_start": "2026-04-02T09:15:00+05:30",
                    "raw_end": "2026-05-01T15:30:00+05:30",
                },
            },
        },
        "partitions": {
            "validation": {
                "status": "completed",
                "metrics": {
                    "trades_taken": 100,
                    "after_cost_expectancy": -1.0,
                    "profit_factor": 0.5,
                    "max_drawdown": 100.0,
                    "contamination_count": 0,
                },
                "certification_blockers": [],
            },
            "holdout": {"status": "skipped_validation_failed"},
        },
        "holdout_tracking": {
            "registry_available": True,
            "repeated_holdout_run": False,
            "repeated_holdout_entries": 0,
        },
        "verdict": "FAILED",
    }
    _write_json(source / "option_replay_wfa_report.json", report)
    controls = tmp_path / "controls.json"
    _write_json(
        controls,
        {
            "controls": {
                "future_mutation": True,
                "timing_shift": True,
                "cost_sensitivity": True,
            }
        },
    )
    tests = tmp_path / "tests.json"
    _write_json(
        tests,
        {
            "collected": 54,
            "passed": 54,
            "failed": 0,
            "errors": 0,
            "repository_commit": "abc123",
        },
    )
    candles = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-01T09:15:00+05:30",
                periods=100,
                freq="min",
            ),
            "bid": [99.0] * 100,
            "ask": [100.0] * 100,
            "bid_qty": [100] * 100,
            "ask_qty": [100] * 100,
        }
    )
    candles.attrs["replay_contract"] = {
        "underlying": "NIFTY",
        "option_type": "CE",
        "strike": 25000.0,
        "expiry": "2026-07-30",
        "provider": "upstox",
        "dataset_hash": "declared-source-hash",
        "bar_interval": "1min",
    }
    monkeypatch.setattr(
        "core.ai_certification.exporter.load_option_symbol_csv",
        lambda **_: candles,
    )

    bundle = export_option_replay_wfa_bundle(
        wfa_output_dir=source,
        bundle_dir=tmp_path / "bundle",
        repository_commit="abc123",
        strategy_id="OPENING_RANGE_BREAKOUT",
        strategy_verdict="NO_STRUCTURAL_EDGE",
        negative_controls_path=controls,
        test_results_path=tests,
        created_at="2026-07-17T10:30:00Z",
    )
    certification = certify_bundle(bundle)

    assert certification.evidence_certification is EvidenceCertification.CERTIFIED
    assert certification.strategy_verdict is StrategyVerdict.NO_STRUCTURAL_EDGE
    assert (bundle / "source/option_replay_wfa_report.json").read_bytes() == (
        source / "option_replay_wfa_report.json"
    ).read_bytes()
    assert (bundle / "source/validation/trade_journal.json").read_bytes() == (
        validation / "trade_journal.json"
    ).read_bytes()
