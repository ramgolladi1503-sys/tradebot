from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts import generate_mean_reversion_trade_ledger as generator


def _write_candle(path: Path) -> None:
    timestamps = pd.date_range("2026-01-05 09:15:00", periods=20, freq="1min")
    values = [100.0 + index * 0.1 for index in range(len(timestamps))]
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": "NIFTY",
            "open": values,
            "high": [value + 0.5 for value in values],
            "low": [value - 0.5 for value in values],
            "close": values,
            "volume": 1000.0,
        }
    ).to_parquet(path)


def _write_quote(path: Path) -> None:
    pd.DataFrame(
        {
            "ts": [1783578300.0],
            "token": [12345],
            "symbol": ["BANKNIFTY 56200 CE 28 JUL 26"],
            "ltp": [100.0],
            "bid": [99.5],
            "ask": [100.5],
        }
    ).to_parquet(path)


def _prepare_runtime(tmp_path: Path) -> Path:
    base = tmp_path / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION"
    base.mkdir(parents=True)
    (base / "upstox_candle_file_audit.json").write_text(
        json.dumps({"classification": "UPSTOX_CANDLE_FILES_VALID"})
    )
    contract = tmp_path / "configs/strategy_risk_contracts"
    contract.mkdir(parents=True)
    (contract / "MEAN_REVERSION_EXTENSION.json").write_text("{}")
    return base


def test_quote_only_date_is_excluded_from_real_generator_economics(
    tmp_path, monkeypatch
):
    base = _prepare_runtime(tmp_path)
    candle_dir = tmp_path / "runtime/upstox_candidate_replay/20260105/underlying"
    candle_dir.mkdir(parents=True)
    _write_candle(candle_dir / "NIFTY_20260105.parquet")

    quote_dir = tmp_path / "runtime/upstox_candidate_replay/20260106/underlying"
    quote_dir.mkdir(parents=True)
    _write_quote(quote_dir / "BANKNIFTY 56200 CE 28 JUL 26.parquet")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["generate_mean_reversion_trade_ledger.py"])
    generator.main()

    summary_path = base / "phase_4_trade_ledger_summary.json"
    first_summary_bytes = summary_path.read_bytes()
    summary = json.loads(first_summary_bytes)
    assert summary["reconciliation"] == {
        "historical_data_catalog_days": 0,
        "parquet_trading_days": 1,
        "parquet_symbol_days": 1,
        "non_candle_parquet_files_skipped": 1,
        "non_candle_only_date_directories": 1,
        "non_candle_schema_distribution": {"NON_CANDLE_QUOTE": 1},
        "candidate_trading_days": 1,
        "ledger_trading_days": 1,
        "active_symbol_days_used_for_capacity": 1,
    }
    assert summary["cap_saturation"]["active_symbol_days"] == 1
    assert summary["cap_saturation"]["max_possible_trades"] == 4
    assert summary["zero_trade_metrics"] == {
        "zero_trade_calendar_days": 1,
        "zero_trade_symbol_days": 1,
        "one_trade_symbol_days": 0,
        "capped_symbol_days": 0,
    }

    telemetry = json.loads((base / "phase_4_pipeline_telemetry.json").read_text())
    assert telemetry["feed_snapshots_seen"] == 20
    assert telemetry["fresh_spot_snapshots"] == 20
    assert (base / "phase_4_trade_ledger.jsonl").read_text() == ""
    assert (base / "phase_4_candidates.jsonl").read_text() == ""

    generator.main()
    assert summary_path.read_bytes() == first_summary_bytes


def test_partial_candle_in_date_directory_aborts_real_generator(
    tmp_path, monkeypatch
):
    base = _prepare_runtime(tmp_path)
    malformed_dir = tmp_path / "runtime/upstox_candidate_replay/20260105/underlying"
    malformed_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": ["2026-01-05 09:15:00"],
            "symbol": ["NIFTY"],
            "open": [100.0],
            "high": [101.0],
            "close": [100.5],
        }
    ).to_parquet(malformed_dir / "NIFTY_20260105.parquet")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["generate_mean_reversion_trade_ledger.py"])
    with pytest.raises(ValueError, match="partial candle schema"):
        generator.main()

    assert not (base / "phase_4_trade_ledger_summary.json").exists()
