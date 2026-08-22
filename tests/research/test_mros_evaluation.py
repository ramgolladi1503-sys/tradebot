import hashlib
import json

import pytest

from research.mros_certification.evaluation import (
    evaluate_prospective,
    structural_edge_decision,
    trading_integration_decision,
)

SHA = "a" * 40
OTHER_SHA = "c" * 40
MODEL = "b" * 64


def _write_artifact(tmp_path, name, payload):
    path = tmp_path / f"{name}.json"
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return {
        "artifact_path": str(path),
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _payload(name, candidate_sha=SHA, **extra):
    return {
        "evidence_kind": name,
        "status": "PASS",
        "candidate_sha": candidate_sha,
        **extra,
    }


def _evidence(tmp_path, candidate_sha=SHA):
    payloads = {
        "prospective": _payload(
            "prospective",
            candidate_sha,
            evaluation_status="PROSPECTIVE_EVALUATED",
        ),
        "historical_oos": _payload(
            "historical_oos", candidate_sha, qualified=True
        ),
        "cost_evidence": _payload("cost_evidence", candidate_sha, qualified=True),
        "robustness": _payload("robustness", candidate_sha, qualified=True),
        "independent_verification": _payload(
            "independent_verification", candidate_sha, verdict="PASS"
        ),
    }
    return {
        name: _write_artifact(tmp_path, name, payload)
        for name, payload in payloads.items()
    }


def _invalidated_evidence(tmp_path, candidate_sha=SHA):
    payload = _payload(
        "prospective", candidate_sha, evaluation_status="INVALIDATED"
    )
    return {"prospective": _write_artifact(tmp_path, "prospective", payload)}


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


def test_candidate_sha_must_be_exact_hex(tmp_path):
    with pytest.raises(ValueError, match="EXACT_CANDIDATE_SHA_REQUIRED"):
        structural_edge_decision(
            candidate_sha="not-a-real-sha".ljust(40, "x"),
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=_evidence(tmp_path),
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
    assert integration["paper_authorized"] is False
    assert integration["broker_write_authority"] is False


def test_edge_certification_requires_complete_sha_bound_artifacts(tmp_path):
    decision = structural_edge_decision(
        candidate_sha=SHA,
        prospective_status="PROSPECTIVE_EVALUATED",
        historical_oos=True,
        cost_evidence=True,
        robustness=True,
        independent_verification="PASS",
        evidence=_evidence(tmp_path),
    )
    assert decision["status"] == "CERTIFIED"
    assert decision["prediction_quality_is_not_edge"] is True
    assert decision["execution_authority"] is False


def test_pass_shaped_in_memory_mapping_is_not_evidence():
    forged = {
        name: {
            "status": "PASS",
            "candidate_sha": SHA,
            "artifact_sha256": "d" * 64,
        }
        for name in (
            "prospective",
            "historical_oos",
            "cost_evidence",
            "robustness",
            "independent_verification",
        )
    }
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_ARTIFACT_PATH_REQUIRED"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=forged,
        )


def test_mismatched_evidence_candidate_sha_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_SHA_MISMATCH:prospective"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=_evidence(tmp_path, OTHER_SHA),
        )


def test_missing_or_invalid_artifact_hash_is_rejected(tmp_path):
    evidence = _evidence(tmp_path)
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


def test_tampered_artifact_bytes_are_rejected(tmp_path):
    evidence = _evidence(tmp_path)
    path = tmp_path / "robustness.json"
    path.write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_ARTIFACT_HASH_MISMATCH:robustness"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=evidence,
        )


def test_wrong_artifact_kind_cannot_be_reused_for_another_gate(tmp_path):
    evidence = _evidence(tmp_path)
    historical = evidence["historical_oos"]
    evidence["cost_evidence"] = dict(historical)
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_KIND_MISMATCH:cost_evidence"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=True,
            independent_verification="PASS",
            evidence=evidence,
        )


def test_caller_flags_must_match_verified_artifact_bundle(tmp_path):
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_ROBUSTNESS_STATUS_MISMATCH"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="PROSPECTIVE_EVALUATED",
            historical_oos=True,
            cost_evidence=True,
            robustness=False,
            independent_verification="PASS",
            evidence=_evidence(tmp_path),
        )


def test_caller_cannot_forge_verifier_pass(tmp_path):
    evidence = _evidence(tmp_path)
    verifier_path = tmp_path / "independent_verification.json"
    forged_payload = _payload(
        "independent_verification", SHA, verdict="FAIL"
    )
    evidence["independent_verification"] = _write_artifact(
        tmp_path, "independent_verification", forged_payload
    )
    assert verifier_path.is_file()
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


def test_bound_invalidated_prospective_artifact_propagates_invalidated(tmp_path):
    decision = structural_edge_decision(
        candidate_sha=SHA,
        prospective_status="INVALIDATED",
        historical_oos=False,
        cost_evidence=False,
        robustness=False,
        independent_verification="NOT_REQUIRED",
        evidence=_invalidated_evidence(tmp_path),
    )
    assert decision["status"] == "INVALIDATED"
    assert decision["execution_authority"] is False


def test_invalidated_evidence_must_match_claimed_status(tmp_path):
    evidence = _evidence(tmp_path)
    with pytest.raises(ValueError, match="EDGE_EVIDENCE_PROSPECTIVE_STATUS_MISMATCH"):
        structural_edge_decision(
            candidate_sha=SHA,
            prospective_status="INVALIDATED",
            historical_oos=False,
            cost_evidence=False,
            robustness=False,
            independent_verification="NOT_REQUIRED",
            evidence={"prospective": evidence["prospective"]},
        )
