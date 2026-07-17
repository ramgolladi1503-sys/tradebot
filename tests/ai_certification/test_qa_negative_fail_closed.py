from __future__ import annotations

from core.ai_certification import (
    BacktestCertificationAgent,
    EvidenceCertification,
    StrategyVerdict,
    certify_bundle,
)


def test_qa_fail_closed_001_failure_is_not_downgraded_by_missing_evidence(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "dataset_manifest.json": {"stale_quote_count": 1},
        },
        omit={"fill_evidence.json"},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.INVALID_DUE_TO_DATA
    assert "bundle_manifest:REQUIRED_ARTIFACTS_MISSING" in report.blockers
    assert "data_provenance:STALE_QUOTE_COUNT" in report.blockers


def test_qa_fail_closed_002_malformed_artifact_with_valid_hash_is_insufficient(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        raw_artifacts={"timing_evidence.json": "{not-json"},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.INSUFFICIENT_EVIDENCE
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert "temporal_causality:TIMING_EVIDENCE_UNAVAILABLE" in report.blockers


def test_qa_negative_001_missing_dataset_identity_is_not_assumed(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={"dataset_manifest.json": {"provider": ""}},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.INSUFFICIENT_EVIDENCE
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert "data_provenance:DATASET_PROVENANCE_INCOMPLETE" in report.blockers


def test_qa_negative_002_stale_quotes_reject_data_certification(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={"dataset_manifest.json": {"stale_quote_count": 3}},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.INVALID_DUE_TO_DATA
    assert "data_provenance:STALE_QUOTE_COUNT" in report.blockers


def test_qa_negative_003_fallback_fill_rejects_execution_realism(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "fill_evidence.json": {"fallback_liquidity_fill_count": 1}
        },
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.INVALID_DUE_TO_DATA
    assert "execution_realism:FALLBACK_LIQUIDITY_FILL_COUNT" in report.blockers


def test_qa_negative_004_financial_mismatch_blocks_certification(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={"cost_reconciliation.json": {"net_pnl": -14.0}},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert "financial_reconciliation:GROSS_COST_NET_MISMATCH" in report.blockers


def test_qa_negative_005_repeated_holdout_use_blocks_certification(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={"wfa_results.json": {"repeated_holdout_run_count": 1}},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert "walk_forward_integrity:REPEATED_HOLDOUT_USE" in report.blockers


def test_qa_negative_006_failed_negative_control_blocks_certification(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={
            "negative_controls.json": {
                "controls": {"timing_shift": False},
            }
        },
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert "negative_controls:NEGATIVE_CONTROL_FAILED" in report.blockers


def test_qa_negative_007_failed_test_run_blocks_certification(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={"test_results.json": {"failed": 2, "passed": 73}},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert "test_evidence:TESTS_NOT_GREEN" in report.blockers


def test_qa_fail_closed_003_validator_exception_returns_agent_error(
    qa_bundle_factory,
):
    def exploding_validator(bundle, policy):
        del bundle, policy
        raise RuntimeError("simulated validator crash")

    report = BacktestCertificationAgent(validators=(exploding_validator,)).certify(
        qa_bundle_factory()
    )

    assert report.evidence_certification is EvidenceCertification.AGENT_ERROR
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert report.blockers == (
        "exploding_validator:VALIDATOR_EXCEPTION",
    )


def test_qa_negative_008_policy_version_mismatch_rejects_bundle(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        manifest_overrides={"policy_version": "obsolete-policy-v0"},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.REJECTED
    assert report.strategy_verdict is StrategyVerdict.INVALID_DUE_TO_DATA
    assert "bundle_manifest:POLICY_VERSION_MISMATCH" in report.blockers


def test_qa_behavior_004_unknown_strategy_verdict_is_warning_not_fake_methodology_failure(
    qa_bundle_factory,
):
    bundle = qa_bundle_factory(
        artifact_overrides={"strategy_result.json": {"verdict": "GUARANTEED_PROFIT"}},
    )

    report = certify_bundle(bundle)

    assert report.evidence_certification is EvidenceCertification.CERTIFIED
    assert report.strategy_verdict is StrategyVerdict.WITHHELD
    assert report.blockers == ()
    assert "strategy_result_consistency:UNKNOWN_STRATEGY_VERDICT" in report.warnings
