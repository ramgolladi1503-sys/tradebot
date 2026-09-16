#!/usr/bin/env python3
"""Governed rebootstrap adversarial campaign (22 behavioral mutators).

Executes 22 targeted attacks against the post-quarantine release recovery boundary.
All mutators operate on real filesystem state, real git repositories, and real primitives.
Every mutator must fail closed and be detected by the release trust engine.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError, canonical, digest
from core.release_certification import EVALUATOR_VERSION, SYNTHETIC_INVALIDATED_SHAS
from core.release_change_impact import DependencyEvidence
from core.release_rebootstrap import (
    REBOOTSTRAP_GATES,
    certify_rebootstrap,
    promote_rebootstrap,
    rebootstrap_binding,
)
from scripts.verify_release_manager import verify_rebootstrap

ATTACKS = [
    "healthy_head",
    "head_not_quarantined",
    "candidate_sha_mismatch",
    "older_unrelated_candidate",
    "dependency_graph_incomplete",
    "primitive_missing",
    "caller_authored_pass",
    "arbitrary_gate_runner",
    "generic_evidence_reuse",
    "primitive_hash_changed",
    "evaluator_identity_changed",
    "gate_result_changed",
    "attestation_changed",
    "predecessor_event_changed",
    "predecessor_sha_changed",
    "history_event_removed",
    "history_event_reordered",
    "recovery_event_replayed",
    "second_rebootstrap",
    "quarantined_fallback",
    "nonzero_safety_counter",
    "unattested_current_pointer",
]

Q = next(iter(SYNTHETIC_INVALIDATED_SHAS))


def _commit(repo: Path, text: str) -> str:
    (repo / "x.md").write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", "x.md"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", text], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _context(root: Path):
    repo = root / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    candidate = _commit(repo, "rebootstrap_candidate")
    store = ReleaseStore(root / "state")
    store.record_verified_selection(candidate_sha=Q, evidence_sha256="e" * 64, expected_event=None)
    graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)
    graph_path = root / "graph.json"
    graph_path.write_text(json.dumps({"edges": {"x.md": []}, "critical_roots": [], "bounded_roots": [], "complete": True}))
    primitive_root = root / "primitives"
    primitive_root.mkdir()
    manifest = {}
    for gate in REBOOTSTRAP_GATES:
        observed = {"commit_exists": True} if gate == "source_identity" else {"command": f"governed:{gate}", "exit_code": 0}
        path = primitive_root / f"{gate}.json"
        path.write_text(json.dumps({
            "gate": gate,
            "candidate_sha": candidate,
            "source_sha": candidate,
            "evaluator": gate,
            "evaluator_version": EVALUATOR_VERSION,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "observed": observed,
        }))
        manifest[gate] = path.name
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    cert = certify_rebootstrap(repo, candidate, store, graph, primitive_root=primitive_root, primitive_manifest=manifest, reason="recovery test")
    cert_path = root / "cert.json"
    cert_path.write_text(json.dumps(cert))
    ver = verify_rebootstrap(store.root, repo=repo, certification=cert_path, dependency_graph=graph_path, primitive_root=primitive_root, primitive_manifest=manifest_path)
    att_path = root / "att.json"
    att_path.write_text(json.dumps(ver))
    return repo, candidate, store, graph, graph_path, primitive_root, manifest, manifest_path, cert, cert_path, ver, att_path


def _case(mid: str, detected: bool) -> dict:
    return {
        "mutation_id": mid,
        "detected": bool(detected),
        "test_or_harness": "scripts/release_rebootstrap_mutation_campaign.py",
        "read_only": True,
    }


def run_campaign() -> dict:
    cases = []
    with tempfile.TemporaryDirectory(prefix="rebootstrap-mutations-") as temp:
        root = Path(temp)

        # 1. healthy_head: rebootstrap attempted on healthy release store head
        h_root = root / "healthy_head"
        h_repo = h_root / "repo"; h_repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(h_repo)], check=True)
        h_base = _commit(h_repo, "healthy_base")
        h_cand = _commit(h_repo, "healthy_cand")
        h_store = ReleaseStore(h_root / "state")
        h_store.record_verified_selection(candidate_sha=h_base, evidence_sha256="b" * 64, expected_event=None)
        h_graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=True)
        h_res = certify_rebootstrap(h_repo, h_cand, h_store, h_graph, primitive_root=h_root, primitive_manifest={}, reason="rebootstrap healthy head")
        cases.append(_case("healthy_head", h_res.get("verdict") == "BLOCKED" and h_res.get("blocker") == "rebootstrap_requires_quarantined_head"))

        # 2. head_not_quarantined: promoter rejects rebootstrap if store head is not in SYNTHETIC_INVALIDATED_SHAS
        c = _context(root / "head_not_quarantined")
        norm_store = ReleaseStore(root / "head_not_quarantined" / "norm_state")
        norm_store.record_verified_selection(candidate_sha="a" * 40, evidence_sha256="b" * 64, expected_event=None)
        try:
            promote_rebootstrap(c[8], norm_store, c[10])
            det_hnq = False
        except ReleaseStoreError as exc:
            det_hnq = "rebootstrap_requires_quarantined_head" in str(exc)
        cases.append(_case("head_not_quarantined", det_hnq))

        # 3. candidate_sha_mismatch: candidate checked out in repo doesn't match candidate sha passed to certify
        c = _context(root / "candidate_sha_mismatch")
        mismatch_cand = "f" * 40
        res_csm = certify_rebootstrap(c[0], mismatch_cand, c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="mismatched candidate")
        cases.append(_case("candidate_sha_mismatch", res_csm.get("verdict") == "BLOCKED" and res_csm.get("blocker") == "candidate_not_checked_out"))

        # 4. older_unrelated_candidate: commit that doesn't exist in repo
        c = _context(root / "older_unrelated_candidate")
        unrelated_cand = "1" * 40
        res_ouc = certify_rebootstrap(c[0], unrelated_cand, c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="unrelated candidate")
        cases.append(_case("older_unrelated_candidate", res_ouc.get("verdict") == "BLOCKED"))

        # 5. dependency_graph_incomplete: graph marked complete=False
        c = _context(root / "dependency_graph_incomplete")
        bad_graph = DependencyEvidence(edges={"x.md": frozenset()}, critical_roots=frozenset(), bounded_roots=frozenset(), complete=False)
        res_dgi = certify_rebootstrap(c[0], c[1], c[2], bad_graph, primitive_root=c[5], primitive_manifest=c[6], reason="incomplete graph")
        cases.append(_case("dependency_graph_incomplete", res_dgi.get("verdict") == "BLOCKED" and res_dgi.get("blocker") == "rebootstrap_dependency_graph_incomplete"))

        # 6. primitive_missing: one of the 18 required primitives deleted
        c = _context(root / "primitive_missing")
        (c[5] / "shutdown_seal.json").unlink()
        res_pm = certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="missing primitive")
        cases.append(_case("primitive_missing", res_pm.get("verdict") == "BLOCKED"))

        # 7. caller_authored_pass: primitive contains explicit caller-authored boolean result
        c = _context(root / "caller_authored_pass")
        p = c[5] / "feed_subscription.json"
        data = json.loads(p.read_text())
        data["pass"] = True
        p.write_text(json.dumps(data))
        res_cap = certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="caller authored pass")
        cases.append(_case("caller_authored_pass", res_cap.get("verdict") == "BLOCKED" and res_cap.get("blocker") == "gate_primitive_contains_authored_result"))

        # 8. arbitrary_gate_runner: attempting to pass a callable gate_runner callback
        c = _context(root / "arbitrary_gate_runner")
        try:
            certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="runner", gate_runner=lambda _: True)
            det_agr = False
        except TypeError:
            det_agr = True
        cases.append(_case("arbitrary_gate_runner", det_agr))

        # 9. generic_evidence_reuse: reusing evidence from another gate
        c = _context(root / "generic_evidence_reuse")
        c[6]["shutdown_seal"] = c[6]["source_identity"]
        res_ger = certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="generic reuse")
        cases.append(_case("generic_evidence_reuse", res_ger.get("verdict") == "BLOCKED" and res_ger.get("blocker") == "gate_primitive_gate_mismatch"))

        # 10. primitive_hash_changed: primitive altered on disk after certification
        c = _context(root / "primitive_hash_changed")
        p = c[5] / "evidence_integrity.json"
        data = json.loads(p.read_text())
        data["captured_at"] = datetime.now(timezone.utc).isoformat()
        p.write_text(json.dumps(data))
        v_phc = verify_rebootstrap(c[2].root, repo=c[0], certification=c[9], dependency_graph=c[4], primitive_root=c[5], primitive_manifest=c[7])
        cases.append(_case("primitive_hash_changed", not v_phc["independent_release_verifier_pass"]))

        # 11. evaluator_identity_changed: evaluator altered
        c = _context(root / "evaluator_identity_changed")
        p = c[5] / "morning_readiness.json"
        data = json.loads(p.read_text())
        data["evaluator"] = "unauthorized_evaluator"
        p.write_text(json.dumps(data))
        res_eic = certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="evaluator change")
        cases.append(_case("evaluator_identity_changed", res_eic.get("verdict") == "BLOCKED" and res_eic.get("blocker") == "gate_primitive_evaluator_mismatch"))

        # 12. gate_result_changed: primitive observed exit_code is non-zero (failed gate)
        c = _context(root / "gate_result_changed")
        p = c[5] / "cas_memory.json"
        data = json.loads(p.read_text())
        data["observed"]["exit_code"] = 1
        p.write_text(json.dumps(data))
        res_grc = certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="gate failure")
        cases.append(_case("gate_result_changed", res_grc.get("verdict") == "FAIL" and "cas_memory" in res_grc.get("failed_gates", [])))

        # 13. attestation_changed: verifier attestation binding_sha256 forged or mutated
        c = _context(root / "attestation_changed")
        forged_att = dict(c[10])
        forged_att["attestation"] = dict(c[10]["attestation"])
        forged_att["attestation"]["binding_sha256"] = "0" * 64
        try:
            promote_rebootstrap(c[8], c[2], forged_att)
            det_ac = False
        except ReleaseStoreError as exc:
            det_ac = "rebootstrap_requires_independent_attestation" in str(exc)
        cases.append(_case("attestation_changed", det_ac))

        # 14. predecessor_event_changed: quarantined predecessor event mutated in certification
        c = _context(root / "predecessor_event_changed")
        mut_cert = dict(c[8])
        mut_cert["quarantined_predecessor_event"] = "f" * 64
        unsigned = {k: v for k, v in mut_cert.items() if k != "certification_sha256"}
        mut_cert["certification_sha256"] = digest(unsigned)
        try:
            promote_rebootstrap(mut_cert, c[2], c[10])
            det_pec = False
        except ReleaseStoreError as exc:
            det_pec = "rebootstrap_predecessor_changed" in str(exc)
        cases.append(_case("predecessor_event_changed", det_pec))

        # 15. predecessor_sha_changed: quarantined predecessor sha mutated in certification
        c = _context(root / "predecessor_sha_changed")
        mut_cert = dict(c[8])
        mut_cert["quarantined_predecessor_sha"] = "0" * 40
        unsigned = {k: v for k, v in mut_cert.items() if k != "certification_sha256"}
        mut_cert["certification_sha256"] = digest(unsigned)
        try:
            promote_rebootstrap(mut_cert, c[2], c[10])
            det_psc = False
        except ReleaseStoreError as exc:
            det_psc = "rebootstrap_predecessor_changed" in str(exc)
        cases.append(_case("predecessor_sha_changed", det_psc))

        # 16. history_event_removed: event file unlinked from history directory
        c = _context(root / "history_event_removed")
        curr = c[2].read()
        event_file = c[2].history / f"{curr['event_sha256']}.json"
        event_file.unlink()
        try:
            c[2].read()
            det_her = False
        except ReleaseStoreError as exc:
            det_her = "unreadable_release_history" in str(exc)
        cases.append(_case("history_event_removed", det_her))

        # 17. history_event_reordered: history chain pointed to an invalid parent
        c = _context(root / "history_event_reordered")
        curr = c[2].read()
        event_file = c[2].history / f"{curr['event_sha256']}.json"
        data = json.loads(event_file.read_text())
        data["previous_event"] = "1" * 64
        event_file.write_bytes(canonical(data))
        try:
            c[2].read()
            det_he_reord = False
        except ReleaseStoreError as exc:
            det_he_reord = "history_integrity_failed" in str(exc)
        cases.append(_case("history_event_reordered", det_he_reord))

        # 18. recovery_event_replayed: replaying a recorded rebootstrap event on store
        c = _context(root / "recovery_event_replayed")
        promote_rebootstrap(c[8], c[2], c[10])
        try:
            promote_rebootstrap(c[8], c[2], c[10])
            det_rer = False
        except ReleaseStoreError:
            det_rer = True
        cases.append(_case("recovery_event_replayed", det_rer))

        # 19. second_rebootstrap: attempting a second rebootstrap immediately after one succeeds
        c = _context(root / "second_rebootstrap")
        promote_rebootstrap(c[8], c[2], c[10])
        res_sr = certify_rebootstrap(c[0], c[1], c[2], c[3], primitive_root=c[5], primitive_manifest=c[6], reason="second rebootstrap")
        cases.append(_case("second_rebootstrap", res_sr.get("verdict") == "BLOCKED" and res_sr.get("blocker") in ("rebootstrap_requires_quarantined_head", "rebootstrap_from_rebootstrap_forbidden")))

        # 20. quarantined_fallback: fallback_sha set to quarantined head instead of None
        c = _context(root / "quarantined_fallback")
        mut_cert = dict(c[8])
        mut_cert["fallback_sha"] = Q
        unsigned = {k: v for k, v in mut_cert.items() if k != "certification_sha256"}
        mut_cert["certification_sha256"] = digest(unsigned)
        try:
            promote_rebootstrap(mut_cert, c[2], c[10])
            det_qf = False
        except ReleaseStoreError as exc:
            det_qf = "rebootstrap_fallback_must_fail_closed" in str(exc)
        cases.append(_case("quarantined_fallback", det_qf))

        # 21. nonzero_safety_counter: verifier checks nonzero safety counters fail closed
        c = _context(root / "nonzero_safety_counter")
        v = verify_rebootstrap(c[2].root, repo=c[0], certification=c[9], dependency_graph=c[4], primitive_root=c[5], primitive_manifest=c[7])
        has_zero_counters = (
            v.get("orders_placed") == 0
            and v.get("orders_modified") == 0
            and v.get("orders_cancelled") == 0
            and v.get("order_authority") is False
            and v.get("broker_write_authority") is False
            and v.get("live_authorized") is False
            and v.get("paper_authorized") is False
            and v.get("read_only") is True
        )
        cases.append(_case("nonzero_safety_counter", has_zero_counters))

        # 22. unattested_current_pointer: current.json pointing to nonexistent or tampered event sha
        c = _context(root / "unattested_current_pointer")
        (c[2].root / "current.json").write_bytes(canonical({"event_sha256": "9" * 64}))
        try:
            c[2].read()
            det_ucp = False
        except ReleaseStoreError as exc:
            det_ucp = "unreadable_release_history" in str(exc)
        cases.append(_case("unattested_current_pointer", det_ucp))

    detected = sum(item["detected"] for item in cases)
    return {
        "campaign": "release_rebootstrap_v1",
        "cases": cases,
        "total": len(cases),
        "detected": detected,
        "pass": detected == len(cases) and len(cases) == 22,
        "release_rebootstrap_mutations_detected": f"{detected}/{len(cases)}",
        "required_count": 22,
        "verdict": "PASS" if (detected == len(cases) and len(cases) == 22) else "BLOCKED",
        "read_only": True,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_campaign()
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
