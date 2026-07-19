from __future__ import annotations

from pathlib import Path
from typing import Any

from research.opening_range_retest_outcomes_v2.contract import INPUT_CANDIDATE_COUNT, canonical_json_bytes, safety_fields, sha256_bytes, sha256_file


def verify_sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    actual = sha256_file(path)
    expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None
    return {"path": str(path), "artifact_sha256": actual, "sidecar_sha256": expected, "sidecar_match": actual == expected}


def audit_outputs(*, contract: dict[str, Any], ledger: dict[str, Any], summary: dict[str, Any], overlap: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    failures = []
    records = ledger.get("records") or []
    if len(records) != INPUT_CANDIDATE_COUNT:
        failures.append("CANDIDATE_COUNT_MISMATCH")
    ids = [record.get("candidate_id") for record in records]
    if len(ids) != len(set(ids)):
        failures.append("DUPLICATE_CANDIDATE_ID")
    recomputed = sha256_bytes(canonical_json_bytes(records))
    if recomputed != ledger.get("outcome_ledger_hash"):
        failures.append("OUTCOME_LEDGER_HASH_MISMATCH")
    if ledger.get("decision") != "ORB_OUTCOME_LEDGER_V2_CERTIFIED":
        failures.append("OUTCOME_LEDGER_NOT_CERTIFIED")
    sidecars = {name: verify_sidecar(path) for name, path in paths.items()}
    if not all(item["sidecar_match"] for item in sidecars.values()):
        failures.append("ARTIFACT_SIDECAR_MISMATCH")
    if summary.get("decision") != "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED":
        failures.append("SUMMARY_NOT_CERTIFIED")
    return {
        "schema_version": 1,
        "mode": "ORB_OUTCOME_AUDIT_V2",
        "verdict": "ORB_OUTCOMES_V2_AUDIT_CERTIFIED" if not failures else "ORB_OUTCOMES_V2_AUDIT_NOT_CERTIFIED",
        "failures": failures,
        "candidate_conservation": "CANDIDATE_CONSERVATION_PASS" if len(records) == INPUT_CANDIDATE_COUNT and len(ids) == len(set(ids)) else "CANDIDATE_CONSERVATION_FAIL",
        "recomputed_outcome_ledger_hash": recomputed,
        "sidecar_verdict": "ARTIFACT_SIDECARS_CERTIFIED" if "ARTIFACT_SIDECAR_MISMATCH" not in failures else "ARTIFACT_SIDECARS_NOT_CERTIFIED",
        "source_join_verified_count": ledger.get("join_verified_count"),
        "overlap_decision": overlap.get("decision"),
        **safety_fields(),
    }

