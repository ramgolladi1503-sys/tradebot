from __future__ import annotations

from tools.code_excellence.ariadne import build_fix_contract, cluster_failure_text


def test_ariadne_groups_multiple_failures_from_same_fixture_drift():
    text = """
FAILED tests/test_alpha.py::test_one
E fixture 'runtime_config' not found
FAILED tests/test_beta.py::test_two
E fixture 'runtime_config' not found
FAILED tests/test_gamma.py::test_three
E fixture 'runtime_config' not found
FAILED tests/test_delta.py::test_four
E fixture 'runtime_config' not found
"""

    report = cluster_failure_text(text)

    assert report.cluster_count == 1
    cluster = report.clusters[0]
    assert cluster.reason == "fixture"
    assert cluster.confidence == "CONFIRMED"
    assert cluster.failure_count == 4
    assert cluster.proof == ("shared_fixture_signal",)


def test_ariadne_separates_unrelated_failure_clusters():
    text = """
FAILED tests/test_fixture.py::test_fixture
E fixture 'runtime_config' not found
FAILED tests/test_schema.py::test_schema
E KeyError: 'candidate_id'
FAILED tests/test_broker.py::test_boundary
E AssertionError: broker boundary violated proof:safety trace
"""

    report = cluster_failure_text(text)

    reasons = sorted(cluster.reason for cluster in report.clusters)
    assert reasons == ["fixture", "missing_field", "safety_boundary"]
    assert report.cluster_count == 3


def test_ariadne_marks_low_confidence_as_unknown():
    text = """
FAILED tests/test_unknown.py::test_unknown
some loose output without a stable root cause signal
"""

    report = cluster_failure_text(text)

    assert report.cluster_count == 1
    assert report.clusters[0].confidence == "UNKNOWN"
    assert report.clusters[0].reason == "module"


def test_ariadne_does_not_create_fix_contract_without_proof():
    text = """
FAILED tests/test_unknown.py::test_unknown
some loose output without a stable root cause signal
"""

    cluster = cluster_failure_text(text).clusters[0]
    contract = build_fix_contract(cluster)

    assert contract.allowed is False
    assert contract.reason == "proof_required_before_fix_contract"


def test_ariadne_creates_fix_contract_when_cluster_has_proof():
    text = """
FAILED tests/test_alpha.py::test_one
E fixture 'runtime_config' not found
FAILED tests/test_beta.py::test_two
E fixture 'runtime_config' not found
"""

    cluster = cluster_failure_text(text).clusters[0]
    contract = build_fix_contract(cluster)

    assert contract.allowed is True
    assert contract.reason == "cluster_has_root_cause_proof"
    assert contract.proof == ("shared_fixture_signal",)


def test_ariadne_clusters_missing_field_failures():
    text = """
FAILED tests/test_schema_a.py::test_schema_a
E KeyError: 'candidate_id'
FAILED tests/test_schema_b.py::test_schema_b
E missing field candidate_id
"""

    report = cluster_failure_text(text)

    assert report.cluster_count == 1
    assert report.clusters[0].reason == "missing_field"
    assert report.clusters[0].confidence == "CONFIRMED"
    assert report.clusters[0].failure_count == 2
