"""Fail-closed, offline release certification.

This module deliberately has no callback-shaped gate API. A release caller may
provide primitive-evidence locations, but gate authority remains in this
repository: each required gate is evaluated by its registered contract and the
candidate identity is checked again here and by the independent verifier.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .certified_release_store import ReleaseStore, ReleaseStoreError
from .release_change_impact import DependencyEvidence, classify
from .release_gate_registry import EVALUATOR_VERSION_V2, is_generic_exit_code_zero_placeholder, validate_gate_predicate_v2

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EVALUATOR_VERSION = "release_gate_registry_v1"
SYNTHETIC_INVALIDATED_SHAS = frozenset({"93934d7c040b338b840eabd72e575644eaa3fbc0"})


def canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def dependency_graph_digest(graph: DependencyEvidence) -> str:
    """Stable identity for the exact dependency graph used by certification."""
    payload = {"edges": {key: sorted(value) for key, value in sorted(graph.edges.items())},
               "critical_roots": sorted(graph.critical_roots), "bounded_roots": sorted(graph.bounded_roots),
               "complete": graph.complete, "unresolved": sorted(graph.unresolved)}
    return digest(payload)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _safe_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ReleaseStoreError("gate_primitive_path_missing")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved_root, resolved = root.resolve(), path.resolve()
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise ReleaseStoreError("gate_primitive_path_escapes_root")
    if path.is_symlink() or resolved.is_symlink() or not resolved.is_file():
        raise ReleaseStoreError("gate_primitive_missing")
    return resolved


def _primitive(root: Path, gate: str, candidate: str, manifest: Mapping[str, object], repo: Path) -> dict[str, Any]:
    raw_paths = list(manifest.values())
    if raw_paths.count(manifest.get(gate)) > 1:
        raise ReleaseStoreError("same_primitive_reused_for_multiple_gates")
    path = _safe_path(root, manifest.get(gate))
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseStoreError("gate_primitive_invalid_json") from exc
    if not isinstance(payload, dict):
        raise ReleaseStoreError("gate_primitive_not_object")
    if payload.get("gate") != gate:
        raise ReleaseStoreError("gate_primitive_gate_mismatch")
    if payload.get("candidate_sha") != candidate or payload.get("source_sha") != candidate:
        raise ReleaseStoreError("gate_primitive_candidate_mismatch")
    version = payload.get("evaluator_version")
    if payload.get("evaluator") != gate or version not in (EVALUATOR_VERSION, EVALUATOR_VERSION_V2):
        raise ReleaseStoreError("gate_primitive_evaluator_mismatch")
    observed = payload.get("observed")
    if not isinstance(observed, dict) or "pass" in payload or "result" in payload or "status" in payload:
        raise ReleaseStoreError("gate_primitive_contains_authored_result")
    if version == EVALUATOR_VERSION_V2 and is_generic_exit_code_zero_placeholder(observed) and gate != "source_identity":
        raise ReleaseStoreError("generic_exit_code_zero_placeholder_rejected")
    captured_at = payload.get("captured_at")
    try:
        captured = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
        committed = datetime.fromisoformat(_git(repo, "show", "-s", "--format=%cI", candidate).replace("Z", "+00:00"))
    except (TypeError, ValueError, subprocess.CalledProcessError) as exc:
        raise ReleaseStoreError("gate_primitive_timestamp_invalid") from exc
    if captured < committed:
        raise ReleaseStoreError("gate_primitive_stale")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "payload": payload}


def _predicate(gate: str, payload: Mapping[str, Any], repo: Path, candidate: str) -> bool:
    """Repository-owned evaluation contract. No supplied boolean is consulted."""
    observed = payload["observed"]
    version = payload.get("evaluator_version", EVALUATOR_VERSION)
    if version == EVALUATOR_VERSION_V2:
        return validate_gate_predicate_v2(gate, observed, repo, candidate)
    if gate == "source_identity":
        return observed == {"commit_exists": True} and _git(repo, "rev-parse", candidate) == candidate
    # Each non-identity gate needs a gate-specific immutable command primitive.
    # A generic artifact cannot satisfy this contract, because both the gate and
    # command identity must match the repository-owned evaluator registry.
    command = observed.get("command")
    exit_code = observed.get("exit_code")
    return isinstance(command, str) and command == f"governed:{gate}" and exit_code == 0 and len(observed) == 2


def certify(repo: Path, candidate: str, store: ReleaseStore, graph: DependencyEvidence,
            primitive_root: Path | None = None, primitive_manifest: Mapping[str, object] | None = None) -> dict[str, Any]:
    """Evaluate registered gates from primitive evidence; caller booleans are impossible."""
    if SHA_RE.fullmatch(candidate) is None:
        return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "invalid_exact_sha"}
    if candidate in SYNTHETIC_INVALIDATED_SHAS:
        return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "synthetic_authority_quarantined"}
    try:
        _git(repo, "cat-file", "-e", candidate + "^{commit}")
        if _git(repo, "rev-parse", "HEAD") != candidate:
            return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "candidate_not_checked_out"}
        if _git(repo, "status", "--porcelain"):
            return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "candidate_tree_dirty"}
        current = store.read()
        if current is None:
            return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "certified_release_uninitialized"}
        if current.get("certified_live_sha") in SYNTHETIC_INVALIDATED_SHAS:
            return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": "synthetic_authority_quarantined"}
        base = current["certified_live_sha"]
        changed = [] if base == candidate else _git(repo, "diff", "--name-only", base, candidate).splitlines()
        impact = classify(changed, graph); gates = impact["required_gates"]
        if primitive_root is None or primitive_manifest is None:
            return {"candidate_sha": candidate, "base_sha": base, "required_gates": gates, "verdict": "BLOCKED", "blocker": "governed_primitives_required"}
        if set(primitive_manifest) != set(gates):
            return {"candidate_sha": candidate, "base_sha": base, "required_gates": gates, "verdict": "BLOCKED", "blocker": "primitive_gate_set_mismatch"}
        evaluations = []
        for gate in gates:
            primitive = _primitive(Path(primitive_root), gate, candidate, primitive_manifest, repo)
            passed = _predicate(gate, primitive["payload"], repo, candidate)
            version = primitive["payload"].get("evaluator_version", EVALUATOR_VERSION)
            evaluations.append({"gate": gate, "evaluator": gate, "evaluator_version": version,
                                "primitive_path": primitive["path"], "primitive_sha256": primitive["sha256"],
                                "observed": primitive["payload"]["observed"],
                                "status": "PASS" if passed else "FAIL", "recomputed_result": "PASS" if passed else "FAIL",
                                "evaluated_at": datetime.now(timezone.utc).isoformat()})
        hashes = [entry["primitive_sha256"] for entry in evaluations]
        if len(hashes) != len(set(hashes)):
            return {"candidate_sha": candidate, "base_sha": base, "required_gates": gates, "verdict": "BLOCKED", "blocker": "primitive_reused_across_gates"}
        passed = [entry["gate"] for entry in evaluations if entry["recomputed_result"] == "PASS"]
        failed = [entry["gate"] for entry in evaluations if entry["recomputed_result"] != "PASS"]
        result: dict[str, Any] = {"schema_version": 2, "candidate_sha": candidate, "base_sha": base,
                                  "fallback_sha": base, "changed_paths": changed, "change_impact": impact["impact"],
                                  "dependency_graph_sha256": dependency_graph_digest(graph),
                                  "required_gates": gates, "gate_evaluations": evaluations,
                                  "passed_gates": passed, "failed_gates": failed,
                                  "verdict": "PASS" if not failed else "FAIL"}
        result["certification_sha256"] = digest(result)
        return result
    except (subprocess.CalledProcessError, ReleaseStoreError, ValueError, OSError) as exc:
        return {"candidate_sha": candidate, "verdict": "BLOCKED", "blocker": str(exc)}


def validate_certification_result(result: Mapping[str, Any], current: Mapping[str, Any] | None) -> None:
    if not isinstance(result, dict) or result.get("schema_version") != 2 or result.get("verdict") != "PASS":
        raise ReleaseStoreError("promotion_requires_governed_pass_certification")
    if current is None or result.get("base_sha") != current.get("certified_live_sha") or result.get("fallback_sha") != current.get("certified_live_sha") or not re.fullmatch(r"[0-9a-f]{64}", str(result.get("dependency_graph_sha256", ""))):
        raise ReleaseStoreError("promotion_base_mismatch")
    required, passed, failed, evaluations = result.get("required_gates"), result.get("passed_gates"), result.get("failed_gates"), result.get("gate_evaluations")
    if not isinstance(required, list) or not required or len(required) != len(set(required)) or set(passed or ()) != set(required) or failed not in ([], ()):
        raise ReleaseStoreError("promotion_requires_all_governed_gates")
    if not isinstance(evaluations, list) or {item.get("gate") for item in evaluations if isinstance(item, dict)} != set(required):
        raise ReleaseStoreError("promotion_requires_gate_evaluations")
    claimed = result.get("certification_sha256"); unsigned = dict(result); unsigned.pop("certification_sha256", None)
    if claimed != digest(unsigned):
        raise ReleaseStoreError("certification_hash_mismatch")


def promote(result: Mapping[str, Any], store: ReleaseStore, attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Promotion requires an independently generated, candidate-bound attestation."""
    current = store.read(); validate_certification_result(result, current)
    binding = {"candidate_sha": result["candidate_sha"], "required_gates": result["required_gates"],
               "evidence_hashes": [item["primitive_sha256"] for item in result["gate_evaluations"]],
               "dependency_graph_sha256": result["dependency_graph_sha256"],
               "certification_sha256": result["certification_sha256"]}
    if isinstance(attestation, dict) and "attestation" in attestation:
        if attestation.get("independent_release_verifier_pass") is not True:
            raise ReleaseStoreError("promotion_requires_independent_attestation")
        attestation = attestation["attestation"]
    if not isinstance(attestation, dict) or attestation.get("binding_sha256") != digest(binding) or attestation.get("verdict") != "PASS" or attestation.get("verifier") != "verify_release_manager_v2":
        raise ReleaseStoreError("promotion_requires_independent_attestation")
    event = store.record_verified_selection(candidate_sha=result["candidate_sha"], evidence_sha256=result["certification_sha256"], expected_event=current["event_sha256"])
    return {"promotion_status": "PROMOTED", **event}
