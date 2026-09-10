"""Offline candidate certification policy for the certified release journal."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable

from .certified_release_store import ReleaseStore, ReleaseStoreError
from .release_change_impact import DependencyEvidence, Impact, classify

ORIGINAL_CERTIFIED_SHA = "be002d824ff33adf1a3fe176144d61163c3f86c6"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _tree_clean(repo: Path) -> bool:
    unstaged = subprocess.run(["git", "-C", str(repo), "diff", "--quiet"])
    staged = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"])
    untracked = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"],
        text=True,
    ).strip()
    return unstaged.returncode == 0 and staged.returncode == 0 and not untracked


def certify(repo: Path, candidate: str, store: ReleaseStore, graph: DependencyEvidence,
            gate_runner: Callable[[str], bool] | None = None) -> dict:
    if len(candidate) != 40 or any(c not in "0123456789abcdef" for c in candidate):
        return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "invalid_exact_sha"}
    try:
        _git(repo, "cat-file", "-e", candidate + "^{commit}")
        if not _tree_clean(repo):
            return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "candidate_tree_dirty"}
        current = store.read()
        if current is None:
            return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "certified_release_uninitialized"}
        base = current["certified_live_sha"]
        changed = [] if base == candidate else _git(repo, "diff", "--name-only", base, candidate).splitlines()
        impact = classify(changed, graph)
        gates = impact["required_gates"]
        passed = [gate for gate in gates if gate_runner is not None and gate_runner(gate)]
        failed = [gate for gate in gates if gate not in passed]
        verdict = "PASS" if not failed and gate_runner is not None else "FAIL"
        return {"candidate_sha": candidate, "base_sha": base, "changed_paths": changed,
                "change_impact": impact["impact"], "required_gates": gates,
                "passed_gates": passed, "failed_gates": failed, "verdict": verdict,
                "fallback_sha": base}
    except (subprocess.CalledProcessError, ReleaseStoreError, ValueError) as exc:
        return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": str(exc)}


def _valid_exact_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def validate_certification_result(result: dict, current: dict | None) -> None:
    """Fail closed unless the certification result is complete and exact."""
    if not isinstance(result, dict):
        raise ReleaseStoreError("promotion_requires_structured_certification")
    if result.get("verdict") != "PASS":
        raise ReleaseStoreError("promotion_requires_certified_candidate")
    candidate = result.get("candidate_sha")
    if not _valid_exact_sha(candidate):
        raise ReleaseStoreError("promotion_requires_exact_candidate_sha")
    if current is None:
        raise ReleaseStoreError("promotion_requires_existing_certified_release")
    if result.get("base_sha") != current.get("certified_live_sha"):
        raise ReleaseStoreError("promotion_base_mismatch")
    if result.get("fallback_sha") != current.get("certified_live_sha"):
        raise ReleaseStoreError("promotion_fallback_mismatch")
    required = result.get("required_gates")
    passed = result.get("passed_gates")
    failed = result.get("failed_gates")
    if not isinstance(required, list) or not required:
        raise ReleaseStoreError("promotion_requires_required_gates")
    if not isinstance(passed, list) or set(passed) != set(required):
        raise ReleaseStoreError("promotion_requires_all_gates_passed")
    if failed not in ([], ()):
        raise ReleaseStoreError("promotion_requires_no_failed_gates")
    if len(required) != len(set(required)) or len(passed) != len(set(passed)):
        raise ReleaseStoreError("promotion_rejects_duplicate_gates")
    if "release_verifier" not in required or "release_verifier" not in passed:
        raise ReleaseStoreError("promotion_requires_independent_verifier_gate")


def promote(result: dict, store: ReleaseStore, evidence: bytes) -> dict:
    current = store.read()
    validate_certification_result(result, current)
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    event = store.record_verified_selection(candidate_sha=result["candidate_sha"],
                                            evidence_sha256=evidence_sha,
                                            expected_event=current["event_sha256"])
    return {"promotion_status": "PROMOTED", **event}
