from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import mros_agent_git_worker as worker  # noqa: E402


def test_failed_frozen_role_gets_unique_retry_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "queue"
    root = repo / worker.QUEUE_ROOT
    for name in ("requests", "receipts", "packets", "results", "manifests"):
        (root / name).mkdir(parents=True, exist_ok=True)

    candidate = "e" * 40
    manifest = {
        "job_type": "reviewer",
        "candidate_head": candidate,
        "round": "R002",
        "members": [{"execution_role_id": "R03"}],
    }
    (root / "manifests" / "S003_R002_REVIEW_POPULATION.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    packet_rel = (worker.QUEUE_ROOT / "packets" / "S003_R002_R03.md").as_posix()
    output_rel = (worker.QUEUE_ROOT / "results" / "S003_R002_R03.json").as_posix()
    request = {
        "schema_version": 1,
        "request_id": "S003-R002-R03-eeeeeeee",
        "created_by": "mros-autonomous-supervisor",
        "created_at": "2026-08-08",
        "job_type": "reviewer",
        "role_id": "R03",
        "candidate_sha": candidate,
        "packet_path": packet_rel,
        "output_path": output_rel,
        "backend": "codex",
    }
    request_path = root / "requests" / "S003_R002_R03.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    (repo / packet_rel).write_text("# R03\n", encoding="utf-8")
    failed_receipt = root / "receipts" / "S003_R002_R03.json"
    failed_receipt.write_text(
        json.dumps({"job": {"state": "FAILED", "exit_code": None, "error_code": "WORKTREE_CREATE_FAILED"}}),
        encoding="utf-8",
    )

    expected_packet = (worker.QUEUE_ROOT / "packets" / "S003_R002_R03_RETRY1.md").as_posix()
    expected_request = (worker.REQUEST_DIR / "S003_R002_R03_RETRY1.json").as_posix()

    def fake_run_git(_repo: Path, *args: str, **_kwargs):
        if args[:3] == ("diff", "--cached", "--name-only"):
            return SimpleNamespace(stdout=f"{expected_packet}\n{expected_request}\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(worker, "run_git", fake_run_git)

    created = worker._enqueue_retry_for_role(repo, "automation/mros-agent-queue-v1", "reviewer", "R03", candidate)
    assert created is True
    assert failed_receipt.is_file(), "failed attempt evidence must remain intact"

    retry_request_path = repo / expected_request
    retry_packet_path = repo / expected_packet
    assert retry_request_path.is_file()
    assert retry_packet_path.is_file()
    retry = json.loads(retry_request_path.read_text(encoding="utf-8"))
    assert retry["role_id"] == "R03"
    assert retry["candidate_sha"] == candidate
    assert retry["request_id"].endswith("-retry1")
    assert retry["output_path"].endswith("S003_R002_R03_RETRY1.json")
    assert "Infrastructure retry 1" in retry_packet_path.read_text(encoding="utf-8")
