"""Independent artifact audit for ORB fidelity outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent

REQUIRED_ARTIFACTS = (
    "source_identity.json",
    "specification_authority.json",
    "intended_strategy_spec.json",
    "intended_strategy_spec.md",
    "parameter_ownership_matrix.json",
    "parameter_ownership_matrix.md",
    "parameter_wiring_results.json",
    "temporal_semantics_results.json",
    "replay_equivalence_results.json",
    "candidate_vs_score_semantics.json",
    "label_truth_audit.json",
    "score_formula_audit.json",
    "profile_generality_audit.json",
    "implementation_spec_matrix.json",
    "final_fidelity_verdict.json",
    "final_fidelity_report.md",
    "artifact_audit.json",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_artifacts() -> dict[str, Any]:
    missing: list[str] = []
    sidecar_mismatches: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        path = OUT_DIR / name
        sidecar = OUT_DIR / f"{name}.sha256"
        if not path.exists():
            missing.append(name)
            continue
        if not sidecar.exists():
            missing.append(f"{name}.sha256")
            continue
        expected = sidecar.read_text(encoding="utf-8").split()[0]
        actual = sha256_file(path)
        if expected != actual:
            sidecar_mismatches.append(name)
    verdict_path = OUT_DIR / "final_fidelity_verdict.json"
    verdict = json.loads(verdict_path.read_text(encoding="utf-8")) if verdict_path.exists() else {}
    status = "READY" if not missing and not sidecar_mismatches and verdict.get("primary_verdict") == "PARAMETER_CONTRACT_BROKEN" else "INVALID"
    return {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "required_artifacts": list(REQUIRED_ARTIFACTS),
        "missing": missing,
        "sidecar_mismatches": sidecar_mismatches,
        "final_verdict": verdict.get("primary_verdict"),
        "status": status,
    }


if __name__ == "__main__":
    print(json.dumps(audit_artifacts(), sort_keys=True, indent=2))
