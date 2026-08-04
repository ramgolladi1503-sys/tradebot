from __future__ import annotations

import pytest

from aixion_trade_intelligence.certification import (
    REQUIRED_STRATEGY_GATES,
    CertificationGateResult,
    GateStatus,
    certify_strategy,
)


def gate(gate_id: str, status: GateStatus) -> CertificationGateResult:
    return CertificationGateResult(
        gate_id=gate_id,
        status=status,
        reason=f"{gate_id}_{status.value}",
        evidence_refs=(f"evidence/{gate_id}.json",) if status is not GateStatus.NOT_EVALUATED else (),
        calculation_version="1.0.0",
    )


def test_missing_gates_are_not_evaluated_and_block_promotion():
    decision = certify_strategy([gate("DATA_VALID", GateStatus.PASS)])
    assert decision.verdict == "INSUFFICIENT_EVIDENCE"
    assert decision.ready_for_human_review is False
    assert "POINT_IN_TIME_VALID" in decision.unevaluated_gates


def test_failed_gate_rejects_without_hidden_score():
    results = [gate(gate_id, GateStatus.PASS) for gate_id in REQUIRED_STRATEGY_GATES]
    failure_index = REQUIRED_STRATEGY_GATES.index("FILL_REALISM_VALID")
    results[failure_index] = gate("FILL_REALISM_VALID", GateStatus.FAIL)
    decision = certify_strategy(results)
    assert decision.verdict == "REJECTED_FILL_REALISM_VALID"
    assert decision.failed_gates == ("FILL_REALISM_VALID",)
    assert decision.ready_for_human_review is False


def test_all_explicit_gates_pass_only_to_human_review():
    decision = certify_strategy(
        [gate(gate_id, GateStatus.PASS) for gate_id in REQUIRED_STRATEGY_GATES]
    )
    assert decision.verdict == "READY_FOR_HUMAN_PROMOTION_REVIEW"
    assert decision.ready_for_human_review is True
    assert decision.failed_gates == ()
    assert decision.unevaluated_gates == ()


def test_evaluated_gate_requires_evidence():
    with pytest.raises(ValueError, match="requires_evidence"):
        CertificationGateResult(
            gate_id="DATA_VALID",
            status=GateStatus.PASS,
            reason="valid",
            evidence_refs=(),
            calculation_version="1.0.0",
        )


def test_duplicate_gate_is_rejected():
    item = gate("DATA_VALID", GateStatus.PASS)
    with pytest.raises(ValueError, match="duplicate_gate"):
        certify_strategy([item, item])
