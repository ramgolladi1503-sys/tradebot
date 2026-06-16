#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


RAW_COLUMNS_8 = ["symbol", "date", "time", "open", "high", "low", "close", "volume"]
RAW_COLUMNS_9 = ["symbol", "date", "time", "open", "high", "low", "close", "volume", "oi"]
CANONICAL_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


def _read_intraday_file(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, header=None)
    if raw.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    if raw.shape[1] >= 9:
        raw = raw.iloc[:, :9]
        raw.columns = RAW_COLUMNS_9
    elif raw.shape[1] == 8:
        raw.columns = RAW_COLUMNS_8
    else:
        raise ValueError(f"unsupported_column_count:{path}:{raw.shape[1]}")

    frame = raw.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str.strip()
    frame["time"] = frame["time"].astype(str).str.strip()
    frame["timestamp"] = pd.to_datetime(
        frame["date"] + " " + frame["time"],
        errors="coerce",
        format=None,
    )
    frame = frame.dropna(subset=["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    frame = frame[CANONICAL_COLUMNS].copy()
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


def convert_aeron7_intraday(*, source_root: str | Path, output_dir: str | Path, symbols: list[str] | None = None) -> dict[str, object]:
    src_root = Path(source_root).expanduser()
    out_root = Path(output_dir).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)

    wanted = {s.strip().upper() for s in (symbols or []) if str(s).strip()}
    files = sorted(src_root.rglob("*.txt"))
    written: list[str] = []
    skipped: list[str] = []

    grouped: dict[str, list[pd.DataFrame]] = {}
    for path in files:
        symbol = path.stem.strip().upper()
        if wanted and symbol not in wanted:
            continue
        try:
            frame = _read_intraday_file(path)
        except Exception:
            skipped.append(str(path))
            continue
        if frame.empty:
            skipped.append(str(path))
            continue
        grouped.setdefault(symbol, []).append(frame)

    total_rows = 0
    for symbol, frames in grouped.items():
        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        out_path = out_root / f"{symbol}_intraday.csv"
        merged.to_csv(out_path, index=False)
        written.append(str(out_path))
        total_rows += len(merged)

    return {
        "source_root": str(src_root),
        "output_dir": str(out_root),
        "symbols": sorted(grouped.keys()),
        "written_files": written,
        "skipped_files": skipped,
        "rows_written": total_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Aeron7 intraday text files into canonical OHLCV CSVs.")
    parser.add_argument("--source-root", required=True, help="Root of the cloned Aeron7 dataset.")
    parser.add_argument("--output-dir", required=True, help="Directory to write canonical CSVs.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol filter, e.g. NIFTY_F1,BANKNIFTY")
    args = parser.parse_args(argv)

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    report = convert_aeron7_intraday(source_root=args.source_root, output_dir=args.output_dir, symbols=symbols)
    print(f"converted_files={len(report['written_files'])} rows_written={report['rows_written']}")
    for path in report["written_files"]:
        print(path)
    if report["skipped_files"]:
        print(f"skipped_files={len(report['skipped_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
