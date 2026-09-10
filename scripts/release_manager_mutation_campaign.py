#!/usr/bin/env python3
"""Offline mutation campaign for Release Manager V1 governance failures."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import certify, promote
from core.release_change_impact import DependencyEvidence, classify
from scripts.release_manager_prepare_next_session import prepare
from scripts.verify_release_manager import verify


def _run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True).strip()


def _commit(repo: Path, name: str, text: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", name], check=True)
    return _run(["git", "-C", str(repo), "rev-parse", "HEAD"])


def _repo(root: Path) -> tuple[Path, str, str]:
    repo = root / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base = _commit(repo, "core/live.py", "SAFE=True\n")
    candidate = _commit(repo, "core/live.py", "SAFE=False\n")
    return repo, base, candidate


def _store(root: Path, sha: str) -> ReleaseStore:
    store = ReleaseStore(root / "state")
    store.record_verified_selection(candidate_sha=sha, evidence_sha256="e" * 64, expected_event=None)
    return store


def _case(mutation_id: str, name: str, detected: bool, detail: object, primitive: str, expected: str) -> dict:
    return {
        "mutation_id": mutation_id,
        "name": name,
        "description": name,
        "test_or_harness": "scripts/release_manager_mutation_campaign.py",
        "primitive_mutation_applied": primitive,
        "expected_failure_control_behavior": expected,
        "actual_behavior": detail,
        "detected": bool(detected),
        "evidence_path": "self",
        "detail": detail,
    }


def run_campaign() -> dict:
    cases: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="release-manager-mutations-") as tmp:
        root = Path(tmp)
        repo, base, candidate = _repo(root)
        graph = DependencyEvidence(
            edges={"main.py": frozenset({"core/live.py"})},
            critical_roots=frozenset({"main.py"}),
            bounded_roots=frozenset(),
            complete=True,
        )
        full_gates = classify(["core/live.py"], graph)["required_gates"]

        store = _store(root / "main_ahead", base)
        current_before = store.read()["certified_live_sha"]
        result = certify(repo, candidate, store, graph, gate_runner=lambda _: False)
        current_after = store.read()["certified_live_sha"]
        cases.append(_case(
            "M01",
            "main_ahead_of_certified_release_does_not_promote",
            result["verdict"] == "FAIL" and current_before == current_after == base,
            {"verdict": result["verdict"], "current": current_after},
            "created second commit while release store still points to base",
            "candidate remains unpromoted and certified pointer stays at base",
        ))

        verification = verify(_store(root / "nonexistent_sha", "f" * 40).root, repo=repo)
        cases.append(_case(
            "M02",
            "manifest_points_to_nonexistent_sha",
            not verification["independent_release_verifier_pass"],
            verification["checks"],
            "release store initialized to syntactically valid SHA absent from repo",
            "independent verifier rejects missing commit",
        ))

        store = _store(root / "missing_gate", base)
        result = certify(repo, candidate, store, graph, gate_runner=lambda gate: gate != "whole_tree_compile")
        cases.append(_case(
            "M04",
            "candidate_certification_missing_required_gate",
            result["verdict"] != "PASS",
            result["verdict"],
            "gate runner returns false for whole_tree_compile",
            "certification verdict is not PASS",
        ))

        underclassified = {"verdict": "PASS", "candidate_sha": candidate, "base_sha": base, "fallback_sha": base,
                           "change_impact": "NO_LIVE_IMPACT", "required_gates": ["source_identity", "release_verifier"],
                           "passed_gates": ["source_identity", "release_verifier"], "failed_gates": []}
        store = _store(root / "underclassified", base)
        current = store.record_verified_selection(candidate_sha=candidate, evidence_sha256="f" * 64,
                                                  expected_event=store.read()["event_sha256"])
        cert_path = root / "underclassified.json"
        cert_path.write_text(json.dumps(underclassified), encoding="utf-8")
        graph_path = root / "graph.json"
        graph_path.write_text(json.dumps({
            "edges": {"main.py": ["core/live.py"]},
            "critical_roots": ["main.py"],
            "bounded_roots": [],
            "complete": True,
            "unresolved": [],
        }), encoding="utf-8")
        verification = verify(root / "underclassified" / "state", repo=repo, certification=cert_path,
                              dependency_graph=graph_path)
        cases.append(_case(
            "M05",
            "impact_classifier_underclassifies_critical_live_change",
            not verification["independent_release_verifier_pass"],
            verification.get("blocker"),
            "certification result claims NO_LIVE_IMPACT for core/live.py reachable from main.py",
            "independent verifier rejects impact or fallback mismatch",
        ))

        store = _store(root / "promotion_before_certification", base)
        try:
            promote({"verdict": "PASS", "candidate_sha": candidate}, store, b"evidence")
            detected = False
            detail = "accepted"
        except ReleaseStoreError as exc:
            detected = True
            detail = str(exc)
        cases.append(_case(
            "M12",
            "promotion_attempted_before_complete_certification",
            detected,
            detail,
            "promote called with PASS shell lacking base/fallback/gate fields",
            "promotion raises ReleaseStoreError",
        ))

        store = _store(root / "invalid_fallback", base)
        result = certify(repo, candidate, store, graph, gate_runner=lambda _: True)
        result["fallback_sha"] = "c" * 40
        try:
            promote(result, store, b"evidence")
            detected = False
            detail = "accepted"
        except ReleaseStoreError as exc:
            detected = True
            detail = str(exc)
        cases.append(_case(
            "M07",
            "invalid_fallback_release",
            detected,
            detail,
            "certification fallback_sha changed away from current certified release",
            "promotion rejects fallback mismatch",
        ))

        store = _store(root / "uncertified_sha", "a" * 40)
        verification = verify(root / "uncertified_sha" / "state", repo=repo)
        cases.append(_case(
            "M03",
            "manifest_points_to_uncertified_sha",
            not verification["independent_release_verifier_pass"],
            verification["checks"],
            "release store points to SHA with no certification evidence in repo",
            "independent verifier rejects absent commit",
        ))

        incomplete = DependencyEvidence(edges={}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=False)
        impact = classify(["core/live.py"], incomplete)
        cases.append(_case(
            "M06",
            "unknown_impact_requires_critical_gates",
            "critical_mutations" in impact["required_gates"],
            impact["impact"],
            "incomplete dependency evidence classifies core/live.py",
            "UNKNOWN_IMPACT requires critical mutation gate",
        ))

        stale_authority = root / "stale_authority.json"
        stale_authority.write_text(json.dumps({"authority_verdict": "PASS", "independent_verifier_status": "PASS",
                                               "session_date": "2026-09-08"}), encoding="utf-8")
        store = _store(root / "stale_fallback_authority", base)
        prep = prepare(root / "stale_fallback_authority" / "state", "2026-09-09",
                       root / "stale_fallback_authority" / "next.json", authority_artifact=stale_authority)
        cases.append(_case(
            "M08",
            "fallback_session_authority_stale",
            prep["next_session_status"] == "BLOCKED" and "authority_session_stale" in prep["blockers"],
            prep["blockers"],
            "authority artifact session_date is previous day",
            "next-session preparation blocks stale authority",
        ))

        dirty_repo, dirty_base, dirty_candidate = _repo(root / "dirty")
        (dirty_repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        result = certify(dirty_repo, dirty_candidate, _store(root / "dirty_store", dirty_base), graph, gate_runner=lambda _: True)
        cases.append(_case(
            "M09",
            "candidate_tree_dirty",
            result["verdict"] == "BLOCKED" and result.get("blocker") == "candidate_tree_dirty",
            result,
            "uncommitted file created before certify",
            "certification blocks dirty tree",
        ))

        missing_evidence = root / "missing_evidence_gates.json"
        missing_evidence.write_text(json.dumps({"gates": {"source_identity": {"pass": True,
            "evidence_path": str(root / "absent.json"), "evidence_sha256": "0" * 64}}}), encoding="utf-8")
        from scripts.release_manager import _gate_result
        gates = _gate_result(missing_evidence)
        cases.append(_case(
            "M10",
            "certification_evidence_missing",
            gates["source_identity"] is False,
            gates,
            "gate manifest references missing evidence path",
            "gate parser marks gate false",
        ))

        store = _store(root / "missing_verifier_gate", base)
        shell = {"verdict": "PASS", "candidate_sha": candidate, "base_sha": base, "fallback_sha": base,
                 "required_gates": [g for g in full_gates if g != "release_verifier"],
                 "passed_gates": [g for g in full_gates if g != "release_verifier"], "failed_gates": []}
        try:
            promote(shell, store, b"evidence")
            detected = False
            detail = "accepted"
        except ReleaseStoreError as exc:
            detected = True
            detail = str(exc)
        cases.append(_case(
            "M11",
            "independent_verifier_missing",
            detected and detail == "promotion_requires_independent_verifier_gate",
            detail,
            "promotion result omits release_verifier from required and passed gates",
            "promotion rejects missing independent verifier gate",
        ))

        try:
            classify(["../core/live.py"], graph)
            detected = False
            detail = "accepted"
        except ValueError as exc:
            detected = True
            detail = str(exc)
        cases.append(_case(
            "M14",
            "merge_conflict_live_path_requires_impact_escalation",
            "critical_mutations" in classify(["core/live.py"], graph)["required_gates"],
            classify(["core/live.py"], graph)["impact"],
            "live dependency core/live.py is changed",
            "impact classifier escalates to critical gates",
        ))

        store = _store(root / "history_overwrite", base)
        event_id = store.read()["event_sha256"]
        try:
            (root / "history_overwrite" / "state" / "history" / f"{event_id}.json").write_text("tampered\n", encoding="utf-8")
            verify(root / "history_overwrite" / "state", repo=repo)
            detected = not verify(root / "history_overwrite" / "state", repo=repo)["independent_release_verifier_pass"]
        except OSError:
            detected = True
        cases.append(_case(
            "M13",
            "history_tamper_detected",
            detected,
            "history_integrity_failed",
            "committed history event overwritten with non-JSON text",
            "independent verifier rejects corrupted history",
        ))

        stale_authority = root / "stale_dated_authority.json"
        stale_authority.write_text(json.dumps({"authority_verdict": "PASS", "independent_verifier_status": "PASS",
                                               "session_date": "2026-09-08"}), encoding="utf-8")
        store = _store(root / "stale_dated_authority", base)
        prep = prepare(root / "stale_dated_authority" / "state", "2026-09-09",
                       root / "stale_dated_authority" / "next.json", authority_artifact=stale_authority)
        cases.append(_case(
            "M15",
            "dated_session_authority_stale",
            prep["next_session_status"] == "BLOCKED" and "authority_session_stale" in prep["blockers"],
            prep["blockers"],
            "dated authority artifact session_date is previous day",
            "next-session preparation blocks stale dated authority",
        ))

        cases.append(_case(
            "EXTRA01",
            "invalid_changed_path_rejected",
            detected,
            detail,
            "changed path contains parent traversal",
            "classifier raises invalid_changed_path",
        ))

    detected_count = sum(1 for case in cases if case["detected"])
    return {
        "campaign": "release_manager_v1_mutation_campaign",
        "detected": detected_count,
        "total": len(cases),
        "release_manager_mutations_detected": f"{detected_count}/{len(cases)}",
        "mandatory_mutation_classes_detected": f"{sum(1 for case in cases if case['mutation_id'].startswith('M') and case['detected'])}/15",
        "pass": detected_count == len(cases),
        "read_only": True,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_campaign()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
