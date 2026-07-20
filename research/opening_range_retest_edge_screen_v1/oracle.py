from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.opening_range_retest_edge_screen_v1 import contract as C


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(output_dir: Path) -> dict[str, Any]:
    failures: list[str] = []
    artifacts: dict[str, dict[str, Any]] = {}
    for key, filename in C.ARTIFACT_NAMES.items():
        path = output_dir / filename
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not path.exists():
            failures.append(f"MISSING_ARTIFACT:{key}")
            continue
        actual = C.sha256_file(str(path))
        expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None
        if actual != expected:
            failures.append(f"SIDECAR_MISMATCH:{key}")
        artifacts[key] = {"path": filename, "sha256": actual, "sidecar_sha256": expected}
    if failures:
        return {"schema_version": C.SCHEMA_VERSION, "mode": "ORB_EDGE_SCREEN_ORACLE_AUDIT_V1", "verdict": "ORB_EDGE_SCREEN_AUDIT_FAILED", "failures": failures, **C.safety_fields()}
    contract = load_json(output_dir / C.ARTIFACT_NAMES["contract"])
    metrics = load_json(output_dir / C.ARTIFACT_NAMES["metrics"])
    controls = load_json(output_dir / C.ARTIFACT_NAMES["controls"])
    concentration = load_json(output_dir / C.ARTIFACT_NAMES["concentration"])
    replication = load_json(output_dir / C.ARTIFACT_NAMES["replication"])
    overlap = load_json(output_dir / C.ARTIFACT_NAMES["overlap"])
    verdict = load_json(output_dir / C.ARTIFACT_NAMES["verdict"])
    if contract != C.contract_payload():
        failures.append("CONTRACT_PAYLOAD_MISMATCH")
    if metrics["primary_horizon"] != C.PRIMARY_HORIZON or metrics["secondary_horizon"] != C.SECONDARY_HORIZON:
        failures.append("HORIZON_SWITCH_DETECTED")
    if metrics["primary"]["candidate_count"] != C.EXPECTED_MEASURED_COUNTS[C.PRIMARY_HORIZON]:
        failures.append("PRIMARY_COUNT_MISMATCH")
    if metrics["secondary"]["candidate_count"] != C.EXPECTED_MEASURED_COUNTS[C.SECONDARY_HORIZON]:
        failures.append("SECONDARY_COUNT_MISMATCH")
    recomputed_structural = all(verdict.get("structural_gates", {}).values())
    if verdict["verdict"] == "ORB_STRUCTURAL_EDGE_CANDIDATE" and not recomputed_structural:
        failures.append("VERDICT_UPGRADE_WITH_FAILED_STRUCTURAL_GATE")
    if controls["opposite_direction"]["verdict"] != "PASS":
        failures.append("OPPOSITE_DIRECTION_CONTROL_FAILED")
    if controls["matched_time"]["coverage"] > 1 or controls["matched_time"]["coverage"] < 0:
        failures.append("MATCHED_TIME_COVERAGE_INVALID")
    if concentration["removal_means"]["best_5_sessions_removed"] != concentration["removal_means"]["best_5_sessions_removed"]:
        failures.append("CONCENTRATION_NAN")
    if not replication["years"] or not replication["symbols"] or not replication["directions"]:
        failures.append("REPLICATION_TABLE_MISSING")
    if overlap["sensitivity_a"]["candidate_count"] <= 0 or overlap["sensitivity_b"]["candidate_count"] <= 0:
        failures.append("OVERLAP_SENSITIVITY_EMPTY")
    return {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_ORACLE_AUDIT_V1",
        "verdict": "ORB_EDGE_SCREEN_AUDIT_CERTIFIED" if not failures else "ORB_EDGE_SCREEN_AUDIT_FAILED",
        "failures": failures,
        "artifact_hashes": artifacts,
        **C.safety_fields(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(audit(Path(args.artifact_dir)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

