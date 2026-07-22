from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"guard failed for {label}: expected exactly one match")
    return text.replace(old, new)


def main() -> None:
    orchestrator = Path("scripts/run_mean_reversion_postmerge_regeneration.py")
    text = orchestrator.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''import numpy as np
import pandas as pd


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
''',
        '''import numpy as np
import pandas as pd

from core.research_backtest_integrity import (
    RESEARCH_CANDLE,
    RESEARCH_NON_CANDLE_QUOTE,
    load_research_candle_parquet,
)


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
EXPECTED_CANDLE_FILES = 1547
EXPECTED_QUOTE_DEPTH_FILES = 129
''',
        label="orchestrator imports and frozen counts",
    )
    text = replace_once(
        text,
        '''    dates: set[str] = set()
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
''',
        '''    dates: set[str] = set()
    symbols: set[str] = set()
    row_counts: list[int] = []
    total_rows = 0
    candle_files = 0
    quote_depth_files = 0
    for path in underlying:
        classification, frame, symbol = load_research_candle_parquet(path)
        if classification == RESEARCH_NON_CANDLE_QUOTE:
            quote_depth_files += 1
            continue
        if classification != RESEARCH_CANDLE or frame is None or symbol is None:
            raise RuntimeError(f"unexpected corpus classification for {path}: {classification}")

        date_key = path.parent.parent.name
        candle_files += 1
        dates.add(date_key)
        symbols.add(symbol)
        row_counts.append(len(frame))
        total_rows += len(frame)

    if candle_files != EXPECTED_CANDLE_FILES:
        raise RuntimeError(
            f"frozen candle count mismatch expected={EXPECTED_CANDLE_FILES} actual={candle_files}"
        )
    if quote_depth_files != EXPECTED_QUOTE_DEPTH_FILES:
        raise RuntimeError(
            "frozen quote/depth count mismatch "
            f"expected={EXPECTED_QUOTE_DEPTH_FILES} actual={quote_depth_files}"
        )

    ordered_dates = sorted(dates)
''',
        label="corpus classification loop",
    )
    text = replace_once(
        text,
        '''        "parquet_files_verified": len(expected),
        "underlying_symbol_days": len(underlying),
        "underlying_rows": total_rows,
        "symbols": sorted(symbols),
        "first_date": ordered_dates[0],
        "last_date": ordered_dates[-1],
        "source_files_not_monotonic": unsorted_files,
''',
        '''        "parquet_files_verified": len(expected),
        "underlying_parquet_files_classified": len(underlying),
        "candle_files_verified": candle_files,
        "quote_depth_files_verified": quote_depth_files,
        "underlying_symbol_days": candle_files,
        "underlying_rows": total_rows,
        "symbols": sorted(symbols),
        "first_date": ordered_dates[0],
        "last_date": ordered_dates[-1],
        "timestamp_order_contract": "NORMALIZED_AND_DUPLICATE_REJECTED",
''',
        label="input authority evidence",
    )
    text = replace_once(
        text,
        '''        "underlying_symbol_days": len(underlying),
        "underlying_rows": total_rows,
''',
        '''        "underlying_symbol_days": candle_files,
        "quote_depth_files": quote_depth_files,
        "underlying_rows": total_rows,
''',
        label="historical catalog counts",
    )
    text = replace_once(
        text,
        '''    frames: list[pd.DataFrame] = []
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for path in files:
        frame = pd.read_parquet(path)
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise RuntimeError(f"{path} missing columns {missing}")
        frames.append(frame[required].copy())
''',
        '''    frames: list[pd.DataFrame] = []
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for path in files:
        classification, frame, symbol = load_research_candle_parquet(path)
        if classification != RESEARCH_CANDLE or frame is None or symbol != "NIFTY":
            raise RuntimeError(
                f"unexpected NIFTY WFA input classification path={path} "
                f"classification={classification} symbol={symbol}"
            )
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise RuntimeError(f"{path} missing columns {missing}")
        frames.append(frame[required].copy())
''',
        label="shared WFA input loading",
    )
    orchestrator.write_text(text, encoding="utf-8")

    workflow = Path(".github/workflows/mean_reversion_postmerge_regeneration.yml")
    workflow_text = workflow.read_text(encoding="utf-8")
    workflow_text = workflow_text.replace(
        "research/postmerge-mean-reversion-rerun-v1",
        "research/postmerge-mean-reversion-rerun-v2",
    )
    workflow_text = replace_once(
        workflow_text,
        '''          for sidecar in sidecars:
              sidecar.unlink()
          target = Path(os.environ['EVIDENCE_DIR']) / 'appledouble_cleanup.json'
''',
        '''          if len(records) != 1676:
              raise RuntimeError(
                  f"AppleDouble sidecar count mismatch expected=1676 actual={len(records)}"
              )
          for sidecar in sidecars:
              sidecar.unlink()
          target = Path(os.environ['EVIDENCE_DIR']) / 'appledouble_cleanup.json'
''',
        label="frozen AppleDouble count gate",
    )
    workflow.write_text(workflow_text, encoding="utf-8")

    review = Path("docs/agent_reviews/mean_reversion_postmerge_regeneration.md")
    review_text = review.read_text(encoding="utf-8")
    review_text = review_text.replace(
        "merged commit `c6d1240ff506210be15f8647bad0ee677b4870a7`",
        "provisional production-fix head `2f0e1f8837bb8a6ada04cbdef3bc189096c25652`",
    )
    review_text = review_text.replace(
        "This branch does not need to merge before the evidence workflow runs.",
        "This branch is a dependent provisional evidence run and must not merge before production PR #693.",
    )
    review.write_text(review_text, encoding="utf-8")

    Path(".github/workflows/prepare_mean_reversion_rerun_v2.yml").unlink()
    Path("tools/prepare_mean_reversion_rerun_v2.py").unlink()


if __name__ == "__main__":
    main()
