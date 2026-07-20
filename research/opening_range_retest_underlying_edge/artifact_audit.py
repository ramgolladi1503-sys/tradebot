from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "research" / "opening_range_retest_underlying_edge"
CANDIDATE_LEDGER = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_causal_replay_candidate_ledger_v2.json"
OUTCOME_LEDGER = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_outcome_ledger_v2.json"
VALIDATED_SOURCE = "cf1b63908c779db844ef3534804142a8af26cbac"
REQUIRED = (
    "source_identity.json",
    "input_audit.json",
    "input_audit.md",
    "underlying_edge_contract.json",
    "all_candidate_results.json",
    "score_discrimination_results.json",
    "wfa_fold_results.json",
    "final_holdout_results.json",
    "statistical_uncertainty.json",
    "negative_controls.json",
    "concentration_analysis.json",
    "determinism_report.json",
    "final_verdict.json",
    "final_report.md",
)
ALLOWED_VERDICTS = {
    "UNDERLYING_STRUCTURAL_EDGE_CONFIRMED",
    "CORRECTED_SCORE_DISCRIMINATION_CONFIRMED",
    "CANDIDATE_EDGE_PRESENT_SCORE_NOT_PREDICTIVE",
    "UNDERLYING_SIGNAL_WEAK_OR_UNSTABLE",
    "NO_UNDERLYING_STRUCTURAL_EDGE",
    "INSUFFICIENT_HISTORICAL_UNDERLYING_EVIDENCE",
}


def cbytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    data = cbytes(payload) + b"\n"
    path.write_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{hashlib.sha256(data).hexdigest()}  {path.name}\n", encoding="utf-8")


def sidecar_failures(output_dir: Path) -> list[str]:
    failures = []
    for path in sorted([*output_dir.glob("*.json"), *output_dir.glob("*.md")]):
        if path.name == "artifact_audit.json":
            continue
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not sidecar.exists():
            failures.append(f"{path.name}:missing_sidecar")
            continue
        expected = sidecar.read_text(encoding="utf-8").split()[0]
        actual = sha256_file(path)
        if expected != actual:
            failures.append(f"{path.name}:sha256_mismatch")
    return failures


def source_join_failures() -> list[str]:
    failures = []
    candidates = read_json(CANDIDATE_LEDGER)["records"]
    outcomes = read_json(OUTCOME_LEDGER)["records"]
    cids = [row["candidate_id"] for row in candidates]
    oids = [row["candidate_id"] for row in outcomes]
    if len(cids) != 2215:
        failures.append("candidate_count")
    if len(set(cids)) != len(cids):
        failures.append("duplicate_candidates")
    if len(set(oids)) != len(oids):
        failures.append("duplicate_outcomes")
    if set(cids) != set(oids):
        failures.append("candidate_outcome_set_mismatch")
    measured = sum(1 for row in outcomes if row["horizons"]["15"]["status"] == "MEASURED")
    if measured < 300:
        failures.append("primary_horizon_sample_gate")
    return failures


def artifact_failures(output_dir: Path) -> list[str]:
    failures = []
    payload = {name: read_json(output_dir / name) for name in REQUIRED if name.endswith(".json") and (output_dir / name).exists()}
    source = payload.get("source_identity.json", {})
    contract = payload.get("underlying_edge_contract.json", {})
    folds = payload.get("wfa_fold_results.json", {}).get("folds", [])
    stats = payload.get("statistical_uncertainty.json", {})
    controls = payload.get("negative_controls.json", {})
    verdict = payload.get("final_verdict.json", {})
    if source.get("validated_production_source") != VALIDATED_SOURCE or source.get("decision") != "PASS":
        failures.append("source_identity")
    if contract.get("primary_horizon") != "15-minute direction-normalized underlying return":
        failures.append("primary_horizon")
    if contract.get("chronological_split", {}).get("random_split") != "FORBIDDEN":
        failures.append("random_split_not_forbidden")
    if len(folds) != 5 or [fold.get("fold") for fold in folds] != [1, 2, 3, 4, 5]:
        failures.append("fold_completeness")
    if any("training_score_80th_percentile" not in fold for fold in folds):
        failures.append("training_thresholds_missing")
    if stats.get("aggregate_oos_mean", {}).get("method") != "session_cluster":
        failures.append("bootstrap_not_session_cluster")
    if stats.get("bootstrap_resamples") != 10000:
        failures.append("bootstrap_resample_count")
    if controls.get("permutations") != 2000:
        failures.append("control_permutation_count")
    if controls.get("join_corruption_control") != "PASS_FAILS_CLOSED":
        failures.append("join_corruption_control")
    if verdict.get("final_verdict") not in ALLOWED_VERDICTS:
        failures.append("unknown_final_verdict")
    if verdict.get("option_economic_edge") != "NOT_EVALUATED_NO_BID_ASK" or verdict.get("option_profitability_claimed") != "NO":
        failures.append("option_profitability_boundary")
    broker_flag = verdict.get("broker_api_called")
    if verdict.get("production_files_changed") != "NO" or broker_flag not in {"NO", False} or verdict.get("order_action") != "NO":
        failures.append("safety_boundary")
    determinism = payload.get("determinism_report.json", {})
    if determinism.get("decision") not in {"PASS", "PENDING_EXTERNAL_TWO_RUN_COMPARISON"}:
        failures.append("determinism")
    return failures


def audit(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    missing = [name for name in REQUIRED if not (output_dir / name).exists()]
    failures = {
        "missing": missing,
        "sidecars": sidecar_failures(output_dir),
        "source_join": source_join_failures(),
        "artifacts": artifact_failures(output_dir) if not missing else ["missing_required_artifacts"],
    }
    flat = [item for values in failures.values() for item in values]
    report = {
        "schema_version": 1,
        "mode": "ORB_UNDERLYING_EDGE_ARTIFACT_AUDIT",
        "verdict": "PASS" if not flat else "FAIL",
        "failures": failures,
        "candidate_outcome_join_verified": not failures["source_join"],
        "no_option_profitability_claim": "option_profitability_boundary" not in failures["artifacts"],
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
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
