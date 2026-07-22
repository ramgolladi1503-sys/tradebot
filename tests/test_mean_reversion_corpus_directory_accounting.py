from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

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


def test_quote_only_date_does_not_pollute_trading_day_or_capacity_counts(
    tmp_path, monkeypatch
):
    base = tmp_path / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION"
    base.mkdir(parents=True)
    (base / "upstox_candle_file_audit.json").write_text(
        json.dumps({"classification": "UPSTOX_CANDLE_FILES_VALID"})
    )
    contract = tmp_path / "configs/strategy_risk_contracts"
    contract.mkdir(parents=True)
    (contract / "MEAN_REVERSION_EXTENSION.json").write_text("{}")

    candle_dir = tmp_path / "runtime/upstox_candidate_replay/20260105/underlying"
    candle_dir.mkdir(parents=True)
    _write_candle(candle_dir / "NIFTY_20260105.parquet")

    quote_dir = tmp_path / "runtime/upstox_candidate_replay/20260106/underlying"
    quote_dir.mkdir(parents=True)
    _write_quote(quote_dir / "BANKNIFTY 56200 CE 28 JUL 26.parquet")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["generate_mean_reversion_trade_ledger.py"])
    generator.main()

    summary = json.loads(
        (base / "phase_4_trade_ledger_summary.json").read_text()
    )
    reconciliation = summary["reconciliation"]
    assert reconciliation["parquet_trading_days"] == 1
    assert reconciliation["parquet_symbol_days"] == 1
    assert reconciliation["candidate_trading_days"] == 1
    assert reconciliation["ledger_trading_days"] == 1
    assert reconciliation["non_candle_parquet_files_skipped"] == 1
    assert reconciliation["non_candle_only_date_directories"] == 1
    assert reconciliation["non_candle_schema_distribution"] == {
        "NON_CANDLE_QUOTE": 1
    }
    assert summary["cap_saturation"]["active_symbol_days"] == 1
