from __future__ import annotations

import pytest

from research.opening_range_retest_outcomes_v2.controls import CONTROL_CASES, build_negative_control_report, execute_control_case


@pytest.mark.parametrize("case", CONTROL_CASES, ids=lambda case: case.control_id)
def test_orb_outcome_negative_control(case) -> None:
    result = execute_control_case(case)
    assert result.status == "PASS", result.error
    assert result.observed_failure == case.expected_failure
    assert result.pytest_node_id.endswith(f"[{case.control_id}]")


def test_executable_control_report_is_bound_to_real_nodes() -> None:
    report = build_negative_control_report(frozen_code_sha="frozen", implementation_tree_hash="tree")
    assert report["verdict"] == "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED"
    assert report["collected"] >= 75
    assert report["executed"] == report["collected"]
    assert report["passed"] == report["executed"]
    assert report["failed"] == 0
    assert report["skipped"] == 0
    assert report["xfailed"] == 0
    assert report["xpassed"] == 0
    assert report["duplicate_ids"] == 0
    assert report["failures"] == []
    assert all(row["pytest_node_id"].endswith(f"[{row['control_id']}]") for row in report["controls"])
    assert all("negative mutation" not in row["mutation"].lower() for row in report["controls"])
