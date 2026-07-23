#!/usr/bin/env python3
"""Normalize accepted Upstox V3 five-minute candle files.

Inputs are manifest rows, not filename guesses. The command is offline and
research-only; it never calls Upstox or any broker API.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = [
    "timestamp",
    "session",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "provider",
    "instrument_key",
    "source_file_sha256",
    "data_origin",
    "synthetic",
    "mock",
    "fallback",
]


def load_json_gz(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


def parse_candles(row: dict[str, Any], start: pd.Timestamp, end: pd.Timestamp) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    path = Path(row["stored_path"])
    payload = load_json_gz(path)
    candles = payload.get("data", {}).get("candles", [])
    accepted: list[dict[str, Any]] = []
    invalid_ohlc: list[dict[str, Any]] = []
    counts = {"raw": 0, "malformed": 0, "out_of_window": 0, "invalid_ohlc_quarantined": 0}
    for candle in candles:
        counts["raw"] += 1
        if not isinstance(candle, list) or len(candle) != 7:
            counts["malformed"] += 1
            continue
        ts_raw, open_, high, low, close, volume, oi = candle
        ts = pd.Timestamp(ts_raw)
        if ts.tzinfo is None:
            counts["malformed"] += 1
            continue
        local = ts.tz_convert("Asia/Kolkata")
        session = local.date().isoformat()
        if pd.Timestamp(session) < start or pd.Timestamp(session) > end:
            counts["out_of_window"] += 1
            continue
        if local.minute % 5 != 0:
            counts["malformed"] += 1
            continue
        try:
            o = float(open_)
            h = float(high)
            l = float(low)
            c = float(close)
        except (TypeError, ValueError):
            counts["invalid_ohlc_quarantined"] += 1
            invalid_ohlc.append({"source_file": str(path), "source_file_sha256": row["sha256"], "symbol": row["symbol"], "timestamp": str(ts_raw), "open": open_, "high": high, "low": low, "close": close})
            continue
        invalid = o <= 0 or h <= 0 or l <= 0 or c <= 0 or h < max(o, c) or l > min(o, c) or h < l
        if invalid:
            counts["invalid_ohlc_quarantined"] += 1
            invalid_ohlc.append({"source_file": str(path), "source_file_sha256": row["sha256"], "symbol": row["symbol"], "timestamp": str(ts_raw), "open": o, "high": h, "low": l, "close": c})
            continue
        accepted.append({
            "timestamp": ts.tz_convert("UTC"),
            "session": session,
            "symbol": str(row["symbol"]).upper(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": float(volume or 0),
            "oi": float(oi or 0),
            "provider": "Upstox V3",
            "instrument_key": row.get("instrument_key") or "",
            "source_file_sha256": row["sha256"],
            "data_origin": "upstox_v3_manifest",
            "synthetic": False,
            "mock": False,
            "fallback": False,
        })
    return accepted, invalid_ohlc, counts


def normalize(accepted_manifest: Path, ticker_resolution: Path, start_date: str, end_date: str, output_root: Path) -> dict[str, Any]:
    rows = json.loads(accepted_manifest.read_text())
    resolution = pd.read_csv(ticker_resolution) if ticker_resolution.is_file() else pd.DataFrame()
    resolved_symbols = set(resolution.get("proxy_ticker", pd.Series(dtype=str)).dropna().astype(str).str.upper())
    key_by_symbol = dict(zip(resolution.get("proxy_ticker", pd.Series(dtype=str)).astype(str).str.upper(), resolution.get("instrument_key", pd.Series(dtype=str)).astype(str)))
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    output_root.mkdir(parents=True, exist_ok=True)
    reports = output_root.parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    conservation = {"raw_rows": 0, "normalized_accepted": 0, "out_of_window": 0, "malformed": 0, "invalid_ohlc_quarantined": 0, "identical_duplicates_collapsed": 0, "conflicting_duplicates_rejected": 0}
    for row in rows:
        if resolved_symbols and str(row.get("symbol") or "").upper() not in resolved_symbols:
            conservation["malformed"] += int(row.get("candle_count") or 0)
            continue
        if not row.get("instrument_key") and str(row.get("symbol") or "").upper() in key_by_symbol:
            row = dict(row)
            row["instrument_key"] = key_by_symbol[str(row.get("symbol")).upper()]
        accepted, invalid, counts = parse_candles(row, start, end)
        all_rows.extend(accepted)
        invalid_rows.extend(invalid)
        for key, value in counts.items():
            if key == "raw":
                conservation["raw_rows"] += value
            else:
                conservation[key] += value
    frame = pd.DataFrame(all_rows, columns=REQUIRED_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["symbol", "timestamp", "source_file_sha256"]).reset_index(drop=True)
        identical = frame.duplicated(REQUIRED_COLUMNS[:-3], keep="first")
        conservation["identical_duplicates_collapsed"] = int(identical.sum())
        frame = frame.loc[~identical].copy()
        conflict = frame.duplicated(["symbol", "timestamp"], keep=False)
        conflict_rows = frame.loc[conflict].copy()
        conservation["conflicting_duplicates_rejected"] = int(len(conflict_rows))
        frame = frame.loc[~conflict].copy()
    else:
        conflict_rows = pd.DataFrame()
    conservation["normalized_accepted"] = int(len(frame))
    conservation["row_conservation_passed"] = conservation["raw_rows"] == sum(conservation[k] for k in ["normalized_accepted", "out_of_window", "malformed", "invalid_ohlc_quarantined", "identical_duplicates_collapsed", "conflicting_duplicates_rejected"])
    bars_path = output_root / "constituent_index_5m.parquet"
    frame.to_parquet(bars_path, index=False)
    pd.DataFrame(invalid_rows).to_parquet(reports / "invalid_ohlc_rows.parquet", index=False)
    conflict_rows.to_parquet(output_root / "duplicate_dispositions.parquet", index=False)
    sessions = frame.groupby("session").agg(row_count=("timestamp", "size"), symbols=("symbol", "nunique")).reset_index() if not frame.empty else pd.DataFrame(columns=["session", "row_count", "symbols"])
    sessions.to_parquet(output_root / "session_inventory.parquet", index=False)
    symbols = frame.groupby("symbol").agg(row_count=("timestamp", "size"), session_count=("session", "nunique"), instrument_key=("instrument_key", "first")).reset_index() if not frame.empty else pd.DataFrame(columns=["symbol", "row_count", "session_count", "instrument_key"])
    symbols.to_csv(output_root / "symbol_inventory.csv", index=False)
    (output_root / "row_conservation.json").write_text(json.dumps(conservation, indent=2, sort_keys=True) + "\n")
    report = {"output_path": str(bars_path), "columns": REQUIRED_COLUMNS, "start_date": start_date, "end_date": end_date, **conservation}
    (output_root / "normalization_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    parser.add_argument("--ticker-resolution", type=Path, required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(normalize(args.accepted_manifest, args.ticker_resolution, args.start_date, args.end_date, args.output_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
