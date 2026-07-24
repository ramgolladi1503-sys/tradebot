from __future__ import annotations

import ast
import inspect

import pytest

from research.opening_range_retest_outcomes_v2.control_cases import temporal_horizon
from research.opening_range_retest_outcomes_v2.control_protocol import ControlExpectation, MutationSpec, RawExecution


SPECS = temporal_horizon.temporal_horizon_specs()
EXPECTATIONS = {item.control_id: item for item in temporal_horizon.temporal_horizon_expectations()}


@pytest.mark.parametrize("spec", SPECS, ids=[item.control_id for item in SPECS])
def test_temporal_horizon_control_observes_exact_failure(spec: MutationSpec) -> None:
    raw = temporal_horizon.execute_temporal_horizon_control(spec)
    expectation = EXPECTATIONS[spec.control_id]

    assert isinstance(raw, RawExecution)
    assert set(raw.observed_failures) == set(expectation.expected_failures)
    assert raw.target_invoked is True
    assert raw.mutation_applied is True
    assert raw.fixture_hash_before != raw.fixture_hash_after
    assert raw.target_output_hash


def test_temporal_horizon_controls_cover_required_contract_surface() -> None:
    control_ids = {item.control_id for item in SPECS}
    assert "S4_READYNESS_MALFORMED_TIMESTAMP" in control_ids
    assert "S4_READYNESS_OUTSIDE_SESSION" in control_ids
    assert "S4_COMPLETED_BAR_OFF_GRID_SECONDS" in control_ids
    assert "S4_COMPLETED_BAR_REQUIRED" in control_ids
    assert "S4_SAME_TIME_EXCLUDED_FROM_ENTRY" in control_ids
    assert "S4_LATER_ENTRY_REQUIRED" in control_ids
    assert "S4_TIMESTAMP_DUPLICATE" in control_ids
    assert "S4_TIMESTAMP_NON_MONOTONIC" in control_ids
    assert "S4_TIMESTAMP_CADENCE_GAP" in control_ids
    assert "S4_TIMESTAMP_WRONG_SESSION_DATE" in control_ids
    assert "S4_EXACT_HORIZON_MISSING_MINUTE" in control_ids
    assert "S4_NO_FALL_FORWARD" in control_ids
    assert "S4_HORIZON_CONSERVATION" in control_ids
    assert "S4_SESSION_ENDED_BEFORE_HORIZON" in control_ids
    assert "S4_FUTURE_MUTATION_BLOCKED" in control_ids


def test_temporal_horizon_uses_shared_protocol_types() -> None:
    assert all(isinstance(item, MutationSpec) for item in SPECS)
    assert all(isinstance(item, ControlExpectation) for item in EXPECTATIONS.values())
    assert {item.control_id for item in SPECS} == set(EXPECTATIONS)
    assert all(item.category == "temporal_horizon" for item in SPECS)


def test_temporal_horizon_fingerprints_are_unique() -> None:
    fingerprints = []
    for spec in SPECS:
        raw = temporal_horizon.execute_temporal_horizon_control(spec)
        fingerprints.append(temporal_horizon.control_fingerprint(spec, raw))

    fingerprint_count = sum(1 for _ in fingerprints)
    unique_fingerprint_count = sum(1 for _ in set(fingerprints))
    assert fingerprint_count == unique_fingerprint_count


def test_temporal_horizon_executor_has_no_expectation_access() -> None:
    source = inspect.getsource(temporal_horizon.execute_temporal_horizon_control)
    tree = ast.parse(source)

    forbidden_names = {"expected", "expectation", "ControlExpectation"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names
        if isinstance(node, ast.Attribute):
            assert "expected" not in node.attr
