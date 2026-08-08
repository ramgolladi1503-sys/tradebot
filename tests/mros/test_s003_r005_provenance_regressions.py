from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import advance_program
import population_git_trust


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_review_aggregate_rejects_stale_population_manifest_reference() -> None:
    aggregate = {
        "candidate_head": "a" * 40,
        "decision": "PASS",
        "runtime_authority": "NONE",
        "authority": "Research / R",
        "transport": "mac_git_mailbox",
        "population_manifest": "research/evidence/sprints/S003/agent_queue/manifests/S003_R999_REVIEW_POPULATION.json",
        "reviews": [],
        "valid_reviews": 0,
        "invalid_reviews": 0,
        "expected_reviews": 0,
        "submitted_reviews": 0,
        "minimum_valid_reviews": 0,
        "omitted_reviews": [],
        "extra_reviews": [],
        "manifest_errors": [],
        "critical": 0,
        "major": 0,
        "minor": 0,
        "unknown": 0,
    }
    errors = advance_program._validate_aggregate(
        aggregate,
        candidate_head="a" * 40,
        kind="review",
        manifest={},
        receipts={},
        expected_sprint="S003",
        expected_round="R005",
        minimum_required=3,
    )
    assert "REVIEW_POPULATION_MANIFEST_REF_MISMATCH" in errors


def _init_receipt_repo(tmp_path: Path, *, round_id: str = "R005") -> tuple[Path, dict, str]:
    repo = tmp_path / "queue"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "mros-test@example.invalid")
    _git(repo, "config", "user.name", "MROS Test")

    candidate = "b" * 40
    manifest_rel = population_git_trust.canonical_manifest_path("S003", round_id, "reviewer")
    output_rel = f"research/evidence/sprints/S003/agent_queue/results/S003_{round_id}_R01.json"
    packet_rel = f"research/evidence/sprints/S003/agent_queue/packets/S003_{round_id}_R01.md"
    receipt_rel = f"research/evidence/sprints/S003/agent_queue/receipts/S003_{round_id}_R01.json"
    manifest = {
        "candidate_head": candidate,
        "sprint": "S003",
        "round": round_id,
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
    return repo, manifest, receipt_rel


def _valid_receipt(manifest: dict) -> dict:
    member = manifest["members"][0]
    return {
        "request": {
            "candidate_sha": manifest["candidate_head"],
            "role_id": "R01",
            "packet_path": member["packet_path"],
            "output_path": member["output_path"],
        },
        "job": {"job_id": "1" * 32},
    }


def test_post_freeze_receipt_creation_is_required(tmp_path: Path, monkeypatch) -> None:
    repo, manifest, receipt_rel = _init_receipt_repo(tmp_path, round_id="R006")
    receipt_path = repo / receipt_rel
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(_valid_receipt(manifest)), encoding="utf-8")
    _git(repo, "add", receipt_rel)
    _git(repo, "commit", "-m", "post-freeze receipt")

    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    receipts, errors = population_git_trust.load_exact_receipts(queue_repo=repo, manifest=manifest)
    assert errors == []
    assert len(receipts) == 1


def test_receipt_origin_at_population_freeze_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "queue"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "mros-test@example.invalid")
    _git(repo, "config", "user.name", "MROS Test")
    candidate = "b" * 40
    round_id = "R006"
    manifest_rel = population_git_trust.canonical_manifest_path("S003", round_id, "reviewer")
    output_rel = f"research/evidence/sprints/S003/agent_queue/results/S003_{round_id}_R01.json"
    packet_rel = f"research/evidence/sprints/S003/agent_queue/packets/S003_{round_id}_R01.md"
    receipt_rel = f"research/evidence/sprints/S003/agent_queue/receipts/S003_{round_id}_R01.json"
    manifest = {
        "candidate_head": candidate,
        "sprint": "S003",
        "round": round_id,
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
    receipt_path = repo / receipt_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt_path.write_text(json.dumps(_valid_receipt(manifest)), encoding="utf-8")
    _git(repo, "add", manifest_rel, receipt_rel)
    _git(repo, "commit", "-m", "invalid simultaneous freeze and receipt")

    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    _, errors = population_git_trust.load_exact_receipts(queue_repo=repo, manifest=manifest)
    assert "RECEIPT_MEMBER_0_ORIGIN_NOT_STRICTLY_AFTER_FREEZE" in errors


def test_modified_receipt_history_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo, manifest, receipt_rel = _init_receipt_repo(tmp_path)
    receipt = _valid_receipt(manifest)
    receipt_path = repo / receipt_rel
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _git(repo, "add", receipt_rel)
    _git(repo, "commit", "-m", "record receipt")

    receipt["tampered"] = True
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _git(repo, "add", receipt_rel)
    _git(repo, "commit", "-m", "modify receipt")

    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    _, errors = population_git_trust.load_exact_receipts(queue_repo=repo, manifest=manifest)
    assert "RECEIPT_MEMBER_0_HISTORY_NOT_IMMUTABLE" in errors


def test_malformed_receipt_root_returns_controlled_error(tmp_path: Path, monkeypatch) -> None:
    repo, manifest, receipt_rel = _init_receipt_repo(tmp_path, round_id="R006")
    receipt_path = repo / receipt_rel
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text("[]", encoding="utf-8")
    _git(repo, "add", receipt_rel)
    _git(repo, "commit", "-m", "malformed receipt root")

    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    receipts, errors = population_git_trust.load_exact_receipts(queue_repo=repo, manifest=manifest)
    assert receipts == {}
    assert "RECEIPT_MEMBER_0_OBJECT_REQUIRED" in errors
