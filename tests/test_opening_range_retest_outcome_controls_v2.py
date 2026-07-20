from __future__ import annotations

import pytest

from research.opening_range_retest_outcomes_v2.controls import CONTROL_CASES, build_negative_control_report, execute_control_case, executor_expectation_imports, executor_expected_result_leaks
from research.opening_range_retest_outcomes_v2.oracle import control_report_failures


@pytest.mark.parametrize("case", CONTROL_CASES, ids=lambda case: case.control_id)
def test_orb_outcome_negative_control(case) -> None:
    result = execute_control_case(case)
    assert result.status == "PASS", result.error
    assert set(result.observed_failures) == set(case.expected_failures)
    assert result.unrelated_failures == ()
    assert result.missing_expected_failures == ()
    assert result.case.node_id.endswith(f"[{case.control_id}]")
    assert result.target_invoked is True
    assert result.mutation_applied is True
    assert result.fixture_hash_before != result.fixture_hash_after


def test_executable_control_report_is_bound_to_real_nodes() -> None:
    report = build_negative_control_report(frozen_code_sha="frozen", implementation_tree_hash="tree")
    assert report["verdict"] == "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED"
    assert report["collected"] >= 90
    assert report["executed"] == report["collected"]
    assert report["passed"] == report["executed"]
    assert report["failed"] == 0
    assert report["skipped"] == 0
    assert report["xfailed"] == 0
    assert report["xpassed"] == 0
    assert report["duplicate_ids"] == 0
    assert report["expected_result_leak_count"] == 0
    assert report["direct_expected_result_leak_count"] == 0
    assert report["indirect_expected_result_leak_count"] == 0
    assert report["executor_expectation_import_count"] == 0
    assert report["exact_failure_set_match_count"] == report["control_count"]
    assert report["unexpected_failure_count"] == 0
    assert report["missing_expected_failure_count"] == 0
    assert report["non_isolated_mutation_count"] == 0
    assert report["clean_fixture_failure_count"] == 0
    assert report["non_invoked_target_count"] == 0
    assert report["non_mutating_control_count"] == 0
    assert report["duplicate_control_fingerprint_count"] == 0
    assert report["unique_control_fingerprint_count"] == report["control_count"]
    assert report["failures"] == []
    assert executor_expected_result_leaks() == []
    assert executor_expectation_imports() == []
    assert all(row["test_node_id"].endswith(f"[{row['control_id']}]") for row in report["controls"])
    assert all(row["target_invoked"] is True for row in report["controls"])
    assert all(row["mutation_applied"] is True for row in report["controls"])
    assert all(row["fixture_hash_before"] != row["fixture_hash_after"] for row in report["controls"])
    assert all(".control_cases." in row["executor_function"] for row in report["controls"])
    assert all(row["missing_expected_failures"] == [] for row in report["controls"])
    assert all(row["unrelated_failures"] == [] for row in report["controls"])


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        (lambda report: report.__setitem__("unexpected_failure_count", 1), "NEGATIVE_CONTROL_METRIC_NONZERO:unexpected_failure_count"),
        (lambda report: report.__setitem__("non_isolated_mutation_count", 1), "NEGATIVE_CONTROL_METRIC_NONZERO:non_isolated_mutation_count"),
        (lambda report: report.__setitem__("captured_pytest_node_ids", []), "NEGATIVE_CONTROL_PYTEST_NODE_BINDING_MISMATCH"),
        (lambda report: report.__setitem__("category_source_hashes", {}), "NEGATIVE_CONTROL_CATEGORY_HASH_MISSING"),
        (lambda report: report.__setitem__("frozen_code_sha", "stale"), "NEGATIVE_CONTROL_FROZEN_SHA_MISMATCH"),
        (lambda report: report.__setitem__("implementation_tree_hash", "stale"), "NEGATIVE_CONTROL_IMPLEMENTATION_TREE_MISMATCH"),
        (lambda report: report.__setitem__("control_report_self_hash", "stale"), "NEGATIVE_CONTROL_REPORT_SELF_HASH_MISMATCH"),
    ],
)
def test_oracle_rejects_forged_negative_control_report(mutation, expected_failure) -> None:
    report = build_negative_control_report(frozen_code_sha="frozen", implementation_tree_hash="tree")

    mutation(report)

    failures = control_report_failures(report, frozen_code_sha="frozen", implementation_tree_hash="tree")
    assert expected_failure in failures
