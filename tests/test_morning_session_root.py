import json

import pytest

from core.morning_session_root import SessionRootError, create_session_root


def test_creates_fresh_external_root(tmp_path):
    result = create_session_root(external_root=tmp_path, session_date="2026-09-09", release_sha="a" * 40)
    assert result["root_preexisted"] is False
    assert result["repository_local_live_writers"] == 0
    assert (tmp_path / "morning-sessions" / result["session_id"] / "preflight" / "session_root_manifest.json").exists()


def test_rejects_invalid_release_sha(tmp_path):
    with pytest.raises(SessionRootError, match="release_sha_invalid"):
        create_session_root(external_root=tmp_path, session_date="2026-09-09", release_sha="bad")


def test_rejects_evidence_outside_external_root(tmp_path):
    with pytest.raises(SessionRootError, match="evidence_root_not_external"):
        create_session_root(external_root=tmp_path, session_date="2026-09-09", release_sha="a" * 40, evidence_root=tmp_path.parent / "elsewhere")
