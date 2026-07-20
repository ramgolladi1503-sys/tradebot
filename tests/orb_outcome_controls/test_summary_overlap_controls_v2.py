from __future__ import annotations

import pytest

from research.opening_range_retest_outcomes_v2.control_cases.summary_overlap import (
    CONTROL_CASES,
    control_fingerprint,
    execute_control,
)


@pytest.mark.parametrize("control", CONTROL_CASES, ids=lambda control: control.spec.control_id)
def test_summary_overlap_control(control):
    raw = execute_control(control)

    assert raw.target_invoked is True
    assert raw.mutation_applied is True
    assert raw.fixture_hash_before != raw.fixture_hash_after
    assert set(raw.observed_failures) == set(control.expectation.expected_failures)


def test_summary_overlap_control_fingerprints_are_unique():
    fingerprints = [control_fingerprint(control, execute_control(control)) for control in CONTROL_CASES]

    fingerprint_count = sum(1 for _ in fingerprints)
    unique_fingerprint_count = sum(1 for _ in set(fingerprints))
    assert fingerprint_count == unique_fingerprint_count


def test_summary_overlap_controls_are_bound_to_shared_protocol_types():
    for control in CONTROL_CASES:
        assert control.spec.control_id == control.expectation.control_id
        assert control.spec.category == "summary_overlap"
        assert control.spec.target_function in {
            "control_cases.summary_overlap.exact_summary_failures",
            "control_cases.summary_overlap.exact_overlap_failures",
            "oracle.oracle_independence_failures",
        }
        assert control.test_node_id.endswith(f"[{control.spec.control_id}]")
