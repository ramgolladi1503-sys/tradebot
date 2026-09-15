#!/usr/bin/env python3
"""Independent, read-only verification of governed release certification."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import SYNTHETIC_INVALIDATED_SHAS, certify, dependency_graph_digest, digest
from core.release_change_impact import DependencyEvidence

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _graph(path: Path) -> DependencyEvidence:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DependencyEvidence(edges={key: frozenset(value) for key, value in payload["edges"].items()},
                              critical_roots=frozenset(payload["critical_roots"]),
                              bounded_roots=frozenset(payload["bounded_roots"]), complete=bool(payload["complete"]),
                              unresolved=frozenset(payload.get("unresolved", [])))


def _manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "gates" in payload:
        raise ReleaseStoreError("primitive_manifest_invalid")
    return payload


def _commit_exists(repo: Path, sha: object) -> bool:
    return isinstance(sha, str) and SHA_RE.fullmatch(sha) is not None and subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _binding(result: dict) -> dict:
    return {"candidate_sha": result["candidate_sha"], "required_gates": result["required_gates"],
            "evidence_hashes": [item["primitive_sha256"] for item in result["gate_evaluations"]],
            "certification_sha256": result["certification_sha256"]}


def verify(root: Path, *, repo: Path, certification: Path, dependency_graph: Path,
           primitive_root: Path, primitive_manifest: Path) -> dict:
    checks = {"release_history_readable": False, "candidate_commit_exists": False,
              "certification_hash_valid": False, "required_gates_recomputed": False,
              "primitive_hashes_current": False, "attestation_bound": False}
    safety = {"read_only": True, "broker_api_called": False, "broker_write_authority": False,
              "order_authority": False, "paper_authorized": False, "live_authorized": False,
              "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0}
    try:
        current = ReleaseStore(root).read()
        checks["release_history_readable"] = current is not None and current.get("schema_version") == 1
        if current and current.get("certified_live_sha") in SYNTHETIC_INVALIDATED_SHAS:
            raise ReleaseStoreError("synthetic_authority_quarantined")
        result = json.loads(certification.read_text(encoding="utf-8"))
        unsigned = dict(result); claimed = unsigned.pop("certification_sha256", None)
        checks["certification_hash_valid"] = claimed == digest(unsigned)
        if not checks["certification_hash_valid"]: raise ReleaseStoreError("certification_hash_mismatch")
        candidate = result.get("candidate_sha")
        checks["candidate_commit_exists"] = _commit_exists(repo, candidate)
        if not checks["candidate_commit_exists"]: raise ReleaseStoreError("candidate_commit_missing")
        # Re-run repository-owned evaluators; do not read any claimed PASS list.
        graph = _graph(dependency_graph)
        recomputed = certify(repo, candidate, ReleaseStore(root), graph, primitive_root, _manifest(primitive_manifest))
        checks["required_gates_recomputed"] = (
            recomputed.get("verdict") == "PASS"
            and recomputed.get("candidate_sha") == result.get("candidate_sha")
            and recomputed.get("base_sha") == result.get("base_sha")
            and recomputed.get("fallback_sha") == result.get("fallback_sha")
            and recomputed.get("changed_paths") == result.get("changed_paths")
            and recomputed.get("change_impact") == result.get("change_impact")
            and recomputed.get("required_gates") == result.get("required_gates")
            and recomputed.get("passed_gates") == result.get("passed_gates")
            and result.get("dependency_graph_sha256") == dependency_graph_digest(graph)
        )
        if not checks["required_gates_recomputed"]: raise ReleaseStoreError("required_gate_recomputation_failed")
        original = {item["gate"]: item["primitive_sha256"] for item in result.get("gate_evaluations", []) if isinstance(item, dict)}
        observed = {item["gate"]: item["primitive_sha256"] for item in recomputed.get("gate_evaluations", []) if isinstance(item, dict)}
        original_status = {item["gate"]: (item.get("status"), item.get("recomputed_result")) for item in result.get("gate_evaluations", []) if isinstance(item, dict)}
        observed_status = {item["gate"]: (item.get("status"), item.get("recomputed_result")) for item in recomputed.get("gate_evaluations", []) if isinstance(item, dict)}
        checks["primitive_hashes_current"] = original == observed and original_status == observed_status and set(original) == set(result["required_gates"])
        if not checks["primitive_hashes_current"]: raise ReleaseStoreError("primitive_hash_mismatch")
        attestation = {"verdict": "PASS", "verifier": "verify_release_manager_v2", "binding_sha256": digest(_binding(result))}
        checks["attestation_bound"] = True
        return {"independent_release_verifier_pass": all(checks.values()), "checks": checks,
                "attestation": attestation, "current": current, **safety}
    except (ReleaseStoreError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        return {"independent_release_verifier_pass": False, "checks": checks, "blocker": str(exc), **safety}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("root", type=Path); parser.add_argument("--repo", type=Path, required=True); parser.add_argument("--certification", type=Path, required=True); parser.add_argument("--dependency-graph", type=Path, required=True); parser.add_argument("--primitive-root", type=Path, required=True); parser.add_argument("--primitive-manifest", type=Path, required=True); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = verify(args.root, repo=args.repo, certification=args.certification, dependency_graph=args.dependency_graph, primitive_root=args.primitive_root, primitive_manifest=args.primitive_manifest)
    if args.output: args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result["independent_release_verifier_pass"] else 2


if __name__ == "__main__": raise SystemExit(main())
