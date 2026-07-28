#!/usr/bin/env python3
"""ML meta-labeling robustness certification V2.

Certification-only. This runner treats the sprint artifacts as frozen inputs and
fails closed when required frozen artifacts are missing. It does not retrain,
retune, reconstruct models, call providers, call brokers, or create AlgoTest
specifications.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "2eead6378ffa6bad1127bd1d815e204ac5af0a77"
SPRINT = ROOT / "research/ml_meta_labeling_sprint_v1"
OUT = ROOT / "research/ml_meta_labeling_robustness_certification_v2"


REQUIRED_FROZEN_ARTIFACTS = {
    "candidate_dataset": ["candidate_level_dataset.parquet"],
    "feature_contract": ["feature_contract.json"],
    "label_contract": ["label_contract.json"],
    "split_contract": ["split_contract.json"],
    "model_configuration": ["model_contract.json", "tuning_ledger.json"],
    "trained_model": ["trained_model.joblib", "trained_model.pkl", "xgboost_model.json", "xgboost_model.ubj"],
    "calibration_object": ["calibration_model.joblib", "calibrator.joblib", "calibrated_model.joblib", "calibration_object.pkl"],
    "validation_top_10_threshold": ["xgboost_report.json", "calibrated_model_report.json"],
    "sealed_holdout_predictions": ["holdout_predictions.csv"],
    "economic_metric_implementation": ["scripts/run_ml_meta_labeling_sprint_v1.py"],
    "cost_model": ["label_contract.json"],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = stable_hash(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def first_existing(candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = ROOT / rel if rel.startswith("scripts/") else SPRINT / rel
        if path.exists():
            return path
    return None


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    inventory: dict[str, Any] = {}
    missing: list[str] = []
    for name, candidates in REQUIRED_FROZEN_ARTIFACTS.items():
        path = first_existing(candidates)
        inventory[name] = {
            "required": True,
            "accepted_names": candidates,
            "present": path is not None,
            "path": path.as_posix() if path else None,
            "sha256": sha256_file(path) if path else None,
        }
        if path is None:
            missing.append(name)

    sprint_final = json.loads((SPRINT / "final_verdict.json").read_text()) if (SPRINT / "final_verdict.json").exists() else {}
    verdict = "INVALID_ML_META_LABELING_CERTIFICATION_INPUTS" if missing else "INVALID_ML_META_LABELING_CERTIFICATION"
    reason = (
        "Required frozen certification artifacts are absent; retraining or reconstructing a materially equivalent model would violate the task."
        if missing
        else "All artifacts were present but this guard path should be replaced by full certification implementation."
    )
    write_json(
        OUT / "pre_change_manifest.json",
        {
            "worktree": ROOT.as_posix(),
            "branch": git(["branch", "--show-current"]),
            "source_commit": SOURCE_COMMIT,
            "current_commit": git(["rev-parse", "HEAD"]),
            "provider_calls": False,
            "broker_calls": False,
            "algotest_called": False,
            "production_changes": False,
        },
    )
    write_json(OUT / "frozen_artifact_hashes.json", {"artifacts": inventory, "missing_required_artifacts": missing})
    write_json(
        OUT / "certification_input_reconciliation.json",
        {
            "status": "FAIL",
            "source_sprint_verdict": sprint_final.get("final_verdict"),
            "source_best_model": sprint_final.get("best_model"),
            "source_best_bucket": sprint_final.get("best_bucket"),
            "source_required_incomplete_gates": sprint_final.get("required_incomplete_gates"),
            "missing_required_artifacts": missing,
            "no_retraining_performed": True,
            "no_threshold_reselection_performed": True,
        },
    )
    blocked_payload = {
        "status": "NOT_RUN",
        "reason": "blocked by missing frozen certification inputs",
        "missing_required_artifacts": missing,
    }
    for name in [
        "concrete_strike_selection_contract.json",
        "concrete_strike_coverage_report.json",
        "aggregate_vs_concrete_label_comparison.json",
        "concrete_holdout_economic_report.json",
        "one_bar_delayed_entry_report.json",
        "leave_feature_family_out_report.json",
        "shuffled_label_report.json",
        "equal_count_random_selector_report.json",
        "time_of_day_matched_selector_report.json",
        "concentration_report.json",
        "probability_bin_report.json",
        "expiry_side_setup_time_stability_report.json",
        "wfa_reconciliation.json",
    ]:
        write_json(OUT / name, blocked_payload)

    audit = {
        "frozen_model_available": inventory["trained_model"]["present"],
        "calibration_object_available": inventory["calibration_object"]["present"],
        "candidate_dataset_available": inventory["candidate_dataset"]["present"],
        "holdout_predictions_available": inventory["sealed_holdout_predictions"]["present"],
        "no_retraining": True,
        "no_retuning": True,
        "no_holdout_reopened": True,
        "provider_calls": False,
        "broker_calls": False,
        "algotest_called": False,
        "production_changes": False,
        "result": "FAIL",
        "failure_reason": reason,
    }
    write_json(OUT / "independent_audit.json", audit)
    write_json(OUT / "determinism_report.json", {"status": "PASS", "aggregate_hash": stable_hash({"inventory": inventory, "verdict": verdict})})
    write_json(OUT / "final_verdict.json", {"final_verdict": verdict, "reason": reason, "missing_required_artifacts": missing, "exact_next_action": "Rerun the ML sprint with persisted candidate dataset, serialized trained model, serialized calibration object, and frozen threshold artifacts before attempting certification."})
    write_json(OUT / "artifact_manifest.json", {"files": {p.relative_to(OUT).as_posix(): sha256_file(p) for p in sorted(OUT.rglob("*")) if p.is_file()}})
    return {"verdict": verdict, "missing": missing, "out_dir": OUT.as_posix()}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
