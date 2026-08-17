import pytest

from research.mros_certification.evaluation import (
    evaluate_prospective,
    structural_edge_decision,
    trading_integration_decision,
)

SHA = "a" * 40
OTHER_SHA = "c" * 40
MODEL = "b" * 64
ARTIFACT = "d" * 64


def _evidence(candidate_sha=SHA):
    return {
        "prospective": {
            "status": "PASS",
            "candidate_sha": candidate_sha,
            "artifact_sha256": ARTIFACT,
            "evaluation_status": "PROSPECTIVE_EVALUATED",
        },
        "historical_oos": {
            "status": "PASS",
            "candidate_sha": candidate_sha,
            "artifact_sha256": ARTIFACT,
            "qualified": True,
        },
        "cost_evidence": {
            "status": "PASS",
            "candidate_sha": candidate_sha,
            "artifact_sha256": ARTIFACT,
            "qualified": True,
        },
        "robustness": {
            "status": "PASS",
            "candidate_sha": candidate_sha,
            "artifact_sha256": ARTIFACT,
            "qualified": True,
        },
        "independent_verification": {
            "status": "PASS",
            "candidate_sha": candidate_sha,
            "artifact_sha256": ARTIFACT,
            "verdict": "PASS",
        },
    }


def _invalidated_evidence(candidate_sha=SHA):
    return {
        "prospective": {
            "status": "PASS",
            "candidate_sha": candidate_sha,
            "artifact_sha256": ARTIFACT,
            "evaluation_status": "INVALIDATED",
        }
    }


def test_missing_prospective_data_is_honest():
    assert (
        evaluate_prospective(
            candidate_sha=SHA,
            index="NIFTY",
            predictions=(),
            outcomes={},
            model_sha=MODEL,
            baseline="buy_hold",
        ).status
        == "INSUFFICIENT_PROSPECTIVE_DATA"
    )


def test_provenance_and_future_leakage_rejected():
    row = {"prediction_sha": "p", "session": "s"}
    with pytest.raises(ValueError, match="PROSPECTIVE_PROVENANCE_MISMATCH"):
        evaluate_prospective(
            candidate_sha=SHA,
            index="NIFTY",
            predictions=(row,),
            outcomes={},
            model_sha=MODEL,
            baseline="x",
            minimum_samples=1,
        )


def test_candidate_sha_must_be_exact_hex():
    with pytest.raises(ValueError, match="EXACT_CANDIDATE_SHA_REQUIRED"):
        structural_edge_decision(
            candidate_sha="not-a-real-sha".ljust(40, "x"),
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=_evidence(),
        )


def test_edge_and_integration_fail_closed_without_evidence():
    decision = structural_edge_decision(
        candidate_sha=SHA,
        prospective_status="PROSPECTIVE_EVALUATED",
        historical_oos=True,
        cost_evidence=True,
        robustness=True,
        independent_verification="PASS",
    )
    assert decision["status"] == "NOT_CERTIFIED"
    assert decision["execution_authority"] is False
    integration = trading_integration_decision(candidate_sha=SHA)
    assert integration["live_authorized"] is False
    assert integration["order_authority"] is False


def test_edge_certification_requires_complete_sha_bound_evidence():
    decision = structural_edge_decision(
        candidate_sha=SHA,
        prospective_status="PROSPECTIVE_EVALUATED",
        historical_oos=True,
        cost_evidence=True,
        robustness=True,
        independent_verification="PASS",
        evidence=_evidence(),
    )
    assert decision["status"] == "CERTIFIED"
    assert decision["prediction_quality_is_not_edge"] is True
    assert decision["execution_authority"] is False


def test_mismatched_evidence_candidate_sha_is_rejected():
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_SHA_MISMATCH:prospective"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=_evidence(OTHER_SHA),
        )


def test_missing_or_invalid_artifact_hash_is_rejected():
    evidence = _evidence()
    evidence["cost_evidence"].pop("artifact_sha256")
    with pytest.raises(ValueError, match="EVIDENCE_ARTIFACT_SHA256_REQUIRED"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=evidence,
        )


def test_caller_flags_must_match_evidence_bundle():
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_ROBUSTNESS_STATUS_MISMATCH"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=False,
            independent_verification="PASS",
            evidence=_evidence(),
        )


def test_caller_cannot_forge_verifier_pass():
    evidence = _evidence()
    evidence["independent_verification"]["verdict"] = "FAIL"
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_VERIFIER_STATUS_MISMATCH"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=evidence,
        )


def test_invalidated_status_without_bound_evidence_is_not_authority():
    decision = structural_edge_decision(
        candidate_sha=SHA,
        prospective_status="INVALIDATED",
        historical_oos=False,
        cost_evidence=False,
        robustness=False,
        independent_verification="NOT_REQUIRED",
    )
    assert decision["status"] == "NOT_CERTIFIED"
    assert decision["execution_authority"] is False


def test_bound_invalidated_prospective_evidence_propagates_invalidated():
    decision = structural_edge_decision(
        candidate_sha=SHA,
        prospective_status="INVALIDATED",
        historical_oos=False,
        cost_evidence=False,
        robustness=False,
        independent_verification="NOT_REQUIRED",
        evidence=_invalidated_evidence(),
    )
    assert decision["status"] == "INVALIDATED"
    assert decision["execution_authority"] is False


def test_invalidated_evidence_must_match_claimed_status():
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_PROSPECTIVE_STATUS_MISMATCH"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="INVALIDATED",
            historical_oos=False,
            cost_evidence=False,
            robustness=False,
            independent_verification="NOT_REQUIRED",
            evidence={"prospective": _evidence()["prospective"]},
        )
