import hashlib
import json
from datetime import datetime, timezone
import subprocess

from core.certified_release_store import ReleaseStore
from core.release_certification import certify
from core.release_change_impact import DependencyEvidence
from core.release_gate_registry import EVALUATOR_VERSION_V2
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
        raw_stdout = f"raw_output_for_{gate}\n"
        stdout_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        (root / f"{gate}.stdout").write_text(raw_stdout, encoding="utf-8")
        if gate == "source_identity":
            observed = {"command": f"git cat-file -e {candidate}^{{commit}}", "exit_code": 0, "commit_exists": True, "head_sha": candidate, "raw_stdout_sha256": stdout_hash}
        elif gate == "diff_check":
            observed = {"command": "git diff --check", "exit_code": 0, "raw_stdout_sha256": stdout_hash, "whitespace_clean": True}
        elif gate == "whole_tree_compile":
            observed = {"command": "python3 -m compileall", "exit_code": 0, "raw_stdout_sha256": stdout_hash, "compiled_modules_count": 10}
        elif gate == "release_verifier":
            observed = {"command": "pytest tests/test_release_certification.py", "exit_code": 0, "raw_stdout_sha256": stdout_hash, "verifier_pass": True}
        path = root / f"{gate}.json"
        path.write_text(json.dumps({
            "gate": gate, "candidate_sha": candidate, "source_sha": candidate,
            "evaluator": gate, "evaluator_version": EVALUATOR_VERSION_V2,
            "captured_at": datetime.now(timezone.utc).isoformat(), "observed": observed
        }))
        manifest[gate] = path.name
    manifest_path = tmp_path / "manifest.json"; manifest_path.write_text(json.dumps(manifest))
    graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)
    cert = certify(repo, candidate, store, graph, root, manifest); cert_path = tmp_path / "cert.json"; cert_path.write_text(json.dumps(cert))
    result = verify(store.root, repo=repo, certification=cert_path, dependency_graph=graph_path, primitive_root=root, primitive_manifest=manifest_path)
    assert result["independent_release_verifier_pass"] is True
    assert result["attestation"]["binding_sha256"]
    (root / "diff_check.json").write_text("{}")
    assert verify(store.root, repo=repo, certification=cert_path, dependency_graph=graph_path, primitive_root=root, primitive_manifest=manifest_path)["independent_release_verifier_pass"] is False
