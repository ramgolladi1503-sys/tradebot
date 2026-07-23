#!/usr/bin/env python3
"""Data-only audit of normalized constituent/index bars."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(bars: Path, output_dir: Path, decision_times: list[str]) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(bars)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    invalid = (
        (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df["high"] < df["low"])
    )
    dupes = int(df.duplicated(["symbol", "timestamp"]).sum())
    aligned = bool((df["timestamp"].dt.minute % 5 == 0).all())
    sessions = sorted(df["session"].astype(str).unique())
    nifty_sessions = sorted(df.loc[df["symbol"] == "NIFTY", "session"].astype(str).unique())
    session_coverage = df.groupby("session").agg(row_count=("timestamp", "size"), symbols=("symbol", "nunique")).reset_index()
    session_coverage.to_parquet(output_dir / "session_coverage.parquet", index=False)
    completed_sessions = int(len(nifty_sessions))
    theoretical_max = completed_sessions * len(decision_times)
    report = {
        "bars_path": str(bars),
        "bars_sha256": sha256(bars),
        "row_count": int(len(df)),
        "column_set": list(df.columns),
        "date_min": min(sessions) if sessions else None,
        "date_max": max(sessions) if sessions else None,
        "completed_session_count": completed_sessions,
        "partial_sessions": int(len(set(sessions) - set(nifty_sessions))),
        "unique_symbol_count": int(df["symbol"].nunique()),
        "nifty_rows": int((df["symbol"] == "NIFTY").sum()),
        "nifty_sessions": int(len(nifty_sessions)),
        "invalid_ohlc": int(invalid.sum()),
        "duplicates": dupes,
        "missing_index_sessions": sorted(set(sessions) - set(nifty_sessions)),
        "five_minute_alignment": aligned,
        "timezone": "UTC timestamp, Asia/Kolkata session",
        "decision_times": decision_times,
        "theoretical_max_state_rows": theoretical_max,
        "state_count_bound_check": "not_evaluated_in_bar_audit",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    (output_dir / "bars_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output_dir / "bars_audit.md").write_text(
        f"# Proxy Campaign Bars Audit\n\nRows: {report['row_count']}\n\nCompleted sessions: {completed_sessions}\n\nTheoretical max state rows: {theoretical_max}\n\nInvalid OHLC: {report['invalid_ohlc']}\n",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decision-times", nargs="+", default=["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:15"])
    args = parser.parse_args()
    print(json.dumps(audit(args.bars, args.output_dir, args.decision_times), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
