#!/usr/bin/env python3
"""Conditional precursor discrimination V2.

Stage 0/1 runner:
- verifies the PR #723 consolidation manifest against preserved files;
- rejects unresolved Git LFS pointers;
- validates parquet readability;
- reproduces the prior campaign's published counts and family rates;
- writes deterministic research artifacts.

This script is research-only and performs no broker or order actions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import pandas as pd

CORPUS_REL = Path("research/local_evidence_consolidation_v1")
PRIOR_REL = CORPUS_REL / "worktrees/reverse-causal-option-expansion-v1/runtime_research/reverse_causal_option_expansion_v1"
OUT_REL = Path("runtime/research/conditional_precursor_discrimination_v2")
RESEARCH_REL = Path("research/conditional_precursor_discrimination_v2")

REQUIRED = [
    "event_universe_5m.parquet",
    "matched_controls.parquet",
    "near_miss_controls.parquet",
    "deep_precursor_discrimination.csv",
    "deep_sequence_summary.json",
    "research_package.json",
    "temporal_coverage.json",
    "final_decision_report.md",
    "independent_audit_report.json",
]

EXPECTED_SUMMARY = {
    "accepted_precursors": 0,
    "definitions_tested": 10,
    "event_clusters": 11261,
    "event_sessions": 385,
    "families_tested": 10,
    "holdout_status": "NOT_OPENED_NO_FROZEN_MECHANISM",
    "principal_verdict": "NO_DISCRIMINATIVE_PRECURSOR_IN_TESTED_FAMILIES",
}

@dataclass(frozen=True)
class FileAudit:
    path: str
    exists: bool
    bytes: int | None
    sha256: str | None
    manifest_sha256: str | None
    manifest_bytes: int | None
    hash_match: bool | None
    size_match: bool | None
    lfs_pointer: bool | None
    readable: bool | None
    rows: int | None
    columns: list[str] | None
    error: str | None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    if path.stat().st_size > 2048:
        return False
    head = path.read_bytes()[:256]
    return b"version https://git-lfs.github.com/spec/v1" in head


def load_manifest(root: Path) -> dict[str, dict[str, Any]]:
    manifest_path = root / CORPUS_REL / "CONSOLIDATION_MANIFEST.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("file_manifest", []):
        result[item["path"]] = item
    return result


def audit_file(root: Path, path: Path, manifest: dict[str, dict[str, Any]]) -> FileAudit:
    rel_to_corpus = path.relative_to(root / CORPUS_REL).as_posix()
    item = manifest.get(rel_to_corpus)
    if not path.exists():
        return FileAudit(str(path), False, None, None, item.get("sha256") if item else None,
                         item.get("bytes") if item else None, None, None, None, False, None, None,
                         "missing")
    size = path.stat().st_size
    pointer = is_lfs_pointer(path)
    digest = sha256(path)
    readable = True
    rows = None
    columns = None
    error = None
    try:
        if path.suffix == ".parquet" and not pointer:
            frame = pd.read_parquet(path)
            rows = len(frame)
            columns = [str(c) for c in frame.columns]
        elif path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".csv":
            frame = pd.read_csv(path)
            rows = len(frame)
            columns = [str(c) for c in frame.columns]
        else:
            path.read_text(encoding="utf-8")
    except Exception as exc:  # fail-closed evidence audit
        readable = False
        error = f"{type(exc).__name__}: {exc}"
    return FileAudit(
        str(path), True, size, digest,
        item.get("sha256") if item else None,
        item.get("bytes") if item else None,
        digest == item.get("sha256") if item else None,
        size == item.get("bytes") if item else None,
        pointer, readable, rows, columns, error,
    )


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def reproduce(prior: Path) -> dict[str, Any]:
    summary = json.loads((prior / "deep_sequence_summary.json").read_text(encoding="utf-8"))
    discrimination = pd.read_csv(prior / "deep_precursor_discrimination.csv")
    event = pd.read_parquet(prior / "event_universe_5m.parquet")
    matched = pd.read_parquet(prior / "matched_controls.parquet")
    near = pd.read_parquet(prior / "near_miss_controls.parquet")

    summary_checks = {key: {"expected": expected, "actual": summary.get(key), "match": summary.get(key) == expected}
                      for key, expected in EXPECTED_SUMMARY.items()}
    family_count = int(discrimination["family"].nunique())
    definition_count = int(discrimination["tested_definitions"].sum())

    checks = {
        "summary": summary_checks,
        "family_count": {"expected": 10, "actual": family_count, "match": family_count == 10},
        "definition_count": {"expected": 10, "actual": definition_count, "match": definition_count == 10},
        "matched_control_rows": {"published": 178521, "actual": len(matched), "match": len(matched) == 178521},
        "near_miss_rows": {"published": 100983, "actual": len(near), "match": len(near) == 100983},
    }

    # The event parquet may contain observation-level rows rather than one row per cluster.
    # Reproduce counts only from explicit identifiers when present; otherwise report schema-limited.
    event_columns = set(map(str, event.columns))
    cluster_col = next((c for c in ["event_cluster_id", "cluster_id", "move_cluster_id"] if c in event_columns), None)
    session_col = next((c for c in ["session", "session_date", "trade_date", "date"] if c in event_columns), None)
    if cluster_col:
        actual_clusters = int(event[cluster_col].nunique(dropna=True))
        checks["event_clusters_from_parquet"] = {"expected": 11261, "actual": actual_clusters, "match": actual_clusters == 11261}
    else:
        checks["event_clusters_from_parquet"] = {"expected": 11261, "actual": None, "match": None, "reason": "cluster identifier absent"}
    if session_col:
        actual_sessions = int(event[session_col].nunique(dropna=True))
        checks["event_sessions_from_parquet"] = {"expected": 385, "actual": actual_sessions, "match": actual_sessions == 385}
    else:
        checks["event_sessions_from_parquet"] = {"expected": 385, "actual": None, "match": None, "reason": "session identifier absent"}

    hard_results: list[bool] = []
    for value in summary_checks.values():
        hard_results.append(bool(value["match"]))
    hard_results += [family_count == 10, definition_count == 10, len(matched) == 178521, len(near) == 100983]
    for key in ["event_clusters_from_parquet", "event_sessions_from_parquet"]:
        if checks[key]["match"] is not None:
            hard_results.append(bool(checks[key]["match"]))

    return {
        "verdict": "PRIOR_CAMPAIGN_REPRODUCED" if all(hard_results) else "PRIOR_CAMPAIGN_NOT_REPRODUCIBLE",
        "checks": checks,
        "schemas": {
            "event_universe": list(map(str, event.columns)),
            "matched_controls": list(map(str, matched.columns)),
            "near_miss_controls": list(map(str, near.columns)),
            "discrimination": list(map(str, discrimination.columns)),
        },
        "rows": {
            "event_universe": len(event),
            "matched_controls": len(matched),
            "near_miss_controls": len(near),
            "discrimination": len(discrimination),
        },
        "family_records": discrimination.to_dict(orient="records"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    prior = root / PRIOR_REL
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(root)
    audits = [audit_file(root, prior / name, manifest) for name in REQUIRED]
    audit_payload = {"files": [asdict(a) for a in audits]}
    invalid = [a for a in audits if (not a.exists or a.lfs_pointer or not a.readable or a.hash_match is False or a.size_match is False)]
    audit_payload["verdict"] = "INVALID_CONSOLIDATED_EVIDENCE" if invalid else "CONSOLIDATED_EVIDENCE_VALID"
    stable_json(out / "source_inventory.json", audit_payload)

    if invalid:
        stable_json(out / "final_decision.json", {
            "principal_verdict": "INVALID_CONSOLIDATED_EVIDENCE",
            "invalid_files": [asdict(a) for a in invalid],
        })
        return 2

    result = reproduce(prior)
    stable_json(out / "prior_campaign_reproduction.json", result)
    md = ["# Prior Campaign Reproduction", "", f"Verdict: `{result['verdict']}`", "", "## Counts"]
    for key, value in result["rows"].items():
        md.append(f"- {key}: `{value}`")
    md.extend(["", "## Checks"])
    for key, value in result["checks"].items():
        md.append(f"- {key}: `{json.dumps(value, sort_keys=True)}`")
    (research / "prior_campaign_reproduction.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    stable_json(out / "final_decision.json", {
        "principal_verdict": result["verdict"],
        "next_stage_allowed": result["verdict"] == "PRIOR_CAMPAIGN_REPRODUCED",
        "research_only": True,
        "allowed_for_live_execution": False,
    })
    return 0 if result["verdict"] == "PRIOR_CAMPAIGN_REPRODUCED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
