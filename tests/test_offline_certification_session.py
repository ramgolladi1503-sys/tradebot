from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.offline_certification_session import (
    OfflineSessionEvidence,
    UNKNOWN,
    independently_verify_session_manifest,
    write_final_session_manifest,
)


def test_final_manifest_is_atomic_hash_bound_and_rediscoverable(tmp_path: Path):
    path = tmp_path / "SESSION_MANIFEST.json"
    sha = write_final_session_manifest(
        path,
        OfflineSessionEvidence(
            session_id="offline-20260903-001",
            session_date="2026-09-03",
            release_sha="a" * 40,
            worktree_root=str(tmp_path),
            runtime_root=str(tmp_path / "runtime"),
            metrics={"expected_token_count": UNKNOWN, "cas_evaluator_count": UNKNOWN},
        ),
    )
    result = independently_verify_session_manifest(path)
    assert result["ok"] is True
    assert result["sha256"] == sha
    assert result["payload"]["metrics"]["expected_token_count"] == UNKNOWN
    assert not list(tmp_path.glob(".*.tmp"))


def test_manifest_tamper_is_rejected(tmp_path: Path):
    path = tmp_path / "SESSION_MANIFEST.json"
    write_final_session_manifest(
        path,
        OfflineSessionEvidence("s", "2026-09-03", "b" * 40, str(tmp_path), str(tmp_path)),
    )
    payload = json.loads(path.read_text())
    payload["session_id"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="hash_mismatch"):
        independently_verify_session_manifest(path)


def test_authority_cannot_be_enabled(tmp_path: Path):
    path = tmp_path / "SESSION_MANIFEST.json"
    evidence = OfflineSessionEvidence("s", "2026-09-03", "c" * 40, str(tmp_path), str(tmp_path))
    write_final_session_manifest(path, evidence)
    payload = evidence.payload()
    payload["live_authorized"] = True
    with pytest.raises(ValueError):
        # Reconstructing through the verifier is the independent safety check.
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path.write_bytes(raw)
        path.with_name(path.name + ".sha256").write_text(__import__("hashlib").sha256(raw).hexdigest() + "  SESSION_MANIFEST.json\n")
        independently_verify_session_manifest(path)
