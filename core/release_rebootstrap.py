"""Exceptional post-quarantine release rebootstrap.

This is not a normal promotion path. It exists only to cross a release-store
head that repository policy explicitly quarantines, while retaining that head
and all ancestors in the append-only audit chain.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import subprocess

from .certified_release_store import ReleaseStore, ReleaseStoreError
from .release_certification import (
    EVALUATOR_VERSION, SHA_RE, SYNTHETIC_INVALIDATED_SHAS, _git, _predicate,
    _primitive, dependency_graph_digest, digest,
)
from .release_change_impact import BASE_GATES, BOUNDED_GATES, CRITICAL_GATES, DependencyEvidence

REBOOTSTRAP_VERSION = "post_pr907_primitive_v1"
REBOOTSTRAP_GATES = sorted(BASE_GATES | BOUNDED_GATES | CRITICAL_GATES)


def certify_rebootstrap(repo: Path, candidate: str, store: ReleaseStore, graph: DependencyEvidence,
                        *, primitive_root: Path | None, primitive_manifest: Mapping[str, object] | None,
                        reason: str) -> dict[str, Any]:
    """Recompute the full governed gate set against an explicitly quarantined head."""
    try:
        if SHA_RE.fullmatch(candidate) is None or candidate in SYNTHETIC_INVALIDATED_SHAS:
            raise ReleaseStoreError("invalid_rebootstrap_candidate")
        if not isinstance(reason, str) or not reason.strip():
            raise ReleaseStoreError("rebootstrap_reason_required")
        if not graph.complete or graph.unresolved:
            raise ReleaseStoreError("rebootstrap_dependency_graph_incomplete")
        if _git(repo, "rev-parse", "HEAD") != candidate:
            raise ReleaseStoreError("candidate_not_checked_out")
        if _git(repo, "status", "--porcelain"):
            raise ReleaseStoreError("candidate_tree_dirty")
        _git(repo, "cat-file", "-e", candidate + "^{commit}")
        current = store.read()
        if current is None:
            raise ReleaseStoreError("rebootstrap_requires_existing_store")
        predecessor = current.get("certified_live_sha")
        if predecessor not in SYNTHETIC_INVALIDATED_SHAS:
            raise ReleaseStoreError("rebootstrap_requires_quarantined_head")
        if current.get("schema_version") == 2:
            raise ReleaseStoreError("rebootstrap_from_rebootstrap_forbidden")
        if primitive_root is None or primitive_manifest is None:
            raise ReleaseStoreError("governed_primitives_required")
        if set(primitive_manifest) != set(REBOOTSTRAP_GATES):
            raise ReleaseStoreError("rebootstrap_requires_full_gate_set")

        evaluations = []
        for gate in REBOOTSTRAP_GATES:
            primitive = _primitive(Path(primitive_root), gate, candidate, primitive_manifest, repo)
            passed = _predicate(gate, primitive["payload"], repo, candidate)
            evaluations.append({"gate": gate, "evaluator": gate, "evaluator_version": EVALUATOR_VERSION,
                                "primitive_path": primitive["path"], "primitive_sha256": primitive["sha256"],
                                "observed": primitive["payload"]["observed"],
                                "status": "PASS" if passed else "FAIL",
                                "recomputed_result": "PASS" if passed else "FAIL",
                                "evaluated_at": datetime.now(timezone.utc).isoformat()})
        failed = [entry["gate"] for entry in evaluations if entry["recomputed_result"] != "PASS"]
        result: dict[str, Any] = {
            "schema_version": 1, "certification_type": "GOVERNED_REBOOTSTRAP",
            "trust_boundary": REBOOTSTRAP_VERSION, "candidate_sha": candidate,
            "quarantined_predecessor_sha": predecessor,
            "quarantined_predecessor_event": current["event_sha256"],
            "fallback_sha": None, "rollback_status": "NO_TRUSTED_FALLBACK",
            "dependency_graph_sha256": dependency_graph_digest(graph),
            "required_gates": REBOOTSTRAP_GATES, "gate_evaluations": evaluations,
            "passed_gates": [entry["gate"] for entry in evaluations if entry["recomputed_result"] == "PASS"],
            "failed_gates": failed, "reason": reason.strip(), "verdict": "PASS" if not failed else "FAIL",
        }
        result["certification_sha256"] = digest(result)
        return result
    except (ReleaseStoreError, subprocess.CalledProcessError, OSError, ValueError, TypeError) as exc:
        return {"candidate_sha": candidate, "certification_type": "GOVERNED_REBOOTSTRAP",
                "verdict": "BLOCKED", "blocker": str(exc)}


def rebootstrap_binding(result: Mapping[str, Any]) -> dict[str, Any]:
    return {"candidate_sha": result["candidate_sha"],
            "quarantined_predecessor_sha": result["quarantined_predecessor_sha"],
            "quarantined_predecessor_event": result["quarantined_predecessor_event"],
            "required_gates": result["required_gates"],
            "evidence_hashes": [item["primitive_sha256"] for item in result["gate_evaluations"]],
            "dependency_graph_sha256": result["dependency_graph_sha256"],
            "certification_sha256": result["certification_sha256"],
            "reason": result["reason"], "rollback_status": result["rollback_status"]}


def promote_rebootstrap(result: Mapping[str, Any], store: ReleaseStore,
                        attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Append a rebootstrap event only when independently attested primitives bind exactly."""
    current = store.read()
    if current is None or current.get("certified_live_sha") not in SYNTHETIC_INVALIDATED_SHAS:
        raise ReleaseStoreError("rebootstrap_requires_quarantined_head")
    if result.get("certification_type") != "GOVERNED_REBOOTSTRAP" or result.get("verdict") != "PASS":
        raise ReleaseStoreError("rebootstrap_requires_governed_pass")
    if result.get("quarantined_predecessor_sha") != current.get("certified_live_sha") or result.get("quarantined_predecessor_event") != current.get("event_sha256"):
        raise ReleaseStoreError("rebootstrap_predecessor_changed")
    if result.get("fallback_sha") is not None or result.get("rollback_status") != "NO_TRUSTED_FALLBACK":
        raise ReleaseStoreError("rebootstrap_fallback_must_fail_closed")
    if set(result.get("passed_gates", ())) != set(REBOOTSTRAP_GATES) or result.get("failed_gates") not in ([], ()):
        raise ReleaseStoreError("rebootstrap_requires_all_governed_gates")
    unsigned = dict(result); claimed = unsigned.pop("certification_sha256", None)
    if claimed != digest(unsigned):
        raise ReleaseStoreError("certification_hash_mismatch")
    if isinstance(attestation, dict) and "attestation" in attestation:
        if attestation.get("independent_release_verifier_pass") is not True:
            raise ReleaseStoreError("rebootstrap_requires_independent_attestation")
        attestation = attestation["attestation"]
    if not isinstance(attestation, dict) or attestation.get("verdict") != "PASS" or attestation.get("verifier") != "verify_release_rebootstrap_v1" or attestation.get("binding_sha256") != digest(rebootstrap_binding(result)):
        raise ReleaseStoreError("rebootstrap_requires_independent_attestation")
    attestation_sha = digest(dict(attestation))
    event = store.record_governed_rebootstrap(
        candidate_sha=result["candidate_sha"], expected_event=current["event_sha256"],
        quarantined_predecessor_sha=current["certified_live_sha"],
        dependency_graph_sha256=result["dependency_graph_sha256"],
        certification_sha256=result["certification_sha256"],
        verifier_attestation_sha256=attestation_sha, reason=result["reason"])
    return {"promotion_status": "REBOOTSTRAPPED", **event}
