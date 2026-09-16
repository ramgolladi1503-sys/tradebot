#!/usr/bin/env python3
"""Adversarial primitive mutations for the release trust boundary (read-only)."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore
from core.release_certification import certify, digest
from core.release_change_impact import DependencyEvidence
from core.release_gate_registry import EVALUATOR_VERSION_V2
from scripts.verify_release_manager import verify


def _commit(repo: Path, text: str) -> str:
    (repo / "x.md").write_text(text); subprocess.run(["git", "-C", str(repo), "add", "x.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", text], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _context(root: Path):
    repo = root / "repo"; repo.mkdir(parents=True); subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base, candidate = _commit(repo, "base"), _commit(repo, "candidate")
    store = ReleaseStore(root / "state"); store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)
    graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)
    graph_path = root / "graph.json"; graph_path.write_text(json.dumps({"edges": {"x.md": []}, "critical_roots": [], "bounded_roots": [], "complete": True}))
    primitive_root = root / "primitives"; primitive_root.mkdir(); manifest = {}
    for gate in ["diff_check", "release_verifier", "source_identity", "whole_tree_compile"]:
        raw_stdout = f"raw_output_for_{gate}\n"
        stdout_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        (primitive_root / f"{gate}.stdout").write_text(raw_stdout, encoding="utf-8")
        if gate == "source_identity":
            observed = {"command": f"git cat-file -e {candidate}^{{commit}}", "exit_code": 0, "commit_exists": True, "head_sha": candidate, "raw_stdout_sha256": stdout_hash}
        elif gate == "diff_check":
            observed = {"command": "git diff --check", "exit_code": 0, "raw_stdout_sha256": stdout_hash, "whitespace_clean": True}
        elif gate == "whole_tree_compile":
            observed = {"command": "python3 -m compileall", "exit_code": 0, "raw_stdout_sha256": stdout_hash, "compiled_modules_count": 10}
        elif gate == "release_verifier":
            observed = {"command": "pytest tests/test_release_certification.py", "exit_code": 0, "raw_stdout_sha256": stdout_hash, "verifier_pass": True}
        path = primitive_root / f"{gate}.json"
        path.write_text(json.dumps({
            "gate": gate, "candidate_sha": candidate, "source_sha": candidate,
            "evaluator": gate, "evaluator_version": EVALUATOR_VERSION_V2,
            "captured_at": datetime.now(timezone.utc).isoformat(), "observed": observed
        }))
        manifest[gate] = path.name
    manifest_path = root / "manifest.json"; manifest_path.write_text(json.dumps(manifest))
    cert = certify(repo, candidate, store, graph, primitive_root, manifest); cert_path = root / "cert.json"; cert_path.write_text(json.dumps(cert))
    return repo, base, candidate, store, graph, graph_path, primitive_root, manifest, manifest_path, cert, cert_path


def _case(mid: str, detected: bool) -> dict:
    return {"mutation_id": mid, "detected": bool(detected), "test_or_harness": "scripts/release_manager_mutation_campaign.py", "read_only": True}


def run_campaign() -> dict:
    cases = []
    with tempfile.TemporaryDirectory(prefix="release-trust-mutations-") as temp:
        root = Path(temp)
        # Each mutation alters an actual primitive, certificate, graph, or journal.
        c = _context(root / "m01")
        try: certify(c[0], c[2], c[3], c[4], gate_runner=lambda _: True); detected = False
        except TypeError: detected = True
        cases.append(_case("M01", detected))
        c = _context(root / "m02"); p = c[6] / "diff_check.json"; x = json.loads(p.read_text()); x["pass"] = True; p.write_text(json.dumps(x)); cases.append(_case("M02", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] == "BLOCKED"))
        c = _context(root / "m03"); c[7]["whole_tree_compile"] = c[7]["diff_check"]; cases.append(_case("M03", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] == "BLOCKED"))
        c = _context(root / "m04"); (c[6] / "diff_check.json").write_text("{}"); cases.append(_case("M04", not verify(c[3].root, repo=c[0], certification=c[10], dependency_graph=c[5], primitive_root=c[6], primitive_manifest=c[8])["independent_release_verifier_pass"]))
        c = _context(root / "m05"); p = c[6] / "source_identity.json"; x = json.loads(p.read_text()); x["candidate_sha"] = "a" * 40; p.write_text(json.dumps(x)); cases.append(_case("M05", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] == "BLOCKED"))
        c = _context(root / "m06"); cases.append(_case("M06", certify(c[0], c[1], c[3], c[4], c[6], c[7]).get("blocker") == "candidate_not_checked_out"))
        c = _context(root / "m07"); (c[6] / "whole_tree_compile.json").unlink(); cases.append(_case("M07", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] == "BLOCKED"))
        c = _context(root / "m08"); p = c[6] / "diff_check.json"; x = json.loads(p.read_text()); x["evaluator"] = "unknown"; p.write_text(json.dumps(x)); cases.append(_case("M08", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] == "BLOCKED"))
        c = _context(root / "m09"); p = c[6] / "release_verifier.json"; x = json.loads(p.read_text()); x["observed"]["command"] = "forged:release_verifier"; p.write_text(json.dumps(x)); cases.append(_case("M09", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] != "PASS"))
        c = _context(root / "m10"); c[5].write_text(json.dumps({"edges": {}, "critical_roots": [], "bounded_roots": [], "complete": False})); cases.append(_case("M10", not verify(c[3].root, repo=c[0], certification=c[10], dependency_graph=c[5], primitive_root=c[6], primitive_manifest=c[8])["independent_release_verifier_pass"]))
        c = _context(root / "m11"); x = json.loads(c[10].read_text()); x["candidate_sha"] = "a" * 40; c[10].write_text(json.dumps(x)); cases.append(_case("M11", not verify(c[3].root, repo=c[0], certification=c[10], dependency_graph=c[5], primitive_root=c[6], primitive_manifest=c[8])["independent_release_verifier_pass"]))
        c = _context(root / "m12"); (c[3].root / "current.json").write_text(json.dumps({"event_sha256": "0" * 64})); cases.append(_case("M12", not verify(c[3].root, repo=c[0], certification=c[10], dependency_graph=c[5], primitive_root=c[6], primitive_manifest=c[8])["independent_release_verifier_pass"]))
        c = _context(root / "m13"); c[7].pop("diff_check"); cases.append(_case("M13", certify(c[0], c[2], c[3], c[4], c[6], c[7])["verdict"] == "BLOCKED"))
        c = _context(root / "m14"); x = json.loads(c[10].read_text()); x["required_gates"].append("diff_check"); x["certification_sha256"] = digest({k: v for k, v in x.items() if k != "certification_sha256"}); c[10].write_text(json.dumps(x)); cases.append(_case("M14", not verify(c[3].root, repo=c[0], certification=c[10], dependency_graph=c[5], primitive_root=c[6], primitive_manifest=c[8])["independent_release_verifier_pass"]))
        c = _context(root / "m15"); p = c[6] / "diff_check.json"; x = json.loads(p.read_text()); x["observed"]["exit_code"] = 1; p.write_text(json.dumps(x)); cases.append(_case("M15", not verify(c[3].root, repo=c[0], certification=c[10], dependency_graph=c[5], primitive_root=c[6], primitive_manifest=c[8])["independent_release_verifier_pass"]))
    detected = sum(item["detected"] for item in cases)
    return {"campaign": "release_manager_v2_mutation_campaign", "cases": cases, "total": len(cases), "detected": detected, "pass": detected == len(cases), "release_manager_mutations_detected": f"{detected}/{len(cases)}", "mandatory_mutation_classes_detected": f"{detected}/15", "read_only": True, "broker_api_called": False, "broker_write_authority": False, "order_authority": False, "paper_authorized": False, "live_authorized": False, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = run_campaign()
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end=""); return 0 if result["pass"] else 2


if __name__ == "__main__": raise SystemExit(main())
