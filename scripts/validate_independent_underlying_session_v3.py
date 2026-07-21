#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


SAFETY_FLAGS = {"read_only": True, "is_order_action": False, "broker_api_called": False, "execution_eligibility": False, "allowed_for_live_execution": False}
REQUIRED_COLUMNS = {
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "source",
    "interval",
    "data_origin",
    "synthetic",
    "mock",
    "fallback",
    "provider",
    "source_endpoint_family",
    "fetch_timestamp_utc",
    "source_chunk_start",
    "source_chunk_end",
    "instrument_key_hash",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def validate_frame(df: pd.DataFrame) -> str:
    if not REQUIRED_COLUMNS.issubset(df.columns):
        return "PROVENANCE_FAILURE"
    ts = pd.to_datetime(df["timestamp"])
    if getattr(ts.dt, "tz", None) is None:
        return "PROVENANCE_FAILURE"
    if not ts.is_monotonic_increasing or ts.duplicated().any():
        return "DUPLICATE_ROWS"
    for col in ["open", "high", "low", "close"]:
        if not pd.to_numeric(df[col], errors="coerce").map(lambda x: pd.notna(x) and x > 0).all():
            return "NONFINITE_VALUES"
    if not ((df["high"] >= df[["open", "close", "low"]].max(axis=1)) & (df["low"] <= df[["open", "close", "high"]].min(axis=1))).all():
        return "INVALID_OHLC"
    if bool(df[["synthetic", "mock", "fallback"]].any(axis=None)):
        return "PROVENANCE_FAILURE"
    return "ELIGIBLE_SYMBOL_FILE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--output", default="research/independent_underlying_confirmation_v3/data_acquisition/session_validation_summary.json")
    args = parser.parse_args()
    records = []
    for raw in args.files:
        path = Path(raw)
        try:
            df = pd.read_parquet(path)
            verdict = validate_frame(df)
        except Exception as exc:
            verdict = f"SCHEMA_INCOMPATIBLE:{type(exc).__name__}"
        records.append({"path": str(path), "sha256": sha256_file(path) if path.exists() else None, "verdict": verdict})
    write_json(Path(args.output), {"records": records, "strategy_candidate_counts_calculated": False, "strategy_outcomes_calculated": False, "safety_flags": SAFETY_FLAGS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
