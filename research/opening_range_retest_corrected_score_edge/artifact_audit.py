from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.opening_range_retest_corrected_score_edge.evaluator import OUTPUT_DIR, sha256_file, write_json


REQUIRED_FILES = (
    "edge_validation_contract.json",
    "dataset_manifest.json",
    "candidate_conservation.json",
    "candidate_conservation.md",
    "candidate_semantic_hashes.json",
    "old_vs_corrected_score_ledger.parquet",
    "outcome_invariance.json",
    "outcome_invariance.md",
    "underlying_outcome_summary.json",
    "option_trade_ledger.parquet",
    "option_economic_summary.json",
    "score_discrimination_summary.json",
    "wfa_fold_results.json",
    "holdout_results.json",
    "statistical_uncertainty.json",
    "negative_controls.json",
    "concentration_analysis.json",
    "determinism_report.json",
    "external_artifact_manifest.json",
    "final_verdict.json",
    "final_report.md",
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    missing = [name for name in REQUIRED_FILES if not (output_dir / name).exists()]
    sidecar_failures: list[str] = []
    for path in output_dir.glob("*.json"):
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not sidecar.exists():
            sidecar_failures.append(f"{path.name}:missing_sidecar")
            continue
        expected = sidecar.read_text(encoding="utf-8").split()[0]
        actual = sha256_file(path)
        if expected != actual:
            sidecar_failures.append(f"{path.name}:sha256_mismatch")
    final = _read(output_dir / "final_verdict.json") if (output_dir / "final_verdict.json").exists() else {}
    manifest = _read(output_dir / "dataset_manifest.json") if (output_dir / "dataset_manifest.json").exists() else {}
    external = _read(output_dir / "external_artifact_manifest.json") if (output_dir / "external_artifact_manifest.json").exists() else {}
    external_failures: list[str] = []
    for artifact in external.get("artifacts", []):
        path = Path(str(artifact.get("absolute_current_path") or ""))
        if not path.exists():
            external_failures.append(f"{artifact.get('logical_artifact_name')}:missing")
            continue
        if artifact.get("sha256") != sha256_file(path):
            external_failures.append(f"{artifact.get('logical_artifact_name')}:sha256_mismatch")
        if artifact.get("git_storage_decision") != "EXTERNAL_HASH_PINNED_REPO_POLICY_IGNORED":
            external_failures.append(f"{artifact.get('logical_artifact_name')}:storage_decision")
    verdict = (
        "PASS"
        if not missing
        and not sidecar_failures
        and not external_failures
        and final.get("final_verdict") == "INSUFFICIENT_TRUSTED_OPTION_DATA"
        else "FAIL"
    )
    report = {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_SCORE_EDGE_ARTIFACT_AUDIT",
        "verdict": verdict,
        "missing_files": missing,
        "sidecar_failures": sidecar_failures,
        "external_artifact_failures": external_failures,
        "final_verdict": final.get("final_verdict"),
        "trusted_option_bid_ask_available": manifest.get("trusted_option_bid_ask_available"),
        "production_files_changed": final.get("production_files_changed"),
        "broker_api_called": final.get("broker_api_called"),
        "order_action": final.get("order_action"),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called_bool": False,
        "allowed_for_live_execution": False,
    }
    write_json(output_dir / "artifact_audit.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = audit(args.output_dir)
    print(result["verdict"])
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
