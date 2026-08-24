import json

import pytest

from core.live_artifact_contract import sha256_file, verify_artifact, write_immutable_json


def test_immutable_artifact_is_hashed_and_verified(tmp_path):
    path = tmp_path / "sealed" / "evidence.json"
    record = write_immutable_json(
        path, {"read_only": True, "orders": 0},
        artifact_type="session_evidence", session_id="s1", source_sha="a" * 40,
    )
    assert record.sha256 == sha256_file(path)
    verify_artifact(record)
    assert json.loads(path.read_text()) == {"orders": 0, "read_only": True}


def test_immutable_artifact_cannot_be_replaced_or_tampered(tmp_path):
    path = tmp_path / "evidence.json"
    record = write_immutable_json(
        path, {"value": 1}, artifact_type="evidence", session_id="s1", source_sha="b" * 40,
    )
    with pytest.raises(FileExistsError, match="immutable_artifact_exists"):
        write_immutable_json(
            path, {"value": 2}, artifact_type="evidence", session_id="s1", source_sha="b" * 40,
        )
    path.write_text('{"value": 2}\n')
    with pytest.raises(ValueError, match="hash_mismatch"):
        verify_artifact(record)
