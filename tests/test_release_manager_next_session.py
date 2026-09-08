import json

from core.certified_release_store import ReleaseStore
from scripts.release_manager_prepare_next_session import prepare


def test_next_session_preparation_blocks_without_authority(tmp_path):
    ReleaseStore(tmp_path / "state").record_verified_selection(
        candidate_sha="a" * 40,
        evidence_sha256="e" * 64,
        expected_event=None,
    )

    result = prepare(tmp_path / "state", "2026-09-09", tmp_path / "next.json")

    assert result["next_session_status"] == "BLOCKED"
    assert result["blockers"] == ["authority_artifact_missing"]
    assert result["broker_api_called"] is False
    assert result["orders_placed"] == 0


def test_next_session_preparation_accepts_passing_authority(tmp_path):
    ReleaseStore(tmp_path / "state").record_verified_selection(
        candidate_sha="a" * 40,
        evidence_sha256="e" * 64,
        expected_event=None,
    )
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps({"authority_verdict": "PASS", "independent_verifier_status": "PASS"}),
        encoding="utf-8",
    )

    result = prepare(tmp_path / "state", "2026-09-09", tmp_path / "next.json", authority_artifact=authority)

    assert result["next_session_status"] == "READY"
    assert result["certified_live_sha"] == "a" * 40
    assert result["authority_status"] == "PASS"


def test_next_session_preparation_is_append_only(tmp_path):
    ReleaseStore(tmp_path / "state").record_verified_selection(
        candidate_sha="a" * 40,
        evidence_sha256="e" * 64,
        expected_event=None,
    )
    output = tmp_path / "next.json"
    output.write_text("{}\n", encoding="utf-8")

    try:
        prepare(tmp_path / "state", "2026-09-09", output)
    except FileExistsError as exc:
        assert str(exc) == "next_session_artifact_exists"
    else:
        raise AssertionError("next-session artifact was overwritten")
