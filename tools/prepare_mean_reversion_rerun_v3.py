from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"guard failed for {label}: expected exactly one match")
    return text.replace(old, new)


def main() -> None:
    path = Path("scripts/run_mean_reversion_postmerge_regeneration.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''import numpy as np
import pandas as pd


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
''',
        '''import numpy as np
import pandas as pd

from core.research_backtest_integrity import (
    RESEARCH_APPLEDOUBLE_METADATA,
    RESEARCH_CANDLE,
    RESEARCH_NON_CANDLE_QUOTE,
    load_research_candle_parquet,
)


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
EXPECTED_CANDLE_FILES = 1547
EXPECTED_QUOTE_DEPTH_FILES = 129
EXPECTED_APPLEDOUBLE_FILES = 1676
''',
        label="integrity imports and frozen counts",
    )

    old_block = '''    actual_files = sorted(path for path in corpus_root.rglob("*.parquet") if path.is_file())
    actual_rel = {path.relative_to(corpus_root).as_posix() for path in actual_files}
    if actual_rel != set(expected):
        raise RuntimeError(
            "corpus inventory mismatch "
            f"missing={sorted(set(expected)-actual_rel)[:20]} "
            f"extra={sorted(actual_rel-set(expected))[:20]}"
        )

    for index, relative in enumerate(sorted(expected), start=1):
        digest = _sha256(corpus_root / relative)
        if digest != expected[relative]:
            raise RuntimeError(f"parquet SHA mismatch: {relative}")
        if index % 250 == 0:
            print(f"verified {index}/{len(expected)} parquet files", flush=True)

    underlying = sorted(corpus_root.glob("*/underlying/*.parquet"))
    if not underlying:
        raise RuntimeError("frozen corpus contains no underlying parquet files")

    dates: set[str] = set()
    symbols: set[str] = set()
    row_counts: list[int] = []
    total_rows = 0
    unsorted_files = 0
    for path in underlying:
        date_key = path.parent.parent.name
        symbol = path.stem.split("_")[0]
        frame = pd.read_parquet(
            path, columns=["timestamp", "open", "high", "low", "close"]
        )
        if frame.empty:
            raise RuntimeError(f"empty underlying parquet: {path}")
        timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
        if timestamps.isna().any():
            raise RuntimeError(f"invalid timestamps: {path}")
        if timestamps.duplicated().any():
            raise RuntimeError(f"duplicate timestamps: {path}")
        if not timestamps.is_monotonic_increasing:
            unsorted_files += 1
        dates.add(date_key)
        symbols.add(symbol)
        row_counts.append(len(frame))
        total_rows += len(frame)

    ordered_dates = sorted(dates)
    uniform_rows = row_counts[0] if len(set(row_counts)) == 1 else None
    base = project_root / "runtime" / "strategy_validation" / STRATEGY_ID
    base.mkdir(parents=True, exist_ok=True)
    audit = {
        "classification": "UPSTOX_CANDLE_FILES_VALID",
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "manifest_verified": True,
        "parquet_files_verified": len(expected),
        "underlying_symbol_days": len(underlying),
        "underlying_rows": total_rows,
        "symbols": sorted(symbols),
        "first_date": ordered_dates[0],
        "last_date": ordered_dates[-1],
        "source_files_not_monotonic": unsorted_files,
    }
    catalog = {
        "source": "IMMUTABLE_PRIVATE_RELEASE",
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "date_range_found": ordered_dates,
        "trading_days_count": len(ordered_dates),
        "symbols_found": sorted(symbols),
        "rows_per_day": uniform_rows,
        "underlying_symbol_days": len(underlying),
        "underlying_rows": total_rows,
    }
'''
    new_block = '''    manifest_files = sorted(
        path
        for path in corpus_root.rglob("*.parquet")
        if path.is_file() and not path.name.startswith("._")
    )
    actual_rel = {path.relative_to(corpus_root).as_posix() for path in manifest_files}
    if actual_rel != set(expected):
        raise RuntimeError(
            "corpus inventory mismatch "
            f"missing={sorted(set(expected)-actual_rel)[:20]} "
            f"extra={sorted(actual_rel-set(expected))[:20]}"
        )

    for index, relative in enumerate(sorted(expected), start=1):
        digest = _sha256(corpus_root / relative)
        if digest != expected[relative]:
            raise RuntimeError(f"parquet SHA mismatch: {relative}")
        if index % 250 == 0:
            print(f"verified {index}/{len(expected)} parquet files", flush=True)

    underlying = sorted(corpus_root.glob("*/underlying/*.parquet"))
    if not underlying:
        raise RuntimeError("frozen corpus contains no underlying parquet files")

    dates: set[str] = set()
    symbols: set[str] = set()
    row_counts: list[int] = []
    total_rows = 0
    candle_files = 0
    quote_depth_files = 0
    appledouble_files = 0
    for parquet_path in underlying:
        classification, frame, symbol = load_research_candle_parquet(parquet_path)
        if classification == RESEARCH_APPLEDOUBLE_METADATA:
            appledouble_files += 1
            continue
        if classification == RESEARCH_NON_CANDLE_QUOTE:
            quote_depth_files += 1
            continue
        if classification != RESEARCH_CANDLE or frame is None or symbol is None:
            raise RuntimeError(
                f"unexpected corpus classification path={parquet_path} "
                f"classification={classification}"
            )

        candle_files += 1
        dates.add(parquet_path.parent.parent.name)
        symbols.add(symbol)
        row_counts.append(len(frame))
        total_rows += len(frame)

    frozen_counts = {
        "candle_files": candle_files,
        "quote_depth_files": quote_depth_files,
        "appledouble_files": appledouble_files,
    }
    expected_counts = {
        "candle_files": EXPECTED_CANDLE_FILES,
        "quote_depth_files": EXPECTED_QUOTE_DEPTH_FILES,
        "appledouble_files": EXPECTED_APPLEDOUBLE_FILES,
    }
    if frozen_counts != expected_counts:
        raise RuntimeError(
            f"frozen corpus classification mismatch expected={expected_counts} "
            f"actual={frozen_counts}"
        )

    ordered_dates = sorted(dates)
    if not ordered_dates:
        raise RuntimeError("frozen corpus contains no valid candle dates")
    uniform_rows = row_counts[0] if len(set(row_counts)) == 1 else None
    base = project_root / "runtime" / "strategy_validation" / STRATEGY_ID
    base.mkdir(parents=True, exist_ok=True)
    audit = {
        "classification": "UPSTOX_CANDLE_FILES_VALID",
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "manifest_verified": True,
        "parquet_files_verified": len(expected),
        "underlying_parquet_files_classified": len(underlying),
        "candle_files_verified": candle_files,
        "quote_depth_files_verified": quote_depth_files,
        "appledouble_files_verified": appledouble_files,
        "underlying_symbol_days": candle_files,
        "underlying_rows": total_rows,
        "symbols": sorted(symbols),
        "first_date": ordered_dates[0],
        "last_date": ordered_dates[-1],
        "timestamp_order_contract": "NORMALIZED_AND_DUPLICATE_REJECTED",
    }
    catalog = {
        "source": "IMMUTABLE_PRIVATE_RELEASE",
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "date_range_found": ordered_dates,
        "trading_days_count": len(ordered_dates),
        "symbols_found": sorted(symbols),
        "rows_per_day": uniform_rows,
        "underlying_symbol_days": candle_files,
        "quote_depth_files": quote_depth_files,
        "appledouble_files": appledouble_files,
        "underlying_rows": total_rows,
    }
'''
    text = replace_once(text, old_block, new_block, label="frozen corpus authority")

    text = replace_once(
        text,
        '''            "tests/test_mean_reversion_ledger_accounting.py",
''',
        '''            "tests/test_mean_reversion_ledger_accounting.py",
            "tests/test_research_candle_contract.py",
            "tests/test_mean_reversion_corpus_directory_accounting.py",
''',
        label="focused merged regressions",
    )

    old_wfa = '''    frames: list[pd.DataFrame] = []
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for path in files:
        frame = pd.read_parquet(path)
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise RuntimeError(f"{path} missing columns {missing}")
        frames.append(frame[required].copy())
'''
    new_wfa = '''    frames: list[pd.DataFrame] = []
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for parquet_path in files:
        classification, frame, symbol = load_research_candle_parquet(parquet_path)
        if classification != RESEARCH_CANDLE or frame is None or symbol != "NIFTY":
            raise RuntimeError(
                f"unexpected NIFTY WFA input path={parquet_path} "
                f"classification={classification} symbol={symbol}"
            )
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise RuntimeError(f"{parquet_path} missing columns {missing}")
        frames.append(frame[required].copy())
'''
    text = replace_once(text, old_wfa, new_wfa, label="shared WFA candle loading")
    path.write_text(text, encoding="utf-8")

    review_path = Path("docs/agent_reviews/mean_reversion_postmerge_regeneration.md")
    review = review_path.read_text(encoding="utf-8")
    review = review.replace(
        "MEAN_REVERSION_POSTMERGE_RERUN_V1",
        "MEAN_REVERSION_POSTMERGE_RERUN_V3",
    )
    review = review.replace(
        "after PRs 689 and 690 repaired causal, accounting, audit, and fold-isolation defects.",
        "after PRs 689, 690, and 693 repaired causal, accounting, audit, fold-isolation, and mixed-corpus classification defects.",
    )
    review = review.replace(
        "merged commit `c6d1240ff506210be15f8647bad0ee677b4870a7`",
        "merged commit `a64ddee5f68921bffbac684e2ea06de8943b704a`",
    )
    review = review.replace(
        "- underlying candle inventory and input-authority artifacts;",
        "- exact 1,547 candle / 129 quote-depth / 1,676 AppleDouble classification census and input-authority artifacts;",
    )
    review_path.write_text(review, encoding="utf-8")

    Path("tools/prepare_mean_reversion_rerun_v3.py").unlink()


if __name__ == "__main__":
    main()
