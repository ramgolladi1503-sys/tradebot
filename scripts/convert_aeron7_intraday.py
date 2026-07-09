#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


RAW_COLUMNS_8 = ["symbol", "date", "time", "open", "high", "low", "close", "volume"]
RAW_COLUMNS_9 = [
    "symbol",
    "date",
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
]
CANONICAL_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


def _normalize_csv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    needed = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in frame.columns:
            frame[col] = None
    if "symbol" not in frame.columns:
        frame["symbol"] = "UNKNOWN"

    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    frame = frame[CANONICAL_COLUMNS].copy()
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


def _read_intraday_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path)
        if raw.empty:
            return pd.DataFrame(columns=CANONICAL_COLUMNS)
        return _normalize_csv_frame(raw)

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


def convert_aeron7_intraday(
    *, source_root: str | Path, output_dir: str | Path, symbols: list[str] | None = None,
    start_date: str | None = None, end_date: str | None = None
) -> dict[str, object]:
    src_root = Path(source_root).expanduser()
    out_root = Path(output_dir).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)

    wanted = {s.strip().upper() for s in (symbols or []) if str(s).strip()}
    
    schema_version = "v2"
    cache_dict = {
        "source_root": str(src_root),
        "symbols": sorted(list(wanted)),
        "start_date": start_date or "",
        "end_date": end_date or "",
        "schema_version": schema_version
    }
    
    dict_str = json.dumps(cache_dict, sort_keys=True)
    cache_hash = hashlib.sha256(dict_str.encode("utf-8")).hexdigest()
    
    hash_dir = out_root / cache_hash
    manifest_path = hash_dir / "manifest.json"
    
    if manifest_path.exists():
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            match = all(manifest.get(k) == v for k, v in cache_dict.items())
            if match:
                written_files = manifest.get("written_files", [])
                if all(Path(p).exists() for p in written_files):
                    return {
                        "source_root": str(src_root),
                        "output_dir": str(hash_dir),
                        "symbols": sorted(list(wanted)),
                        "written_files": written_files,
                        "skipped_files": [],
                        "rows_written": manifest.get("total_rows_converted", 0),
                        "cache_hit": True
                    }
        except Exception:
            pass # Ignore and regenerate
            
    hash_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src_root.rglob("*.txt")) + sorted(src_root.rglob("*.csv"))
    written: list[str] = []
    skipped: list[str] = []

    grouped: dict[str, list[pd.DataFrame]] = {}
    for path in files:
        symbol = path.stem.replace("_intraday", "").strip().upper()
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
            
        if start_date or end_date:
            date_strs = frame["timestamp"].dt.strftime("%Y%m%d")
            mask = pd.Series(True, index=frame.index)
            if start_date:
                mask &= date_strs >= start_date
            if end_date:
                mask &= date_strs <= end_date
            frame = frame.loc[mask].copy()
                
        if frame.empty:
            skipped.append(str(path))
            continue
            
        grouped.setdefault(symbol, []).append(frame)

    total_rows = 0
    for symbol, frames in grouped.items():
        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        clean_symbol = symbol.replace(" ", "_")
        out_path = hash_dir / f"{clean_symbol}_intraday.csv"
        merged.to_csv(out_path, index=False)
        written.append(str(out_path))
        total_rows += len(merged)

    manifest_data = dict(cache_dict)
    manifest_data["written_files"] = written
    manifest_data["total_rows_converted"] = total_rows
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)

    return {
        "source_root": str(src_root),
        "output_dir": str(hash_dir),
        "symbols": sorted(grouped.keys()),
        "written_files": written,
        "skipped_files": skipped,
        "rows_written": total_rows,
        "cache_hit": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Aeron7 intraday text files into canonical OHLCV CSVs."
    )
    parser.add_argument(
        "--source-root", required=True, help="Root of the cloned Aeron7 dataset."
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory to write canonical CSVs."
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Optional comma-separated symbol filter, e.g. NIFTY_F1,BANKNIFTY",
    )
    parser.add_argument("--start-date", help="Optional start date YYYYMMDD")
    parser.add_argument("--end-date", help="Optional end date YYYYMMDD")
    args = parser.parse_args(argv)

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    report = convert_aeron7_intraday(
        source_root=args.source_root, output_dir=args.output_dir, symbols=symbols,
        start_date=args.start_date, end_date=args.end_date
    )
    print(
        f"converted_files={len(report['written_files'])} rows_written={report['rows_written']}"
    )
    for path in report["written_files"]:
        print(path)
    if report["skipped_files"]:
        print(f"skipped_files={len(report['skipped_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
