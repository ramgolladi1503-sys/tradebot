import json
import subprocess
import sys

from core.certified_release_store import ReleaseStore


def test_status_command_fails_closed_when_status_missing(tmp_path):
    result = subprocess.run([sys.executable, "scripts/morning_readiness_cli.py", "status", "--status", str(tmp_path / "missing.json"), "--release", "a" * 40], capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert payload["state"] == "FAIL_CLOSED"
    assert payload["blockers"] == ["status_missing"]


def test_preflight_resolves_release_from_store(tmp_path):
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    ReleaseStore(tmp_path / "release-store").record_verified_selection(
        candidate_sha=actual,
        evidence_sha256="e" * 64,
        expected_event=None,
    )
    output = tmp_path / "preflight.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/morning_readiness_cli.py",
            "preflight",
            "--release-store-root",
            str(tmp_path / "release-store"),
            "--session-date",
            "2026-09-09",
            "--external-root",
            str(tmp_path / "external"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode in {0, 2}
    assert payload["release_sha_expected"] == actual
    assert payload["release_sha_match"] is True
    assert "release_authority_missing" not in payload.get("blocker", "")


def test_preflight_fails_closed_without_release_authority(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/morning_readiness_cli.py",
            "preflight",
            "--session-date",
            "2026-09-09",
            "--external-root",
            str(tmp_path / "external"),
            "--output",
            str(tmp_path / "preflight.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["blocker"] == "release_authority_missing"
