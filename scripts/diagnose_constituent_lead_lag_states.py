#!/usr/bin/env python3
"""Summarize persisted state rejections and gate distributions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


PREDICATES = {
    "abs_z_below_2": lambda df: df["lead_gap_z"].abs() < 2,
    "basket_5m_sign_failed": lambda df: df["basket_return_5m_bps"] == 0,
    "basket_10m_sign_failed": lambda df: df["basket_return_10m_bps"] == 0,
    "participation_below_0_70": lambda df: df["participation"] < 0.70,
    "breadth_abs_below_0_40": lambda df: df.get("weighted_breadth", df.get("breadth")).abs() < 0.40,
}


def diagnose(states_path: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(states_path)
    reason_counts = df["reason"].astype(str).value_counts().to_dict() if "reason" in df else {}
    failures = {name: int(fn(df).sum()) for name, fn in PREDICATES.items() if len(df)}
    metrics = {}
    for col in ["lead_gap_z", "participation", "weighted_breadth", "breadth", "dispersion_percentile", "catch_up_ratio", "range_consumed", "weight_coverage", "constituent_coverage"]:
        if col in df:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            metrics[col] = {"count": int(len(s)), "min": float(s.min()) if len(s) else None, "median": float(s.median()) if len(s) else None, "max": float(s.max()) if len(s) else None}
    (output_dir / "state_reason_counts.json").write_text(json.dumps(reason_counts, indent=2, sort_keys=True) + "\n")
    (output_dir / "state_gate_failures.json").write_text(json.dumps(failures, indent=2, sort_keys=True) + "\n")
    (output_dir / "state_metric_distributions.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    df.to_parquet(output_dir / "state_diagnostics.parquet", index=False)
    return {"state_rows": int(len(df)), "reason_counts": reason_counts, "gate_failures": failures, "metric_distributions": metrics}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.states, args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
