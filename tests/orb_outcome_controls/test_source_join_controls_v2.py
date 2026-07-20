from __future__ import annotations

import ast
import inspect

import pytest

from research.opening_range_retest_outcomes_v2.control_protocol import ControlExpectation, MutationSpec, RawExecution
from research.opening_range_retest_outcomes_v2.control_cases.source_join import execute_source_join_spec, source_join_specs


EXPECTATIONS = {
    "S3_SOURCE_RECORD_MISSING_FROM_MANIFEST_JOIN": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_SOURCE_MISSING_PHYSICAL_FILE": ("SOURCE_MISSING_OR_SYMLINK",),
    "S3_SOURCE_SHA_MISMATCH": ("SOURCE_BYTE_IDENTITY_MISMATCH",),
    "S3_SOURCE_SIZE_MISMATCH": ("SOURCE_BYTE_IDENTITY_MISMATCH",),
    "S3_SOURCE_ABSOLUTE_PATH": ("SOURCE_PATH_TRAVERSAL",),
    "S3_SOURCE_TRAVERSAL_PATH": ("SOURCE_PATH_TRAVERSAL",),
    "S3_SOURCE_SYMLINK_FILE": ("SOURCE_MISSING_OR_SYMLINK",),
    "S3_SOURCE_SYMLINK_ANCESTOR": ("SOURCE_MISSING_OR_SYMLINK",),
    "S3_SOURCE_SCHEMA_ORDER": ("SOURCE_SCHEMA_MISMATCH",),
    "S3_SOURCE_SCHEMA_MISSING_COLUMN": ("SOURCE_SCHEMA_MISMATCH",),
    "S3_SOURCE_SYMBOL_MISMATCH": ("SOURCE_SYMBOL_MISMATCH",),
    "S3_SOURCE_SESSION_MISMATCH": ("SOURCE_SESSION_MISMATCH",),
    "S3_SOURCE_OHLC_NON_POSITIVE": ("SOURCE_OHLC_INVALID",),
    "S3_SOURCE_OHLC_NAN": ("SOURCE_OHLC_INVALID",),
    "S3_SOURCE_OHLC_INFINITE": ("SOURCE_OHLC_INVALID",),
    "S3_SOURCE_OHLC_BOUNDS": ("SOURCE_OHLC_BOUNDS_INVALID",),
    "S3_JOIN_RECORD_ID_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_PATH_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_SHA_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_MANIFEST_HASH_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_MANIFEST_VERSION_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_PROVENANCE_SYMBOL_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_PROVENANCE_SESSION_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_CORE_SYMBOL_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_JOIN_CORE_SESSION_MISMATCH": ("SOURCE_PROVENANCE_MISMATCH",),
    "S3_SOURCE_VALIDATION_BLOCKS_MEASURED": ("SOURCE_VALIDATION_FAILED",),
}


@pytest.mark.parametrize("spec", source_join_specs(), ids=lambda spec: spec.control_id)
def test_source_join_negative_control(spec: MutationSpec) -> None:
    raw = execute_source_join_spec(spec)
    expectation = ControlExpectation(spec.control_id, EXPECTATIONS[spec.control_id])

    assert isinstance(raw, RawExecution)
    assert set(raw.observed_failures) == set(expectation.expected_failures)
    assert raw.target_invoked is True
    assert raw.mutation_applied is True
    assert raw.fixture_hash_before != raw.fixture_hash_after
    assert raw.target_output_hash


def test_source_join_control_inventory_is_exact_and_unique() -> None:
    specs = source_join_specs()
    control_ids = [spec.control_id for spec in specs]
    fingerprints = {
        (spec.control_id, spec.category, spec.mutation_kind, spec.target_function, tuple(sorted(spec.mutation_payload.items())))
        for spec in specs
    }

    spec_count = sum(1 for _ in specs)
    unique_control_id_count = sum(1 for _ in set(control_ids))
    fingerprint_count = sum(1 for _ in fingerprints)
    assert spec_count == 26
    assert unique_control_id_count == spec_count
    assert fingerprint_count == spec_count
    assert set(control_ids) == set(EXPECTATIONS)
    assert {spec.category for spec in specs} == {"source_join"}
    assert all(spec.control_id.startswith("S3_") for spec in specs)


def test_source_join_executors_do_not_access_expectations() -> None:
    import research.opening_range_retest_outcomes_v2.control_cases.source_join as source_join

    tree = ast.parse(inspect.getsource(source_join))
    banned_names = {"ControlExpectation", "expected", "expected_failure", "expected_failures", "_expected", "_first_failure"}
    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in banned_names:
            leaks.append((node.id, node.lineno))
        if isinstance(node, ast.Attribute) and node.attr in banned_names:
            leaks.append((node.attr, node.lineno))

    assert leaks == []
