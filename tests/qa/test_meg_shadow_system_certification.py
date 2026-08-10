from __future__ import annotations

import hashlib
import json

from core.qa_certification.meg_shadow_system import (
    CERTIFIED_VERDICT,
    FAILED_VERDICT,
    OFFLINE_PASS_VERDICT,
    PENDING_VERDICT,
    REQUIRED_OFFLINE_GATES,
    assemble_system_certificate,
    build_offline_report,
    validate_offline_report,
)


def _gate(gate_id: str, *, passed: bool = True) -> dict:
    return {
        "gate_id": gate_id,
        "passed": passed,
        "return_code": 0 if passed else 1,
        "timed_out": False,
        "duration_seconds": 0.1,
        "command": ["python", "-m", "pytest", gate_id],
        "test_file_sha256": {f"tests/{gate_id}.py": "a" * 64},
        "stdout_tail": "passed" if passed else "failed",
        "stderr_tail": "",
    }


def _offline() -> dict:
    return build_offline_report(
        head_sha="1" * 40,
        gate_results=[_gate(gate_id) for gate_id in REQUIRED_OFFLINE_GATES],
        generated_at="2026-08-03T00:00:00+00:00",
    )


def _semantic_sha(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _post_market(verdict: str) -> dict:
    passed = verdict == "PASS_READ_ONLY_POST_MARKET_RELIABILITY"
    semantic = {
        "schema_version": 1,
        "verdict": verdict,
        "implementation_complete": True,
        "live_evidence_complete": passed,
        "read_only": True,
        "order_authority": False,
        "broker_write_authority": False,
        "gates": [],
        "limitations": [
            "No strategy profitability or structural edge is certified.",
            "No broker connectivity, real fill quality, or production deployment is certified.",
            "Observed market contributors are not asserted as unique causes.",
        ],
    }
    return {**semantic, "semantic_sha256": _semantic_sha(semantic)}


def test_all_eight_offline_gates_produce_pass_report():
    report = _offline()
    assert report["verdict"] == OFFLINE_PASS_VERDICT
    assert validate_offline_report(report)["passed"] is True
    assert [gate["gate_id"] for gate in report["gates"]] == list(
        REQUIRED_OFFLINE_GATES
    )


def test_missing_offline_gate_fails_closed():
    report = build_offline_report(
        head_sha="1" * 40,
        gate_results=[
            _gate(gate_id) for gate_id in REQUIRED_OFFLINE_GATES[:-1]
        ],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert report["verdict"] == FAILED_VERDICT
    assert REQUIRED_OFFLINE_GATES[-1] in report["missing_gate_ids"]


def test_modified_offline_semantics_are_detected():
    report = _offline()
    report["gates"][0]["passed"] = False
    check = validate_offline_report(report)
    assert check["passed"] is False
    assert "offline_semantic_sha_mismatch" in check["errors"]


def test_offline_pass_without_post_market_certificate_remains_pending():
    certificate = assemble_system_certificate(
        offline_report=_offline(),
        post_market_certificate=None,
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert certificate["verdict"] == PENDING_VERDICT
    assert certificate["remaining_gate"] == "FRESH_PR763_MARKET_SESSION"
    assert certificate["allowed_for_live_execution"] is False


def test_pending_post_market_certificate_cannot_become_green():
    certificate = assemble_system_certificate(
        offline_report=_offline(),
        post_market_certificate=_post_market(PENDING_VERDICT),
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert certificate["verdict"] == PENDING_VERDICT
    assert certificate["post_market_reliability_passed"] is False


def test_real_post_market_pass_produces_read_only_system_certificate():
    certificate = assemble_system_certificate(
        offline_report=_offline(),
        post_market_certificate=_post_market(
            "PASS_READ_ONLY_POST_MARKET_RELIABILITY"
        ),
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert certificate["verdict"] == CERTIFIED_VERDICT
    assert certificate["read_only"] is True
    assert certificate["order_authority"] is False
    assert certificate["broker_write_authority"] is False
    assert certificate["allowed_for_live_execution"] is False
    assert certificate["allowed_for_paper_execution"] is False


def test_order_authority_in_post_market_certificate_fails_closed():
    post = _post_market("PASS_READ_ONLY_POST_MARKET_RELIABILITY")
    post["order_authority"] = True
    certificate = assemble_system_certificate(
        offline_report=_offline(),
        post_market_certificate=post,
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert certificate["verdict"] == FAILED_VERDICT
    assert any(
        "post_market_order_authority_not_false" in error
        for error in certificate["errors"]
    )


def test_stale_post_market_semantic_hash_fails_closed():
    post = _post_market("PASS_READ_ONLY_POST_MARKET_RELIABILITY")
    post["live_evidence_complete"] = False
    certificate = assemble_system_certificate(
        offline_report=_offline(),
        post_market_certificate=post,
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert certificate["verdict"] == FAILED_VERDICT
    assert any(
        "post_market_semantic_sha_mismatch" in error
        for error in certificate["errors"]
    )


def test_failed_offline_gate_overrides_real_live_pass():
    failed = build_offline_report(
        head_sha="1" * 40,
        gate_results=[
            _gate(gate_id, passed=gate_id != "AUTHORITY_RANKING_AND_UI")
            for gate_id in REQUIRED_OFFLINE_GATES
        ],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    certificate = assemble_system_certificate(
        offline_report=failed,
        post_market_certificate=_post_market(
            "PASS_READ_ONLY_POST_MARKET_RELIABILITY"
        ),
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert certificate["verdict"] == FAILED_VERDICT
