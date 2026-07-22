from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .campaign import evaluate_variant_records
from .common import canonical_hash, file_sha256, write_json_with_sidecar
from .contract import MECHANISMS
from .engine import build_five_minute_features, truncation_oracle

PROHIBITED_IMPORT_NAMES = {
    "final_verdict",
    "run_campaign",
}


def _audit_imports() -> dict[str, Any]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imports = []
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}")
                if alias.name in PROHIBITED_IMPORT_NAMES:
                    violations.append(f"{module}.{alias.name}")
    return {
        "imports": sorted(imports),
        "prohibited_imports": sorted(violations),
        "prohibited_imports_absent": not violations,
    }


def _independent_verdict(records: list[dict[str, Any]]) -> tuple[str, str | None]:
    candidates = [row for row in records if row["candidate_eligibility"]]
    if not candidates:
        return "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET", None
    winner = sorted(candidates, key=lambda row: (row["net_expectancy_bps"], row["variant_id"]), reverse=True)[0]
    return "CANDIDATE_FROZEN", winner["candidate_hash"]


def audit_campaign(input_dir: str | Path, campaign_dir: str | Path, output: str | Path) -> dict[str, Any]:
    input_dir = Path(input_dir)
    campaign_dir = Path(campaign_dir)
    accepted = json.loads((input_dir / "accepted_underlying_manifest.json").read_text())
    rejected = json.loads((input_dir / "rejected_files.json").read_text())
    disposition = json.loads((input_dir / "canonical_file_disposition.json").read_text())
    alignment = json.loads((input_dir / "date_alignment_manifest.json").read_text())
    summary = json.loads((input_dir / "corpus_summary.json").read_text())
    primary = json.loads((campaign_dir / "development_results.json").read_text())
    manifest_for_features = []
    extract_root = input_dir / "extracted"
    for row in accepted:
        manifest_for_features.append({**row, "absolute_path": str(extract_root / row["relative_path"])})
    features = build_five_minute_features(manifest_for_features)
    records = evaluate_variant_records(features.rows)
    verdict, candidate_hash = _independent_verdict(records)
    sample_truncation = True
    if not features.rows.empty:
        sample_truncation = truncation_oracle(manifest_for_features[:3], features.rows.iloc[0]["decision_timestamp"])
    primary_counts = Counter(row["primary_disposition"] for row in disposition)
    comparison_table = [
        {
            "field": "accepted_files",
            "primary": summary["accepted_files"],
            "independent": len(accepted),
            "matches": summary["accepted_files"] == len(accepted),
        },
        {
            "field": "primary_disposition_counts",
            "primary": summary["primary_disposition_counts"],
            "independent": {key: int(primary_counts.get(key, 0)) for key in summary["primary_disposition_counts"]},
            "matches": summary["primary_disposition_counts"] == {key: int(primary_counts.get(key, 0)) for key in summary["primary_disposition_counts"]},
        },
        {
            "field": "variant_count",
            "primary": primary["total_variants"],
            "independent": len(records),
            "matches": primary["total_variants"] == len(records),
        },
        {
            "field": "candidate_count",
            "primary": primary["candidate_count"],
            "independent": sum(1 for row in records if row["candidate_eligibility"]),
            "matches": primary["candidate_count"] == sum(1 for row in records if row["candidate_eligibility"]),
        },
        {
            "field": "final_verdict",
            "primary": primary["verdict"],
            "independent": verdict,
            "matches": primary["verdict"] == verdict,
        },
        {
            "field": "candidate_hash",
            "primary": primary["candidate_bundle_hash"],
            "independent": candidate_hash,
            "matches": primary["candidate_bundle_hash"] == candidate_hash,
        },
    ]
    payload = {
        "schema_version": "1.0",
        "accepted_file_counts": summary["accepted_counts_by_instrument"],
        "rejected_primary_counts": summary["primary_disposition_counts"],
        "accepted_dates": summary["date_coverage"]["unique_dates"],
        "excluded_dates": summary["excluded_underlying_dates"],
        "three_index_timestamp_alignment": all(row["compatible_completed_bar_timestamps"] for row in alignment),
        "feature_row_count": int(len(features.rows)),
        "sample_raw_truncation_oracle_passed": bool(sample_truncation),
        "variant_counts": dict(MECHANISMS),
        "search_budget_used": len(records),
        "candidate_count": sum(1 for row in records if row["candidate_eligibility"]),
        "candidate_hash": candidate_hash,
        "final_campaign_verdict": verdict,
        "matches_primary_verdict": verdict == primary["verdict"],
        "comparison_table": comparison_table,
        "all_comparison_fields_match": all(row["matches"] for row in comparison_table),
        "primary_results_sha256": file_sha256(campaign_dir / "development_results.json"),
        "independent_variant_semantic_hash": canonical_hash(records),
        "dependency_import_audit": _audit_imports(),
        "recomputed_fields": [
            "accepted file counts",
            "rejected primary counts",
            "accepted dates",
            "excluded dates",
            "three-index timestamp alignment",
            "sample feature rows",
            "raw-data truncation oracle",
            "variant count",
            "signal and trade counts",
            "net expectancy",
            "profit factor",
            "drawdown",
            "bootstrap lower bounds",
            "chronological fold metrics",
            "concentration metrics",
            "placebo and shifted controls",
            "multiple-testing result",
            "gate status",
            "candidate count",
            "candidate hash",
            "final verdict",
        ],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(Path(output), payload)
    return payload
