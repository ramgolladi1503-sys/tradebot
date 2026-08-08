from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from mros_agent_bridge import (  # noqa: E402
    BackendSpec,
    BridgeConfig,
    BridgeError,
    MrosAgentBridge,
)
from mros_agent_git_worker import validate_request_payload  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> tuple[Path, str, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "mros-test@example.invalid")
    _git(repo, "config", "user.name", "MROS Test")
    packet = repo / "research" / "packets" / "R01.md"
    packet.parent.mkdir(parents=True)
    packet.write_text("# reviewer packet\nReturn a deterministic test artifact.\n", encoding="utf-8")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    sha = _git(repo, "rev-parse", "HEAD")
    fake = tmp_path / "fake_backend.py"
    fake.write_text(
        "from pathlib import Path\n"
        "import argparse\n"
        "p=argparse.ArgumentParser(); p.add_argument('--output'); a=p.parse_args()\n"
        "Path(a.output).write_text('# isolated result\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    return repo, sha, fake


def _bridge(tmp_path: Path) -> tuple[MrosAgentBridge, str, Path]:
    repo, sha, fake = _make_repo(tmp_path)
    config = BridgeConfig(
        repo_root=repo,
        worktree_root=tmp_path / "worktrees",
        state_root=tmp_path / "state",
        allowed_repo_realpath=repo,
        backends={
            "fake": BackendSpec(
                name="fake",
                argv_template=(sys.executable, str(fake), "--output", "{output}"),
                timeout_seconds=30,
            )
        },
        max_parallel_jobs=2,
    )
    return MrosAgentBridge(config), sha, repo


def _wait(bridge: MrosAgentBridge, job_id: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = bridge.get(job_id)
        if record.state in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return record
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_isolated_reviewer_job_creates_artifact_and_removes_worktree(tmp_path: Path) -> None:
    bridge, sha, repo = _bridge(tmp_path)
    record = bridge.submit(
        {
            "job_type": "reviewer",
            "role_id": "R01",
            "candidate_sha": sha,
            "packet_path": "research/packets/R01.md",
            "output_path": "research/results/R01.md",
            "backend": "fake",
        }
    )
    final = _wait(bridge, record.job_id)
    assert final.state == "SUCCEEDED"
    assert final.exit_code == 0
    assert final.command_hash
    assert (repo / "research/results/R01.md").read_text(encoding="utf-8") == "# isolated result\n"
    assert final.worktree_path
    assert not Path(final.worktree_path).exists()
    health = bridge.health()
    assert health["runtime_authority"] == "NONE"
    assert health["broker_actions_allowed"] is False


def test_rejects_reviewer_auditor_role_mismatch(tmp_path: Path) -> None:
    bridge, sha, _ = _bridge(tmp_path)
    with pytest.raises(BridgeError, match="ROLE_JOB_TYPE_MISMATCH"):
        bridge.submit(
            {
                "job_type": "reviewer",
                "role_id": "A01",
                "candidate_sha": sha,
                "packet_path": "research/packets/R01.md",
                "output_path": "research/results/A01.md",
                "backend": "fake",
            }
        )


def test_rejects_path_escape(tmp_path: Path) -> None:
    bridge, sha, _ = _bridge(tmp_path)
    with pytest.raises(BridgeError, match="REPOSITORY_PATH_ESCAPE"):
        bridge.submit(
            {
                "job_type": "reviewer",
                "role_id": "R02",
                "candidate_sha": sha,
                "packet_path": "../secret.md",
                "output_path": "research/results/R02.md",
                "backend": "fake",
            }
        )


def test_rejects_unknown_candidate(tmp_path: Path) -> None:
    bridge, _, _ = _bridge(tmp_path)
    with pytest.raises(BridgeError, match="CANDIDATE_SHA_NOT_PRESENT_LOCALLY"):
        bridge.submit(
            {
                "job_type": "reviewer",
                "role_id": "R03",
                "candidate_sha": "a" * 40,
                "packet_path": "research/packets/R01.md",
                "output_path": "research/results/R03.md",
                "backend": "fake",
            }
        )


def test_rejects_existing_output(tmp_path: Path) -> None:
    bridge, sha, repo = _bridge(tmp_path)
    output = repo / "research/results/R04.md"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n", encoding="utf-8")
    with pytest.raises(BridgeError, match="OUTPUT_PATH_ALREADY_EXISTS"):
        bridge.submit(
            {
                "job_type": "reviewer",
                "role_id": "R04",
                "candidate_sha": sha,
                "packet_path": "research/packets/R01.md",
                "output_path": "research/results/R04.md",
                "backend": "fake",
            }
        )


def test_git_worker_request_contract_requires_all_fields() -> None:
    with pytest.raises(Exception, match="REQUEST_FIELDS_MISSING"):
        validate_request_payload({"job_type": "reviewer"})
    payload = {
        "job_type": "auditor",
        "role_id": "A10",
        "candidate_sha": "b" * 40,
        "packet_path": "p.md",
        "output_path": "o.md",
        "backend": "fake",
    }
    assert validate_request_payload(payload) == payload
