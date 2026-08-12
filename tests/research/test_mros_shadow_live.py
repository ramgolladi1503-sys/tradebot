import pytest

from research.mros_certification.shadow_live import validate_shadow_session

SHA = "a" * 40


def test_replay_is_not_live_proof():
    result = validate_shadow_session({"candidate_sha": SHA, "source_kind": "replay", "replay": True}, candidate_sha=SHA)
    assert result["status"] == "BLOCKED_LIVE_WINDOW"


def test_genuine_session_is_read_only():
    result = validate_shadow_session({"candidate_sha": SHA, "source_kind": "genuine_live", "observed_at": "2026-08-12T09:15:00Z"}, candidate_sha=SHA)
    assert result["status"] == "SHADOW_LIVE_VALID"
    assert result["is_order_action"] is False


def test_authority_cannot_be_enabled():
    with pytest.raises(ValueError, match="SHADOW_AUTHORITY_FORBIDDEN"):
        validate_shadow_session({"candidate_sha": SHA, "source_kind": "genuine_live", "observed_at": "2026-08-12T09:15:00Z", "live_authorized": True}, candidate_sha=SHA)
