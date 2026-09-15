import json
from datetime import datetime, timezone
import subprocess

from core.certified_release_store import ReleaseStore
from core.release_certification import EVALUATOR_VERSION, certify
from core.release_change_impact import DependencyEvidence
from scripts.verify_release_manager import verify


def _commit(repo, name, text):
    (repo / name).write_text(text); subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", name], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def test_independent_verifier_recomputes_primitives_and_binds_attestation(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base, candidate = _commit(repo, "x.md", "one"), _commit(repo, "x.md", "two")
    store = ReleaseStore(tmp_path / "state"); store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)
    graph_path = tmp_path / "graph.json"; graph_path.write_text(json.dumps({"edges": {"x.md": []}, "critical_roots": [], "bounded_roots": [], "complete": True}))
    root = tmp_path / "primitives"; root.mkdir(); manifest = {}
    for gate in ["diff_check", "release_verifier", "source_identity", "whole_tree_compile"]:
        observed = {"commit_exists": True} if gate == "source_identity" else {"command": f"governed:{gate}", "exit_code": 0}
        path = root / f"{gate}.json"; path.write_text(json.dumps({"gate": gate, "candidate_sha": candidate, "source_sha": candidate, "evaluator": gate, "evaluator_version": EVALUATOR_VERSION, "captured_at": datetime.now(timezone.utc).isoformat(), "observed": observed})); manifest[gate] = path.name
    manifest_path = tmp_path / "manifest.json"; manifest_path.write_text(json.dumps(manifest))
    graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)
    cert = certify(repo, candidate, store, graph, root, manifest); cert_path = tmp_path / "cert.json"; cert_path.write_text(json.dumps(cert))
    result = verify(store.root, repo=repo, certification=cert_path, dependency_graph=graph_path, primitive_root=root, primitive_manifest=manifest_path)
    assert result["independent_release_verifier_pass"] is True
    assert result["attestation"]["binding_sha256"]
    (root / "diff_check.json").write_text("{}")
    assert verify(store.root, repo=repo, certification=cert_path, dependency_graph=graph_path, primitive_root=root, primitive_manifest=manifest_path)["independent_release_verifier_pass"] is False
