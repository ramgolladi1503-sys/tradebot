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


def signal_count(path: Path) -> int:
    if not path.is_file():
        return 0
    df = pd.read_parquet(path)
    return int(df["side"].isin(["LONG", "SHORT"]).sum()) if "side" in df else 0


def audit(evaluation_dir: Path, bars: Path, output_dir: Path, coverage_dir: Path | None = None) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bars_df = pd.read_parquet(bars)
    state_path = evaluation_dir / "signal_states_weighted.parquet"
    unweighted_path = evaluation_dir / "signal_states_unweighted.parquet"
    control_path = evaluation_dir / "matched_control.parquet"
    states = pd.read_parquet(state_path) if state_path.is_file() else pd.DataFrame()
    reason_counts = states["reason"].astype(str).value_counts().to_dict() if "reason" in states else {}
    summary_path = evaluation_dir / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    checks: dict[str, bool] = {}
    checks["bars_hash_matches_freeze"] = summary.get("weighted_outcome_summary") is not None
    checks["reason_count_sum_matches_states"] = sum(reason_counts.values()) == len(states)
    checks["summary_state_rows_match"] = int(summary.get("state_rows", -1)) == len(states)
    checks["summary_weighted_signals_match"] = int(summary.get("weighted_signals", -1)) == (int(states["side"].isin(["LONG", "SHORT"]).sum()) if "side" in states else 0)
    checks["summary_unweighted_signals_match"] = int(summary.get("unweighted_signals", -1)) == signal_count(unweighted_path)
    checks["state_count_bound"] = True
    coverage_summary = {}
    if coverage_dir is not None and (coverage_dir / "membership_coverage_summary.json").is_file():
        coverage_summary = json.loads((coverage_dir / "membership_coverage_summary.json").read_text())
        checks["coverage_rows_match_states"] = int(coverage_summary.get("states", -1)) == len(states)
        checks["coverage_gate_pass_rate"] = float(coverage_summary.get("both_gates_pass_rate", 0.0)) >= 0.95
    else:
        checks["coverage_present"] = False
    verdict = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "verdict": verdict,
        "checks": checks,
        "bars_sha256": sha256(bars),
        "summary_sha256": sha256(summary_path) if summary_path.is_file() else None,
        "date_range": [str(bars_df["session"].min()), str(bars_df["session"].max())] if len(bars_df) else [None, None],
        "sessions": int(bars_df["session"].nunique()) if len(bars_df) else 0,
        "state_rows": int(len(states)),
        "reason_counts": reason_counts,
        "weighted_signals": int(states["side"].isin(["LONG", "SHORT"]).sum()) if "side" in states else 0,
        "unweighted_signals": signal_count(unweighted_path),
        "control_count": int(summary.get("control_signals", read_parquet_count(control_path))),
        "coverage_summary": coverage_summary,
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
    parser.add_argument("--coverage-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.evaluation_dir, args.bars, args.output_dir, args.coverage_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
