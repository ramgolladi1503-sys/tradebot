#!/usr/bin/env python3
"""Refresh the current NIFTY 50 constituent reference manifest.

This is an explicit operator command, not a runtime downloader. It accepts either a
local official CSV or downloads the configured official constituent CSV, validates
exactly 50 unique EQ symbols, records the raw-source SHA-256, and writes atomically.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

OFFICIAL_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "market_event_graph_nifty50_constituents_20260605.json"
)


def parse_constituent_csv(raw: bytes) -> list[str]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("constituent_csv_header_missing")
    normalized = {str(name).strip().lower(): name for name in reader.fieldnames}
    symbol_column = normalized.get("symbol")
    series_column = normalized.get("series")
    if symbol_column is None:
        raise ValueError("constituent_csv_symbol_column_missing")

    symbols: list[str] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        if series_column is not None:
            series = str(row.get(series_column) or "").strip().upper()
            if series and series != "EQ":
                continue
        symbol = str(row.get(symbol_column) or "").strip().upper()
        if symbol:
            symbols.append(symbol)

    unique = sorted(set(symbols))
    if len(symbols) != 50 or len(unique) != 50:
        raise ValueError(
            f"constituent_csv_requires_exactly_50_unique_eq_symbols:rows={len(symbols)}:unique={len(unique)}"
        )
    return unique


def build_manifest(
    raw: bytes,
    *,
    effective_from: str,
    retrieved_on: str,
    source_url: str,
) -> dict[str, Any]:
    symbols = parse_constituent_csv(raw)
    return {
        "schema_version": 1,
        "index_symbol": "NIFTY",
        "index_tradingsymbol": "NIFTY 50",
        "exchange": "NSE",
        "instrument_type": "EQ",
        "effective_from": effective_from,
        "retrieved_on": retrieved_on,
        "source_name": "NIFTY_INDICES_CURRENT_CONSTITUENT_LIST",
        "source_url": source_url,
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest_status": "CURRENT_REFERENCE_SNAPSHOT_REQUIRES_PERIODIC_OFFICIAL_REFRESH",
        "historical_backfill_allowed": False,
        "constituents": symbols,
    }


def write_manifest_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _read_source(input_path: Path | None, source_url: str) -> bytes:
    if input_path is not None:
        return input_path.read_bytes()
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "TradeBot-Market-Event-Graph-Manifest-Refresh/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30.0) as response:  # nosec B310 - fixed HTTPS operator URL
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--source-url", default=OFFICIAL_URL)
    parser.add_argument("--effective-from", required=True)
    parser.add_argument("--retrieved-on", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    raw = _read_source(args.input, args.source_url)
    manifest = build_manifest(
        raw,
        effective_from=args.effective_from,
        retrieved_on=args.retrieved_on,
        source_url=args.source_url,
    )
    target = write_manifest_atomic(args.output, manifest)
    print(
        json.dumps(
            {
                "status": "WROTE_CURRENT_REFERENCE_MANIFEST",
                "output": str(target),
                "constituent_count": 50,
                "source_file_sha256": manifest["source_file_sha256"],
                "historical_backfill_allowed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
