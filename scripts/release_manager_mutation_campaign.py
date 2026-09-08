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
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base = _commit(repo, "core/live.py", "SAFE=True\n")
    candidate = _commit(repo, "core/live.py", "SAFE=False\n")
    return repo, base, candidate


def _store(root: Path, sha: str) -> ReleaseStore:
    store = ReleaseStore(root / "state")
    store.record_verified_selection(candidate_sha=sha, evidence_sha256="e" * 64, expected_event=None)
    return store


def _case(name: str, detected: bool, detail: str) -> dict:
    return {"name": name, "detected": bool(detected), "detail": detail}


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

        store = _store(root / "missing_gate", base)
        result = certify(repo, candidate, store, graph, gate_runner=lambda gate: gate != "whole_tree_compile")
        cases.append(_case("candidate_certification_missing_required_gate", result["verdict"] != "PASS", result["verdict"]))

        store = _store(root / "promotion_before_certification", base)
        try:
            promote({"verdict": "PASS", "candidate_sha": candidate}, store, b"evidence")
            detected = False
            detail = "accepted"
        except ReleaseStoreError as exc:
            detected = True
            detail = str(exc)
        cases.append(_case("promotion_attempted_before_complete_certification", detected, detail))

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
        cases.append(_case("invalid_fallback_release", detected, detail))

        store = _store(root / "uncertified_sha", "a" * 40)
        verification = verify(root / "uncertified_sha" / "state", repo=repo)
        cases.append(_case("manifest_points_to_uncertified_sha", not verification["independent_release_verifier_pass"], verification["checks"]))

        incomplete = DependencyEvidence(edges={}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=False)
        impact = classify(["core/live.py"], incomplete)
        cases.append(_case("unknown_impact_requires_critical_gates", "critical_mutations" in impact["required_gates"], impact["impact"]))

        try:
            classify(["../core/live.py"], graph)
            detected = False
            detail = "accepted"
        except ValueError as exc:
            detected = True
            detail = str(exc)
        cases.append(_case("invalid_changed_path_rejected", detected, detail))

        store = _store(root / "history_overwrite", base)
        event_id = store.read()["event_sha256"]
        try:
            (root / "history_overwrite" / "state" / "history" / f"{event_id}.json").write_text("tampered\n", encoding="utf-8")
            verify(root / "history_overwrite" / "state", repo=repo)
            detected = not verify(root / "history_overwrite" / "state", repo=repo)["independent_release_verifier_pass"]
        except OSError:
            detected = True
        cases.append(_case("history_tamper_detected", detected, "history_integrity_failed"))

    detected_count = sum(1 for case in cases if case["detected"])
    return {
        "campaign": "release_manager_v1_mutation_campaign",
        "detected": detected_count,
        "total": len(cases),
        "release_manager_mutations_detected": f"{detected_count}/{len(cases)}",
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
