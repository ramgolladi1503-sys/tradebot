import json
import subprocess

from core.certified_release_store import ReleaseStore
from scripts.verify_release_manager import verify


def _commit(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", name],
        check=True,
    )
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def test_independent_verifier_rejects_nonexistent_certified_sha(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _commit(repo, "base.py", "x=1\n")
    store = ReleaseStore(tmp_path / "state")
    store.record_verified_selection(candidate_sha="a" * 40, evidence_sha256="e" * 64, expected_event=None)

    result = verify(tmp_path / "state", repo=repo)

    assert result["independent_release_verifier_pass"] is False
    assert result["checks"]["certified_sha_exists"] is False
    assert result["broker_api_called"] is False
    assert result["orders_placed"] == 0


def test_independent_verifier_requires_complete_certification_result(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base = _commit(repo, "base.py", "x=1\n")
    candidate = _commit(repo, "candidate.py", "x=2\n")
    store = ReleaseStore(tmp_path / "state")
    current = store.record_verified_selection(candidate_sha=base, evidence_sha256="e" * 64, expected_event=None)
    promoted = store.record_verified_selection(
        candidate_sha=candidate,
        evidence_sha256="f" * 64,
        expected_event=current["event_sha256"],
    )
    cert_path = tmp_path / "certification.json"
    cert_path.write_text(
        json.dumps(
            {
                "verdict": "PASS",
                "candidate_sha": candidate,
                "base_sha": base,
                "fallback_sha": base,
                "required_gates": ["source_identity"],
                "passed_gates": [],
                "failed_gates": [],
            }
        ),
        encoding="utf-8",
    )

    result = verify(tmp_path / "state", repo=repo, certification=cert_path)

    assert promoted["certified_live_sha"] == candidate
    assert result["independent_release_verifier_pass"] is False
    assert result["blocker"] == "promotion_base_mismatch"
