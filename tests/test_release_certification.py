import hashlib
import json
from datetime import datetime, timezone
import subprocess

from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import EVALUATOR_VERSION, certify, digest, promote
from core.release_change_impact import DependencyEvidence
from core.release_gate_registry import EVALUATOR_VERSION_V2


def _commit(repo, text):
    (repo / "x.md").write_text(text); subprocess.run(["git", "-C", str(repo), "add", "x.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", text], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _fixture(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base, candidate = _commit(repo, "x=1\n"), _commit(repo, "x=2\n")
    store = ReleaseStore(tmp_path / "state"); store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)
    graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)
    root = tmp_path / "p"; root.mkdir(); manifest = {}
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
        payload = {
            "gate": gate,
            "candidate_sha": candidate,
            "source_sha": candidate,
            "evaluator": gate,
            "evaluator_version": EVALUATOR_VERSION_V2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "observed": observed,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        manifest[gate] = path.name
    return repo, candidate, store, graph, root, manifest


def test_lambda_true_cannot_be_authority(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path)
    try:
        certify(repo, candidate, store, graph, gate_runner=lambda _: True)
    except TypeError:
        pass
    else:
        raise AssertionError("callback accepted")
    assert certify(repo, candidate, store, graph)["blocker"] == "governed_primitives_required"


def test_generic_pass_and_candidate_mismatch_block(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path)
    path = root / "diff_check.json"; payload = json.loads(path.read_text()); payload["pass"] = True; path.write_text(json.dumps(payload))
    assert certify(repo, candidate, store, graph, root, manifest)["verdict"] == "BLOCKED"
    payload.pop("pass"); payload["candidate_sha"] = "a" * 40; path.write_text(json.dumps(payload))
    assert certify(repo, candidate, store, graph, root, manifest)["blocker"] == "gate_primitive_candidate_mismatch"


def test_stale_primitive_is_blocked(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path)
    path = root / "diff_check.json"; payload = json.loads(path.read_text()); payload["captured_at"] = "1970-01-01T00:00:00+00:00"; path.write_text(json.dumps(payload))
    assert certify(repo, candidate, store, graph, root, manifest)["blocker"] == "gate_primitive_stale"


def test_promotion_requires_bound_attestation(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path); result = certify(repo, candidate, store, graph, root, manifest)
    try:
        promote(result, store, {"verdict": "PASS"})
    except ReleaseStoreError as exc:
        assert str(exc) == "promotion_requires_independent_attestation"
    else:
        raise AssertionError("unbound attestation promoted")


def test_known_synthetic_authority_is_quarantined_without_rewriting_history(tmp_path):
    from core.release_certification import SYNTHETIC_INVALIDATED_SHAS
    assert "93934d7c040b338b840eabd72e575644eaa3fbc0" in SYNTHETIC_INVALIDATED_SHAS
    store = ReleaseStore(tmp_path / "state")
    store.record_verified_selection(candidate_sha="a" * 40, evidence_sha256="e" * 64, expected_event=None)
    assert store.read()["certified_live_sha"] == "a" * 40


def test_bound_independent_attestation_allows_promotion(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path)
    result = certify(repo, candidate, store, graph, root, manifest)
    binding = {"candidate_sha": result["candidate_sha"], "required_gates": result["required_gates"],
               "evidence_hashes": [item["primitive_sha256"] for item in result["gate_evaluations"]],
               "dependency_graph_sha256": result["dependency_graph_sha256"],
               "certification_sha256": result["certification_sha256"]}
    promoted = promote(result, store, {"verdict": "PASS", "verifier": "verify_release_manager_v2", "binding_sha256": digest(binding)})
    assert promoted["promotion_status"] == "PROMOTED"


def test_v1_evaluator_version_quarantined(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path)
    p = root / "diff_check.json"
    data = json.loads(p.read_text())
    data["evaluator_version"] = EVALUATOR_VERSION
    p.write_text(json.dumps(data))
    assert certify(repo, candidate, store, graph, root, manifest)["blocker"] == "v1_evaluator_version_quarantined"


def test_raw_stdout_missing_or_mismatched_blocks(tmp_path):
    repo, candidate, store, graph, root, manifest = _fixture(tmp_path)
    (root / "diff_check.stdout").unlink()
    assert certify(repo, candidate, store, graph, root, manifest)["blocker"] == "raw_execution_output_unverified"
    (root / "diff_check.stdout").write_text("corrupted_output")
    assert certify(repo, candidate, store, graph, root, manifest)["blocker"] == "raw_execution_output_unverified"
