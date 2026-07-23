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
    grid_rows = []
    completed = []
    for session in sessions:
        expected = pd.date_range(
            pd.Timestamp(f"{session} 09:15", tz="Asia/Kolkata").tz_convert("UTC"),
            pd.Timestamp(f"{session} 15:25", tz="Asia/Kolkata").tz_convert("UTC"),
            freq="5min",
        )
        nifty = df[(df["session"].astype(str) == session) & (df["symbol"] == "NIFTY")].sort_values("timestamp")
        have = set(pd.to_datetime(nifty["timestamp"], utc=True))
        missing = [ts.isoformat() for ts in expected if ts not in have]
        cutoffs = {
            t: pd.Timestamp(f"{session} {t}", tz="Asia/Kolkata").tz_convert("UTC") in have
            for t in decision_times
        }
        is_completed = len(missing) == 0 and all(cutoffs.values())
        reason = None
        if nifty.empty:
            reason = "missing_nifty_session"
        elif missing:
            reason = "missing_regular_grid_timestamps"
        elif not all(cutoffs.values()):
            reason = "missing_decision_cutoff"
        if is_completed:
            completed.append(session)
        grid_rows.append({
            "session": session,
            "nifty_first_timestamp": nifty["timestamp"].min().isoformat() if len(nifty) else None,
            "nifty_last_timestamp": nifty["timestamp"].max().isoformat() if len(nifty) else None,
            "nifty_bar_count": int(len(nifty)),
            "expected_bar_count": int(len(expected)),
            "missing_timestamps": missing,
            "decision_cutoffs_available": cutoffs,
            "completed": bool(is_completed),
            "rejection_reason": reason,
        })
    session_grid = pd.DataFrame(grid_rows)
    session_grid.to_parquet(output_dir / "session_grid.parquet", index=False)
    session_coverage = df.groupby("session").agg(row_count=("timestamp", "size"), symbols=("symbol", "nunique")).reset_index()
    session_coverage.to_parquet(output_dir / "session_coverage.parquet", index=False)
    completed_sessions = int(len(completed))
    theoretical_max = completed_sessions * len(decision_times)
    report = {
        "bars_path": str(bars),
        "bars_sha256": sha256(bars),
        "row_count": int(len(df)),
        "column_set": list(df.columns),
        "date_min": min(sessions) if sessions else None,
        "date_max": max(sessions) if sessions else None,
        "completed_session_count": completed_sessions,
        "completed_sessions": completed,
        "partial_sessions": int((~session_grid["completed"]).sum()) if len(session_grid) else 0,
        "rejected_partial_sessions": session_grid.loc[~session_grid["completed"], "session"].astype(str).tolist() if len(session_grid) else [],
        "unique_symbol_count": int(df["symbol"].nunique()),
        "nifty_rows": int((df["symbol"] == "NIFTY").sum()),
        "nifty_sessions": int(df.loc[df["symbol"] == "NIFTY", "session"].nunique()),
        "invalid_ohlc": int(invalid.sum()),
        "duplicates": dupes,
        "missing_index_sessions": session_grid.loc[session_grid["rejection_reason"].eq("missing_nifty_session"), "session"].astype(str).tolist() if len(session_grid) else [],
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
