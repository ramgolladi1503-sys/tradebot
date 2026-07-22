from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"guard failed for {label}: expected exactly one match")
    return text.replace(old, new)


def main() -> None:
    generator = Path("scripts/generate_mean_reversion_trade_ledger.py")
    text = generator.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''from core.research_backtest_integrity import (
    RESEARCH_NON_CANDLE_QUOTE,
''',
        '''from core.research_backtest_integrity import (
    RESEARCH_APPLEDOUBLE_METADATA,
    RESEARCH_NON_CANDLE_QUOTE,
''',
        label="AppleDouble import",
    )
    text = replace_once(
        text,
        '''    non_candle_parquet_files_skipped = 0
    non_candle_schema_distribution: dict[str, int] = {}
''',
        '''    non_candle_parquet_files_skipped = 0
    non_candle_only_date_directories = 0
    non_candle_schema_distribution: dict[str, int] = {}
''',
        label="date classification counter",
    )
    text = replace_once(
        text,
        '''            total_calendar_days += 1
            parquet_trading_days += 1
            day_trades_calendar = 0

            for parquet_file in sorted(underlying_dir.glob("*.parquet")):
''',
        '''            day_trades_calendar = 0
            day_has_candle = False

            for parquet_file in sorted(underlying_dir.glob("*.parquet")):
''',
        label="defer date counting",
    )
    text = replace_once(
        text,
        '''                if classification == RESEARCH_NON_CANDLE_QUOTE:
                    non_candle_parquet_files_skipped += 1
''',
        '''                if classification in {
                    RESEARCH_NON_CANDLE_QUOTE,
                    RESEARCH_APPLEDOUBLE_METADATA,
                }:
                    non_candle_parquet_files_skipped += 1
''',
        label="safe non-candle classifications",
    )
    text = replace_once(
        text,
        '''                parquet_symbol_days += 1
                symbol = resolved_symbol
''',
        '''                day_has_candle = True
                parquet_symbol_days += 1
                symbol = resolved_symbol
''',
        label="mark candle date",
    )
    text = replace_once(
        text,
        '''            if day_trades_calendar == 0:
                zero_trade_calendar_days += 1

    _write_jsonl(base_dir / "phase_4_trade_ledger.jsonl", ledger_rows)
''',
        '''            if day_has_candle:
                total_calendar_days += 1
                parquet_trading_days += 1
                if day_trades_calendar == 0:
                    zero_trade_calendar_days += 1
            else:
                non_candle_only_date_directories += 1
                if day_trades_calendar != 0:
                    raise AssertionError(
                        "non-candle-only date directory produced trades"
                    )

    _write_jsonl(base_dir / "phase_4_trade_ledger.jsonl", ledger_rows)
''',
        label="candle-authoritative date accounting",
    )
    text = replace_once(
        text,
        '''            "non_candle_parquet_files_skipped": non_candle_parquet_files_skipped,
            "non_candle_schema_distribution": dict(
''',
        '''            "non_candle_parquet_files_skipped": non_candle_parquet_files_skipped,
            "non_candle_only_date_directories": non_candle_only_date_directories,
            "non_candle_schema_distribution": dict(
''',
        label="date reconciliation output",
    )
    generator.write_text(text, encoding="utf-8")

    test_path = Path("tests/test_mean_reversion_corpus_directory_accounting.py")
    test_path.write_text(
        '''from __future__ import annotations

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
''',
        encoding="utf-8",
    )

    Path(".github/workflows/apply_mean_reversion_date_accounting_patch.yml").unlink()
    Path("tools/apply_mean_reversion_date_accounting_patch.py").unlink()


if __name__ == "__main__":
    main()
