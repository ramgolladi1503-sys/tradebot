from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(__file__).resolve().parent
EXPECTED_FINAL_VERDICT = "INSUFFICIENT_TRUSTED_OPTION_DATA"
REQUIRED_JSON_FILES = (
    "edge_validation_contract.json",
    "dataset_manifest.json",
    "source_identity.json",
    "candidate_conservation.json",
    "candidate_semantic_hashes.json",
    "outcome_invariance.json",
    "underlying_outcome_summary.json",
    "option_economic_summary.json",
    "score_discrimination_summary.json",
    "wfa_fold_results.json",
    "holdout_results.json",
    "statistical_uncertainty.json",
    "negative_controls.json",
    "concentration_analysis.json",
    "external_artifact_manifest.json",
    "determinism_report.json",
    "final_verdict.json",
)
REQUIRED_TEXT_FILES = (
    "candidate_conservation.md",
    "outcome_invariance.md",
    "determinism_report.md",
    "final_report.md",
)
UNAVAILABLE_REQUIRED_STATUSES = {
    "old_vs_corrected_score_ledger": "NOT_GENERATED_DUAL_REPLAY_MISSING",
    "option_trade_ledger": "NOT_GENERATED_NO_TRUSTED_OPTION_BID_ASK",
}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_with_sidecar(path: Path, payload: dict[str, Any]) -> None:
    data = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(data)
    digest = sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def validate_sidecars(output_dir: Path) -> list[str]:
    failures: list[str] = []
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


