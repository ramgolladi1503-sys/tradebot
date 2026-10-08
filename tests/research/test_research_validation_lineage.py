from datetime import datetime, timedelta, timezone

from core.research_registry.research_models import (
    ExperimentResultReference,
    ExperimentVersion,
    MarketUniverse,
    ParameterSet,
    ResearchExperiment,
)
from core.research_registry.research_types import ResearchStage
from core.research_validation.lineage import audit_experiment_lineage, certify_research_from_registry, lineage_digest
from core.research_validation.policy import CertificationInput


def _version(version_id="V1", *, created=None, commit="abc123", branch="research/test"):
    return ExperimentVersion(
        version_id=version_id,
        created_timestamp=created or datetime(2026, 1, 1, tzinfo=timezone.utc),
        author="tester",
        branch=branch,
        commit=commit,
        market_universe=MarketUniverse(dataset="corpus-v1", market="NIFTY", timeframe="5m"),
        parameters=ParameterSet(parameters={"x": "1"}),
        reason="falsify hypothesis",
        result=ExperimentResultReference(expected_behavior="positive", actual_behavior="positive", limitations=[], conclusion="continue"),
        stage=ResearchStage.TESTED,
    )


def _experiment(experiment_id="E1", *, parent="H1", versions=None):
    return ResearchExperiment(experiment_id=experiment_id, parent_hypothesis_id=parent, versions=versions if versions is not None else [_version()])


def _evidence(**overrides):
    values = dict(hypothesis_id="H1", registered_experiments=999, declared_experiments=1, parameter_stability_pass=True, wfa_pass=True, pbo=0.1, psr=0.99, dsr=0.99, actual_track_record=500, minimum_track_record=100, power=0.9, cost_robust_pass=True, holdout_status="PASS", prospective_status="PASS")
    values.update(overrides)
    return CertificationInput(**values)


def _cert(experiments, evidence=None):
    evidence = evidence or _evidence(declared_experiments=len(experiments))
    return certify_research_from_registry(evidence, experiments, expected_lineage_digest=lineage_digest(experiments))


def test_registry_count_overrides_untrusted_caller_count():
    experiments = [_experiment()]
    assert _cert(experiments).status == "CERTIFIED_RESEARCH"


def test_lineage_digest_is_required():
    verdict = certify_research_from_registry(_evidence(), [_experiment()], expected_lineage_digest=None)
    assert verdict.status == "BLOCKED"
    assert "LINEAGE_DIGEST_REQUIRED" in verdict.reasons


def test_declared_count_must_match_actual_registry_count():
    experiments = [_experiment()]
    verdict = certify_research_from_registry(_evidence(declared_experiments=2), experiments, expected_lineage_digest=lineage_digest(experiments))
    assert verdict.status == "BLOCKED"
    assert "SEARCH_HISTORY_INCOMPLETE" in verdict.reasons


def test_parent_hypothesis_mismatch_blocks():
    audit = audit_experiment_lineage([_experiment(parent="OTHER")], hypothesis_id="H1")
    assert not audit.passed and "PARENT_HYPOTHESIS_MISMATCH" in audit.reasons


def test_duplicate_experiment_id_blocks():
    audit = audit_experiment_lineage([_experiment(), _experiment()], hypothesis_id="H1")
    assert not audit.passed and "DUPLICATE_EXPERIMENT_ID" in audit.reasons


def test_duplicate_version_id_within_experiment_blocks():
    versions = [_version("V1"), _version("V1", created=datetime(2026, 1, 2, tzinfo=timezone.utc))]
    audit = audit_experiment_lineage([_experiment(versions=versions)], hypothesis_id="H1")
    assert not audit.passed and "DUPLICATE_VERSION_ID" in audit.reasons


def test_same_local_version_id_in_distinct_experiments_is_allowed():
    assert audit_experiment_lineage([_experiment("E1"), _experiment("E2")], hypothesis_id="H1").passed


def test_experiment_without_version_blocks():
    audit = audit_experiment_lineage([_experiment(versions=[])], hypothesis_id="H1")
    assert not audit.passed and "EXPERIMENT_WITHOUT_VERSION" in audit.reasons


def test_non_monotonic_version_history_blocks():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    audit = audit_experiment_lineage([_experiment(versions=[_version("V1", created=t0 + timedelta(days=1)), _version("V2", created=t0)])], hypothesis_id="H1")
    assert not audit.passed and "NON_MONOTONIC_VERSION_HISTORY" in audit.reasons


def test_missing_commit_or_branch_provenance_blocks():
    for version in (_version(commit=""), _version(branch="")):
        assert not audit_experiment_lineage([_experiment(versions=[version])], hypothesis_id="H1").passed


def test_nested_mutation_changes_digest_and_blocks_against_frozen_authority():
    experiments = [_experiment()]
    frozen = lineage_digest(experiments)
    experiments[0].versions[0].parameters.parameters["x"] = "999"
    assert lineage_digest(experiments) != frozen
    verdict = certify_research_from_registry(_evidence(), experiments, expected_lineage_digest=frozen)
    assert verdict.status == "BLOCKED"
    assert "LINEAGE_DIGEST_MISMATCH" in verdict.reasons


def test_appending_version_after_freeze_changes_digest():
    experiments = [_experiment()]
    frozen = lineage_digest(experiments)
    experiments[0].versions.append(_version("V2", created=datetime(2026, 1, 2, tzinfo=timezone.utc)))
    assert lineage_digest(experiments) != frozen


def test_lineage_failure_preserves_read_only_non_execution_safety_contract():
    experiments = [_experiment(parent="OTHER")]
    verdict = certify_research_from_registry(_evidence(), experiments, expected_lineage_digest=lineage_digest(experiments))
    assert verdict.status == "BLOCKED"
    assert verdict.read_only is True
    assert verdict.is_order_action is False
    assert verdict.broker_api_called is False
    assert verdict.allowed_for_live_execution is False
    assert verdict.append is False
