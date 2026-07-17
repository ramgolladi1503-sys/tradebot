from __future__ import annotations

from core.ai_certification import (
    EvidenceCertification,
    GateStatus,
    StrategyVerdict,
    certify_bundle,
)


EXPECTED_GATE_ORDER = (
    "bundle_manifest",
    "artifact_hashes",
    "source_artifact_provenance",
    "source_authority",
    "data_provenance",
    "temporal_causality",
    "execution_realism",
    "financial_reconciliation",
    "walk_forward_integrity",
    "negative_controls",
    "test_evidence",
    "strategy_result_consistency",
)


def test_qa_func_001_happy_path_valid_negative_edge_is_certified(
    qa_bundle_factory,
):
    report = certify_bundle(qa_bundle_factory())

    assert report.evidence_certification is EvidenceCertification.CERTIFIED
    assert report.strategy_verdict is StrategyVerdict.NO_STRUCTURAL_EDGE
    assert report.blockers == ()
    assert report.warnings == ()


def test_qa_func_002_happy_path_positive_edge_is_supported(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "strategy_result.json": {
                "verdict": "STRUCTURAL_EDGE_SUPPORTED",
                "trades": 180,
                "after_cost_expectancy": 0.25,
                "profit_factor": 1.35,
            }
        }
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.CERTIFIED
    assert report.strategy_verdict is StrategyVerdict.STRUCTURAL_EDGE_SUPPORTED


def test_qa_func_003_insufficient_trades_is_business_outcome_not_invalid_evidence(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "strategy_result.json": {
                "verdict": "NO_STRUCTURAL_EDGE",
                "trades": 25,
            }
        }
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.CERTIFIED
    assert report.strategy_verdict is StrategyVerdict.INSUFFICIENT_TRADES


def test_qa_func_004_conditionally_supported_verdict_is_preserved(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "strategy_result.json": {
                "verdict": "CONDITIONALLY_SUPPORTED",
                "trades": 150,
                "after_cost_expectancy": 0.05,
                "profit_factor": 1.05,
            }
        }
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.CERTIFIED
    assert report.strategy_verdict is StrategyVerdict.CONDITIONALLY_SUPPORTED


def test_qa_behavior_001_optional_strategy_contradiction_withholds_only_strategy_claim(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "strategy_result.json": {
                "verdict": "STRUCTURAL_EDGE_SUPPORTED",
                "after_cost_expectancy": -0.2,
                "profit_factor": 0.7,
            }
        }
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.CERTIFIED
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert report.blockers == ()
    assert "strategy_result_consistency:NON_POSITIVE_EXPECTANCY" in report.warnings


def test_qa_behavior_002_all_gate_results_have_auditable_contract(
    qa_bundle_factory,
):
    report = certify_bundle(qa_bundle_factory())
    payload = report.to_dict()

    assert tuple(gate.gate for gate in report.gates) == EXPECTED_GATE_ORDER
    assert tuple(payload["gates"]) == EXPECTED_GATE_ORDER
    for gate in report.gates:
        assert gate.status is GateStatus.PASS
        assert gate.reason_code
        assert gate.summary
        assert isinstance(gate.details, dict)
        assert isinstance(gate.evidence_refs, tuple)


def test_qa_behavior_003_repeated_certification_is_bitwise_deterministic(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory()

    first = certify_bundle(bundle)
    second = certify_bundle(bundle)

    assert first.to_dict() == second.to_dict()
    assert first.trace_id == second.trace_id
    assert first.bundle_digest == second.bundle_digest
