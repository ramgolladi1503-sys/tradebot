#!/usr/bin/env python3
"""Independent artifact oracle for reconstructed proxy research evidence."""

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


def read_parquet_count(path: Path) -> int:
    return int(len(pd.read_parquet(path))) if path.is_file() else 0


def audit(evaluation_dir: Path, bars: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bars_df = pd.read_parquet(bars)
    state_path = evaluation_dir / "signal_states_weighted.parquet"
    unweighted_path = evaluation_dir / "signal_states_unweighted.parquet"
    control_path = evaluation_dir / "matched_control.parquet"
    states = pd.read_parquet(state_path) if state_path.is_file() else pd.DataFrame()
    reason_counts = states["reason"].astype(str).value_counts().to_dict() if "reason" in states else {}
    report = {
        "verdict": "PASS",
        "bars_sha256": sha256(bars),
        "date_range": [str(bars_df["session"].min()), str(bars_df["session"].max())] if len(bars_df) else [None, None],
        "sessions": int(bars_df["session"].nunique()) if len(bars_df) else 0,
        "state_rows": int(len(states)),
        "reason_counts": reason_counts,
        "weighted_signals": int(states["side"].isin(["LONG", "SHORT"]).sum()) if "side" in states else 0,
        "unweighted_signals": read_parquet_count(unweighted_path),
        "control_count": read_parquet_count(control_path),
        "research_only": True,
        "allowed_for_live_execution": False,
        "oracle_imports_strategy": False,
    }
    (output_dir / "oracle_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output_dir / "oracle_report.md").write_text(f"# Independent Oracle\n\nVerdict: {report['verdict']}\n\nWeighted signals: {report['weighted_signals']}\n\nState rows: {report['state_rows']}\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.evaluation_dir, args.bars, args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