def validate_parquet_artifact(artifact: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    name = str(artifact.get("logical_artifact_name"))
    path_value = artifact.get("path")
    if not path_value:
        return [f"{name}:available_missing_path"]
    path = Path(path_value)
    if not path.exists():
        return [f"{name}:available_file_missing"]
    if path.stat().st_size <= 0:
        failures.append(f"{name}:zero_byte_parquet")
    with path.open("rb") as handle:
        header = handle.read(4)
        handle.seek(max(path.stat().st_size - 4, 0))
        footer = handle.read(4)
    if header != b"PAR1" or footer != b"PAR1":
        failures.append(f"{name}:invalid_parquet_magic")
    if artifact.get("sha256") != sha256_file(path):
        failures.append(f"{name}:sha256_mismatch")
    if artifact.get("row_count") is None or artifact.get("sha256") is None:
        failures.append(f"{name}:available_null_rows_or_hash")
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except Exception:
        failures.append(f"{name}:parquet_reader_unavailable")
    else:
        try:
            parquet_file = pq.ParquetFile(path)
            if artifact.get("row_count") != parquet_file.metadata.num_rows:
                failures.append(f"{name}:row_count_mismatch")
            schema_fields = [field.name for field in parquet_file.schema_arrow]
            expected_schema = artifact.get("schema")
            if expected_schema is not None and expected_schema != schema_fields:
                failures.append(f"{name}:schema_mismatch")
        except Exception as exc:
            failures.append(f"{name}:parquet_metadata_unreadable:{type(exc).__name__}")
    return failures


def validate_external_artifacts(output_dir: Path, external: dict[str, Any], final: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    available = external.get("available_artifacts", [])
    unavailable = external.get("unavailable_artifacts", [])
    if not isinstance(available, list) or not isinstance(unavailable, list):
        return ["external_manifest:missing_availability_categories"]
    unavailable_by_name = {item.get("logical_artifact_name"): item for item in unavailable}
    for name, status in UNAVAILABLE_REQUIRED_STATUSES.items():
        item = unavailable_by_name.get(name)
        if item is None:
            failures.append(f"{name}:missing_unavailable_record")
            continue
        if item.get("status") != status:
            failures.append(f"{name}:unexpected_unavailable_status")
        if item.get("path") is not None or item.get("size_bytes") is not None or item.get("sha256") is not None or item.get("row_count") is not None:
            failures.append(f"{name}:unavailable_has_physical_metadata")
        placeholder = output_dir / f"{name}.parquet"
        if placeholder.exists():
            failures.append(f"{name}:unavailable_physical_placeholder_exists")
    if final.get("final_verdict") == EXPECTED_FINAL_VERDICT and "option_trade_ledger" not in unavailable_by_name:
        failures.append("option_trade_ledger:required_unavailable_for_insufficient_data")
    for artifact in available:
        if artifact.get("expected_format") == "parquet" or artifact.get("format") == "parquet":
            failures.extend(validate_parquet_artifact(artifact))
    return failures


def validate_candidate_conservation(candidate: dict[str, Any], final: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    decision = candidate.get("decision")
    if decision == "PASS":
        if not candidate.get("distinct_generated_ledger_paths") or len(candidate.get("source_shas_compared", [])) != 2 or len(candidate.get("ledger_sha256_values", [])) != 2:
            failures.append("candidate_conservation:pass_without_two_source_ledgers")
    if decision == "NOT_EVALUATED_DUAL_REPLAY_UNAVAILABLE":
        if candidate.get("base_candidate_count") is not None:
            failures.append("candidate_conservation:baseline_count_inferred")
        if final.get("base_candidate_count") is not None:
            failures.append("final_verdict:baseline_count_inferred")
    if final.get("candidate_conservation") != decision:
        failures.append("final_verdict:candidate_conservation_mismatch")
    return failures


def validate_determinism(determinism: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if determinism.get("decision") != "PASS":
        failures.append("determinism:not_pass")
    if not determinism.get("run_a_hash") or not determinism.get("run_b_hash"):
        failures.append("determinism:missing_run_hashes")
    if not determinism.get("run_a") or not determinism.get("run_b") or determinism.get("run_a") == determinism.get("run_b"):
        failures.append("determinism:missing_two_run_identities")
    if determinism.get("comparison_result") != "PASS" or determinism.get("differing_artifacts"):
        failures.append("determinism:comparison_failed")
    for key in ("old_vs_corrected_score_ledger", "option_trade_ledger"):
        if determinism.get(key) != "NOT_APPLICABLE_ARTIFACT_UNAVAILABLE":
            failures.append(f"determinism:{key}_availability_misclassified")
    return failures


def validate_source_identity(source_identity: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if source_identity.get("decision") != "PASS":
        failures.append("source_identity:not_pass")
    if source_identity.get("validated_production_source_sha") != "cf1b63908c779db844ef3534804142a8af26cbac":
        failures.append("source_identity:production_source_mismatch")
    if source_identity.get("production_changed_paths_since_validated_source"):
        failures.append("source_identity:production_changes_since_source")
    if source_identity.get("working_tree_production_diffs_vs_validated_source"):
        failures.append("source_identity:working_tree_production_diff")
    return failures


def audit(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    missing = [name for name in (*REQUIRED_JSON_FILES, *REQUIRED_TEXT_FILES) if not (output_dir / name).exists()]
    sidecar_failures = validate_sidecars(output_dir)
    payloads: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_JSON_FILES:
        path = output_dir / name
        if path.exists():
            payloads[name] = load_json(path)
    final = payloads.get("final_verdict.json", {})
    manifest = payloads.get("dataset_manifest.json", {})
    external = payloads.get("external_artifact_manifest.json", {})
    candidate = payloads.get("candidate_conservation.json", {})
    determinism = payloads.get("determinism_report.json", {})
    source_identity = payloads.get("source_identity.json", {})
    external_failures = validate_external_artifacts(output_dir, external, final) if external else ["external_manifest:missing"]
    candidate_failures = validate_candidate_conservation(candidate, final) if candidate else ["candidate_conservation:missing"]
    determinism_failures = validate_determinism(determinism) if determinism else ["determinism:missing"]
    source_failures = validate_source_identity(source_identity) if source_identity else ["source_identity:missing"]
    verdict_too_strong = []
    if final.get("final_verdict") != EXPECTED_FINAL_VERDICT:
        verdict_too_strong.append("final_verdict:unexpected_or_too_strong")
    if final.get("trusted_option_bid_ask_available") != "NO" or manifest.get("trusted_option_bid_ask_available") is not False:
        verdict_too_strong.append("trusted_option_bid_ask:unexpected_available")
    failures = [
        *missing,
        *sidecar_failures,
        *external_failures,
        *candidate_failures,
        *determinism_failures,
        *source_failures,
        *verdict_too_strong,
    ]
    report = {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_SCORE_EDGE_ARTIFACT_AUDIT",
        "verdict": "PASS" if not failures else "FAIL",
        "missing_files": missing,
        "sidecar_failures": sidecar_failures,
        "external_artifact_failures": external_failures,
        "candidate_conservation_failures": candidate_failures,
        "determinism_failures": determinism_failures,
        "source_identity_failures": source_failures,
        "verdict_boundary_failures": verdict_too_strong,
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
    write_json_with_sidecar(output_dir / "artifact_audit.json", report)
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
