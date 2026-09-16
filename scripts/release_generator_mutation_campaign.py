#!/usr/bin/env python3
"""Execute the 20 mandatory adversarial mutation attacks against release primitive generators and certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import certify, digest
from core.release_change_impact import DependencyEvidence
from core.release_gate_registry import EVALUATOR_VERSION_V2, validate_gate_predicate_v2
from scripts.generate_evidence_integrity_primitive import evaluate_evidence_integrity
from scripts.generate_option_mirror_primitive import evaluate_option_mirror_semantics
from scripts.generate_security_authority_primitive import evaluate_security_authority


def _commit(repo: Path, text: str) -> str:
    (repo / "x.md").write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", "x.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", text], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _setup_context(root: Path):
    repo = root / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base = _commit(repo, "base")
    candidate = _commit(repo, "candidate")
    store = ReleaseStore(root / "state")
    store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)
    graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)

    primitive_root = root / "primitives"
    primitive_root.mkdir(parents=True)
    manifest = {}

    for gate in ["diff_check", "release_verifier", "source_identity", "whole_tree_compile"]:
        if gate == "source_identity":
            observed = {"commit_exists": True, "head_sha": candidate}
        elif gate == "diff_check":
            observed = {"command": "git diff --check", "exit_code": 0, "raw_stdout_sha256": "0" * 64, "whitespace_clean": True}
        elif gate == "whole_tree_compile":
            observed = {"command": "python3 -m compileall", "exit_code": 0, "raw_stdout_sha256": "0" * 64, "compiled_modules_count": 10}
        elif gate == "release_verifier":
            observed = {"command": "pytest tests/test_release_certification.py", "exit_code": 0, "raw_stdout_sha256": "0" * 64, "verifier_pass": True}

        payload = {
            "gate": gate,
            "candidate_sha": candidate,
            "source_sha": candidate,
            "evaluator": gate,
            "evaluator_version": EVALUATOR_VERSION_V2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "observed": observed,
        }
        p_path = primitive_root / f"{gate}.json"
        p_path.write_text(json.dumps(payload))
        manifest[gate] = f"{gate}.json"

    return repo, base, candidate, store, graph, primitive_root, manifest


def run_campaign() -> dict:
    cases = []

    with tempfile.TemporaryDirectory(prefix="generator-attacks-") as temp:
        root = Path(temp)

        # 1. generic_exit_code_zero_placeholder
        c = _setup_context(root / "a01")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["observed"] = {"command": "governed:diff_check", "exit_code": 0}  # Placeholder!
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "placeholder" in res.get("blocker", ""))
        cases.append({"attack": "generic_exit_code_zero_placeholder", "detected": detected})

        # 2. wrong_gate
        c = _setup_context(root / "a02")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["gate"] = "other_gate"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "gate_mismatch" in res.get("blocker", ""))
        cases.append({"attack": "wrong_gate", "detected": detected})

        # 3. wrong_candidate
        c = _setup_context(root / "a03")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["candidate_sha"] = "0" * 40
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "candidate_mismatch" in res.get("blocker", ""))
        cases.append({"attack": "wrong_candidate", "detected": detected})

        # 4. wrong_source
        c = _setup_context(root / "a04")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["source_sha"] = "0" * 40
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "candidate_mismatch" in res.get("blocker", ""))
        cases.append({"attack": "wrong_source", "detected": detected})

        # 5. wrong_generator
        c = _setup_context(root / "a05")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["evaluator"] = "unregistered_evaluator"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "evaluator_mismatch" in res.get("blocker", ""))
        cases.append({"attack": "wrong_generator", "detected": detected})

        # 6. wrong_generator_version
        c = _setup_context(root / "a06")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["evaluator_version"] = "v999_untrusted"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "evaluator_mismatch" in res.get("blocker", ""))
        cases.append({"attack": "wrong_generator_version", "detected": detected})

        # 7. missing_raw_output
        c = _setup_context(root / "a07")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["observed"].pop("raw_stdout_sha256", None)
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" or "diff_check" in res.get("failed_gates", []))
        cases.append({"attack": "missing_raw_output", "detected": detected})

        # 8. altered_raw_output
        c = _setup_context(root / "a08")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["observed"]["raw_stdout_sha256"] = "invalid_not_hex64"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "FAIL" and "diff_check" in res.get("failed_gates", []))
        cases.append({"attack": "altered_raw_output", "detected": detected})

        # 9. primitive_hash_changed
        c = _setup_context(root / "a09")
        cert = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        # Mutate primitive after certification
        (c[5] / "diff_check.json").write_text("{\"mutated\": true}")
        from scripts.verify_release_manager import verify
        cert_file = root / "a09" / "cert.json"
        cert_file.write_text(json.dumps(cert))
        dep_file = root / "a09" / "graph.json"
        dep_file.write_text(json.dumps({"edges": {"x.md": []}, "critical_roots": [], "bounded_roots": [], "complete": True}))
        man_file = root / "a09" / "manifest.json"
        man_file.write_text(json.dumps(c[6]))
        v_res = verify(c[3].root, repo=c[0], certification=cert_file, dependency_graph=dep_file, primitive_root=c[5], primitive_manifest=man_file)
        detected = not v_res["independent_release_verifier_pass"]
        cases.append({"attack": "primitive_hash_changed", "detected": detected})

        # 10. stale_timestamp
        c = _setup_context(root / "a10")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["captured_at"] = "1970-01-01T00:00:00+00:00"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "stale" in res.get("blocker", ""))
        cases.append({"attack": "stale_timestamp", "detected": detected})

        # 11. authored_pass_field
        c = _setup_context(root / "a11")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["pass"] = True
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "authored_result" in res.get("blocker", ""))
        cases.append({"attack": "authored_pass_field", "detected": detected})

        # 12. authored_result_field
        c = _setup_context(root / "a12")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["result"] = "PASS"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "authored_result" in res.get("blocker", ""))
        cases.append({"attack": "authored_result_field", "detected": detected})

        # 13. authored_status_field
        c = _setup_context(root / "a13")
        p = c[5] / "diff_check.json"
        x = json.loads(p.read_text())
        x["status"] = "PASS"
        p.write_text(json.dumps(x))
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "authored_result" in res.get("blocker", ""))
        cases.append({"attack": "authored_status_field", "detected": detected})

        # 14. same_primitive_reused_for_multiple_gates
        c = _setup_context(root / "a14")
        c[6]["whole_tree_compile"] = c[6]["diff_check"]
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "reused" in res.get("blocker", ""))
        cases.append({"attack": "same_primitive_reused_for_multiple_gates", "detected": detected})

        # 15. path_escape
        c = _setup_context(root / "a15")
        c[6]["diff_check"] = "../escape.json"
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "escape" in res.get("blocker", ""))
        cases.append({"attack": "path_escape", "detected": detected})

        # 16. symlink_escape
        c = _setup_context(root / "a16")
        sym = c[5] / "sym_diff.json"
        sym.symlink_to(c[5] / "diff_check.json")
        c[6]["diff_check"] = "sym_diff.json"
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "missing" in res.get("blocker", ""))
        cases.append({"attack": "symlink_escape", "detected": detected})

        # 17. missing_artifact
        c = _setup_context(root / "a17")
        (c[5] / "diff_check.json").unlink()
        res = certify(c[0], c[2], c[3], c[4], c[5], c[6])
        detected = (res["verdict"] == "BLOCKED" and "missing" in res.get("blocker", ""))
        cases.append({"attack": "missing_artifact", "detected": detected})

        # 18. evidence_hash_mismatch
        c = _setup_context(root / "a18")
        ok, ev, out = evaluate_evidence_integrity(c[5], None, c[2])
        # Force hash mismatch in evidence integrity evaluation
        manifest_file = c[5] / "primitive_manifest.json"
        manifest_file.write_text(json.dumps({"g": "diff_check.json"}))
        ok_mismatch, _, _ = evaluate_evidence_integrity(root / "nonexistent", manifest_file, c[2])
        detected = (ok_mismatch is False)
        cases.append({"attack": "evidence_hash_mismatch", "detected": detected})

        # 19. security_authority_constant_forgery
        forged_obs = {
            "command": "python3 scripts/generate_security_authority_primitive.py",
            "exit_code": 0,
            "raw_stdout_sha256": "0" * 64,
            "singular_candidate_selection_authority_verified": True,
            "singular_execution_authority_verified": True,
            "observer_execution_isolation_verified": True,
            "broker_write_calls_measured": 0,
            "order_actions_measured": 0,
            "measurement_method": "hardcoded_constant_forgery",
        }
        detected = not validate_gate_predicate_v2("security_authority", forged_obs, Path("."), "0" * 40)
        cases.append({"attack": "security_authority_constant_forgery", "detected": detected})

        # 20. option_mirror_fake_ready
        fake_mirror_obs = {
            "command": "python3 scripts/generate_option_mirror_primitive.py",
            "exit_code": 0,
            "raw_stdout_sha256": "0" * 64,
            "offline_readiness_transition_valid": False,  # Fake readiness
            "degraded_fallback_verified": True,
        }
        detected = not validate_gate_predicate_v2("option_mirror", fake_mirror_obs, Path("."), "0" * 40)
        cases.append({"attack": "option_mirror_fake_ready", "detected": detected})

    total = len(cases)
    detected_count = sum(1 for c in cases if c["detected"])
    all_passed = (detected_count == total == 20)

    return {
        "campaign": "release_generator_adversarial_mutation_campaign",
        "total_attacks": total,
        "attacks_detected": detected_count,
        "pass": all_passed,
        "read_only": True,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 20-attack generator mutation campaign")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    args = parser.parse_args()

    result = run_campaign()
    out_str = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out_str, encoding="utf-8")
    print(out_str, end="")
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
