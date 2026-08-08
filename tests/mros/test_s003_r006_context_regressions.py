from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import population_git_trust
import program_context


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _queue_repo(tmp_path: Path, *, receipt_payload: object) -> tuple[Path, dict]:
    repo = tmp_path / "queue"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "mros-test@example.invalid")
    _git(repo, "config", "user.name", "MROS Test")

    candidate = "b" * 40
    manifest_rel = population_git_trust.canonical_manifest_path("S003", "R007", "reviewer")
    packet_rel = "research/evidence/sprints/S003/agent_queue/packets/S003_R007_R01.md"
    output_rel = "research/evidence/sprints/S003/agent_queue/results/S003_R007_R01.json"
    receipt_rel = "research/evidence/sprints/S003/agent_queue/receipts/S003_R007_R01.json"
    manifest = {
        "candidate_head": candidate,
        "sprint": "S003",
        "round": "R007",
        "job_type": "reviewer",
        "frozen_before_execution": True,
        "members": [{
            "execution_role_id": "R01",
            "packet_path": packet_rel,
            "output_path": output_rel,
            "receipt_path": receipt_rel,
        }],
    }
    manifest_path = repo / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git(repo, "add", manifest_rel)
    _git(repo, "commit", "-m", "freeze population")

    receipt_path = repo / receipt_rel
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")
    _git(repo, "add", receipt_rel)
    _git(repo, "commit", "-m", "record post-freeze receipt")
    return repo, manifest


def test_immutable_post_freeze_receipt_is_causally_valid(tmp_path: Path, monkeypatch) -> None:
    candidate = "b" * 40
    packet = "research/evidence/sprints/S003/agent_queue/packets/S003_R007_R01.md"
    output = "research/evidence/sprints/S003/agent_queue/results/S003_R007_R01.json"
    receipt = {
        "request": {"candidate_sha": candidate, "role_id": "R01", "packet_path": packet, "output_path": output},
        "job": {"job_id": "1" * 32},
    }
    repo, manifest = _queue_repo(tmp_path, receipt_payload=receipt)
    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    receipts, errors = population_git_trust.load_exact_receipts(queue_repo=repo, manifest=manifest)
    assert errors == []
    assert "1" * 32 in receipts


def test_malformed_receipt_root_returns_typed_error(tmp_path: Path, monkeypatch) -> None:
    repo, manifest = _queue_repo(tmp_path, receipt_payload=[])
    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    _, errors = population_git_trust.load_exact_receipts(queue_repo=repo, manifest=manifest)
    assert "RECEIPT_MEMBER_0_OBJECT_REQUIRED" in errors


def _contract() -> dict:
    return {
        "sprint": "S003",
        "status": "FROZEN",
        "criteria": [{"id": "S003-AC-001"}, {"id": "S003-AC-002"}],
    }


def _trace(ids: list[str]) -> dict:
    refs, errors = program_context._expected_s003_refs({"review_round": "R007", "audit_round": "A007"}, sprint="S003")
    assert errors == []
    return {
        "schema_version": "mros-sprint-acceptance-trace-v1",
        "sprint": "S003",
        "candidate_head": "c" * 40,
        "authority": "Research / R",
        "runtime_authority": "NONE",
        "m9_status": "NOT_STARTED",
        "review_round": "R007",
        "audit_round": "A007",
        "criteria": [{"id": cid, "status": "PASS", "evidence_refs": refs} for cid in ids],
    }


def test_acceptance_trace_rejects_substituted_contract_ids() -> None:
    trace = _trace(["S003-AC-001", "ATTACKER-ID"])
    errors = program_context.validate_acceptance_trace(
        trace,
        sprint="S003",
        candidate_head="c" * 40,
        contract=_contract(),
        strict_contract=True,
    )
    assert "ACCEPTANCE_TRACE_CONTRACT_IDS_MISMATCH" in errors


def test_acceptance_trace_requires_evidence_bindings() -> None:
    trace = _trace(["S003-AC-001", "S003-AC-002"])
    errors = program_context.validate_acceptance_trace(
        trace,
        sprint="S003",
        candidate_head="c" * 40,
        contract=_contract(),
        strict_contract=True,
        verify_evidence=True,
        authority_root=ROOT,
    )
    assert "ACCEPTANCE_TRACE_EVIDENCE_BINDINGS_REQUIRED" in errors


def test_acceptance_trace_rejects_nonexistent_or_tampered_evidence(tmp_path: Path) -> None:
    auth = tmp_path / "authority"
    queue = tmp_path / "queue"
    auth.mkdir(); queue.mkdir()
    trace = _trace(["S003-AC-001", "S003-AC-002"])
    refs = trace["criteria"][0]["evidence_refs"]
    bindings = []
    for ref in refs:
        source = "queue" if "/agent_queue/" in ref else "authority"
        root = queue if source == "queue" else auth
        p = root / ref
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("expected", encoding="utf-8")
        bindings.append({"path": ref, "source": source, "sha256": "0" * 64})
    trace["evidence_bindings"] = bindings
    errors = program_context.validate_acceptance_trace(
        trace,
        sprint="S003",
        candidate_head="c" * 40,
        contract=_contract(),
        authority_root=auth,
        queue_root=queue,
        strict_contract=True,
        verify_evidence=True,
    )
    assert any(x.startswith("ACCEPTANCE_EVIDENCE_SHA256_MISMATCH:") for x in errors)
