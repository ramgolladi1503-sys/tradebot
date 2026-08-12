import pytest

from research.mros_certification.offline import manifest_sha256, validate_offline_manifest


SHA = "a" * 40


def manifest():
    return {
        "candidate_sha": SHA,
        "task_ids": ["T21"],
        "status": "OFFLINE_EVIDENCE_VALID",
        "live_or_prospective_claimed": False,
        "safety": {
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        },
        "focused": {"status": "PASS", "candidate_sha": SHA},
        "adversarial": {"status": "PASS", "candidate_sha": SHA},
        "integration": {"status": "PASS", "candidate_sha": SHA},
    }


def test_offline_manifest_is_exact_sha_bound_and_pending_certification():
    result = validate_offline_manifest(manifest(), candidate_sha=SHA, required_tasks=["T21"])
    assert result.status == "OFFLINE_EVIDENCE_VALID_PENDING_INDEPENDENT_REVIEW"
    assert result.independent_verification == "PENDING"
    assert result.ci == "PENDING"
    assert len(manifest_sha256(manifest())) == 64


@pytest.mark.parametrize("field,value,error", [
    ("candidate_sha", "b" * 40, "EVIDENCE_CANDIDATE_SHA_MISMATCH"),
    ("live_or_prospective_claimed", True, "OFFLINE_MANIFEST_CANNOT_CLAIM_LIVE"),
    ("safety", {"broker_write_authority": True}, "SAFETY_BOUNDARY_INVALID"),
    ("focused", {"status": "PASS", "candidate_sha": "b" * 40}, "FOCUSED_EVIDENCE_INVALID"),
])
def test_offline_manifest_rejects_tamper_and_authority(field, value, error):
    candidate = manifest()
    candidate[field] = value
    with pytest.raises(ValueError, match=error):
        validate_offline_manifest(candidate, candidate_sha=SHA, required_tasks=["T21"])
