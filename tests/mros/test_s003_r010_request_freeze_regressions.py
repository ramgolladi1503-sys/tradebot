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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "queue"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "mros-test@example.invalid")
    _git(repo, "config", "user.name", "MROS Test")
    return repo


def _population(round_id: str = "R010") -> tuple[dict, dict, str, str]:
    candidate = "e" * 40
    output_rel = f"research/evidence/sprints/S003/agent_queue/results/S003_{round_id}_R01.json"
    packet_rel = f"research/evidence/sprints/S003/agent_queue/packets/S003_{round_id}_R01.md"
    receipt_rel = f"research/evidence/sprints/S003/agent_queue/receipts/S003_{round_id}_R01.json"
    member = {
        "execution_role_id": "R01",
        "packet_path": packet_rel,
        "output_path": output_rel,
        "receipt_path": receipt_rel,
    }
    manifest = {
        "candidate_head": candidate,
        "sprint": "S003",
        "round": round_id,
        "job_type": "reviewer",
        "frozen_before_execution": True,
        "members": [member],
    }
    request = {
        "candidate_sha": candidate,
        "role_id": "R01",
        "packet_path": packet_rel,
        "output_path": output_rel,
    }
    manifest_rel = population_git_trust.canonical_manifest_path("S003", round_id, "reviewer")
    request_rel = population_git_trust.canonical_request_path(member)
    return manifest, request, manifest_rel, request_rel


def _write(repo: Path, rel: str, payload: dict) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _validate(repo: Path, manifest: dict, manifest_rel: str) -> list[str]:
    return population_git_trust.validate_trusted_population(
        queue_repo=repo,
        manifest_path=manifest_rel,
        manifest=manifest,
        candidate_head=manifest["candidate_head"],
        sprint="S003",
        round_id=manifest["round"],
        job_type="reviewer",
    )


def test_request_origin_before_population_freeze_is_accepted(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    manifest, request, manifest_rel, request_rel = _population()
    _write(repo, request_rel, request)
    _git(repo, "add", request_rel)
    _git(repo, "commit", "-m", "create request before freeze")
    _write(repo, manifest_rel, manifest)
    _git(repo, "add", manifest_rel)
    _git(repo, "commit", "-m", "freeze population")

    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    assert _validate(repo, manifest, manifest_rel) == []


def test_request_origin_after_population_freeze_is_rejected(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    manifest, request, manifest_rel, request_rel = _population()
    _write(repo, manifest_rel, manifest)
    _git(repo, "add", manifest_rel)
    _git(repo, "commit", "-m", "freeze population")
    _write(repo, request_rel, request)
    _git(repo, "add", request_rel)
    _git(repo, "commit", "-m", "invalid post-freeze request")

    monkeypatch.setattr(population_git_trust, "QUEUE_REF", "HEAD")
    errors = _validate(repo, manifest, manifest_rel)
    assert "POPULATION_REQUEST_0_POSTDATES_FREEZE" in errors
