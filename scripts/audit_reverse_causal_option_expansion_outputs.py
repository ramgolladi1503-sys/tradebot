#!/usr/bin/env python3
"""Independent artifact audit for reverse-causal option expansion outputs.

This script intentionally does not import the discovery runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/research/reverse_causal_option_expansion_v1"))
    args = parser.parse_args()
    out = args.output_dir
    package = json.loads((out / "research_package.json").read_text())
    events = pd.read_parquet(out / "event_universe_5m.parquet")
    matched = pd.read_parquet(out / "matched_controls.parquet")
    near = pd.read_parquet(out / "near_miss_controls.parquet")
    violations = []
    if package["non_action_flags"]["broker_api_called"] is not False:
        violations.append("BROKER_FLAG_NOT_FALSE")
    if not (events["entry_price_next_open"].notna().all()):
        violations.append("MISSING_NEXT_OBSERVATION_ENTRY")
    clustered = events.dropna(subset=["move_cluster_id"]).copy()
    if len(clustered):
        clustered["timestamp"] = pd.to_datetime(clustered["timestamp"], errors="coerce")
        spans = clustered.groupby("move_cluster_id")["timestamp"].agg(["min", "max"])
        too_wide = (spans["max"] - spans["min"]).dt.total_seconds() > 30 * 60
        if bool(too_wide.any()):
            violations.append("CLUSTER_SPAN_EXCEEDS_COOLDOWN")
    if len(matched) and matched["control_type"].ne("matched_ordinary").any():
        violations.append("MATCHED_CONTROL_TYPE_INVALID")
    if len(near) and near["control_type"].ne("near_miss").any():
        violations.append("NEAR_MISS_TYPE_INVALID")
    audit = {
        "verdict": "PASS" if not violations else "FAIL",
        "violations": violations,
        "event_rows": int(len(events)),
        "matched_control_rows": int(len(matched)),
        "near_miss_rows": int(len(near)),
        "research_package_sha256": sha256_file(out / "research_package.json"),
    }
    deep_path = out / "deep_precursor_discrimination.csv"
    coverage_path = out / "temporal_coverage.json"
    if deep_path.exists() and coverage_path.exists():
        deep = pd.read_csv(deep_path)
        coverage = json.loads(coverage_path.read_text())
        if len(deep) != 10:
            violations.append("DEEP_FAMILY_COUNT_NOT_10")
        if int(coverage["distinct_sessions"]) <= 1:
            violations.append("TEMPORAL_COVERAGE_NOT_MULTI_SESSION")
        if deep["accepted_for_freeze"].any():
            violations.append("AUDIT_REVIEW_REQUIRED_FOR_FROZEN_PRECURSOR")
        audit.update(
            {
                "deep_families": int(len(deep)),
                "temporal_sessions": int(coverage["distinct_sessions"]),
                "resolved_ticks_sessions": int(coverage["resolved_ticks_sessions"]),
            }
        )
        audit["verdict"] = "PASS" if not violations else "FAIL"
        audit["violations"] = violations
    (out / "independent_audit_report.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, sort_keys=True))
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
