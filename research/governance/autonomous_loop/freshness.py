"""Scope-aware historical evidence freshness proofs."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import subprocess
from typing import Mapping, Sequence

@dataclass(frozen=True)
class FreshnessProof:
    task_candidate_sha: str
    current_program_sha: str
    owned_paths: tuple[str, ...]
    frozen_spec_paths: tuple[str, ...]
    dependency_interface_paths: tuple[str, ...]
    task_diff_status: str
    spec_diff_status: str
    dependency_compatibility: Mapping[str, object]
    historical_evidence_integrity: str
    invalidating_findings: tuple[str, ...]
    safety_assumptions_unchanged: bool
    freshness_status: str

def prove_freshness(*, task_candidate_sha: str, current_program_sha: str, owned_paths: Sequence[str], frozen_spec_paths: Sequence[str] = (), dependency_interface_paths: Sequence[str] = (), evidence_path: str | Path | None = None, evidence_sha256: str | None = None, invalidating_findings: Sequence[str] = (), dependency_compatibility: bool = True, safety_assumptions_unchanged: bool = True) -> FreshnessProof:
    _sha(task_candidate_sha); _sha(current_program_sha)
    task_status = _diff_status(task_candidate_sha, current_program_sha, owned_paths)
    spec_status = _diff_status(task_candidate_sha, current_program_sha, frozen_spec_paths)
    dep_status = _diff_status(task_candidate_sha, current_program_sha, dependency_interface_paths)
    integrity = "PASS"
    if evidence_path is None or not Path(evidence_path).is_file(): integrity = "UNKNOWN"
    elif evidence_sha256 and _file_sha(Path(evidence_path)) != evidence_sha256: integrity = "FAIL"
    fresh = all((task_status == "UNCHANGED", spec_status == "UNCHANGED", dep_status == "UNCHANGED" or dependency_compatibility, integrity == "PASS", not invalidating_findings, safety_assumptions_unchanged))
    return FreshnessProof(task_candidate_sha, current_program_sha, tuple(owned_paths), tuple(frozen_spec_paths), tuple(dependency_interface_paths), task_status, spec_status, {"status": "PASS" if dependency_compatibility else "FAIL"}, integrity, tuple(invalidating_findings), safety_assumptions_unchanged, "PASS" if fresh else "FAIL")

def validate_freshness_record(record: Mapping[str, object]) -> None:
    required = {"task_candidate_sha", "current_program_sha", "owned_paths", "frozen_spec_paths", "dependency_interface_paths", "task_diff_status", "spec_diff_status", "dependency_compatibility", "historical_evidence_integrity", "invalidating_findings", "safety_assumptions_unchanged", "freshness_status"}
    if not required.issubset(record) or record.get("freshness_status") != "PASS": raise ValueError("FRESHNESS_PROOF_REQUIRED")
    _sha(record["task_candidate_sha"]); _sha(record["current_program_sha"])
    if record.get("historical_evidence_integrity") != "PASS" or record.get("invalidating_findings") or record.get("safety_assumptions_unchanged") is not True: raise ValueError("FRESHNESS_PROOF_INVALID")
    if record.get("dependency_compatibility", {}).get("status") != "PASS": raise ValueError("DEPENDENCY_COMPATIBILITY_REQUIRED")

def _diff_status(old: str, new: str, paths: Sequence[str]) -> str:
    if not paths: return "UNCHANGED"
    result = subprocess.run(["git", "diff", "--quiet", old, new, "--", *paths], capture_output=True, check=False)
    if result.returncode == 0: return "UNCHANGED"
    if result.returncode == 1: return "CHANGED"
    return "UNKNOWN"
def _file_sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _sha(value: object) -> None:
    if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value): raise ValueError("EXACT_TASK_SHA_REQUIRED")
