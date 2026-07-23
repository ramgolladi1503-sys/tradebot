#!/usr/bin/env python3
"""Build an explicit point-in-time constituent-universe snapshot.

This does not download or infer historical membership. The caller must provide
an official constituent file and a defensible effective date.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from research.constituent_lead_lag.unweighted import validate_universe


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"unsupported constituent source: {path}")


def build_snapshot(
    source: pd.DataFrame,
    *,
    index_symbol: str,
    symbol_column: str,
    effective_from: str,
    source_name: str,
    source_sha256: str,
    snapshot_type: str,
) -> pd.DataFrame:
    if symbol_column not in source:
        raise ValueError(f"missing symbol column: {symbol_column}")
    symbols = (
        source[symbol_column]
        .dropna()
        .astype(str)
        .str.upper()
        .str.strip()
    )
    symbols = symbols[symbols != ""].drop_duplicates().sort_values()
    if len(symbols) < 5:
        raise ValueError("constituent snapshot contains fewer than five symbols")
    frame = pd.DataFrame({
        "index_symbol": index_symbol.upper(),
        "constituent_symbol": symbols,
        "effective_from": effective_from,
        "effective_to": None,
        "source_name": source_name,
        "source_sha256": source_sha256,
        "snapshot_type": snapshot_type,
        "historical_backfill_allowed": False,
    })
    return validate_universe(frame, minimum_constituent_count=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--index", choices=["NIFTY", "BANKNIFTY"], required=True)
    parser.add_argument("--symbol-column", default="Symbol")
    parser.add_argument("--effective-from", required=True)
    parser.add_argument("--source-name", default="OFFICIAL_NSE_CONSTITUENT_SNAPSHOT")
    parser.add_argument(
        "--snapshot-type",
        choices=[
            "CURRENT_OFFICIAL_SNAPSHOT",
            "POINT_IN_TIME_OFFICIAL_SNAPSHOT",
        ],
        default="CURRENT_OFFICIAL_SNAPSHOT",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = read_source(args.input)
    snapshot = build_snapshot(
        source,
        index_symbol=args.index,
        symbol_column=args.symbol_column,
        effective_from=args.effective_from,
        source_name=args.source_name,
        source_sha256=file_hash(args.input),
        snapshot_type=args.snapshot_type,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_csv(args.output, index=False)
    print(f"Wrote {len(snapshot)} constituents to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
