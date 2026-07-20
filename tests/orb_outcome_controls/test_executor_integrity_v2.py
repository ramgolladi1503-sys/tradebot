from __future__ import annotations

import ast
from pathlib import Path

from research.opening_range_retest_outcomes_v2.control_cases import summary_overlap
from research.opening_range_retest_outcomes_v2.control_cases.summary_overlap import (
    CONTROL_CASES,
    control_fingerprint,
    execute_control,
    executor_expected_access_findings,
)


MODULE_PATH = Path(summary_overlap.__file__)


def test_s6_executors_have_no_direct_or_indirect_expectation_access():
    assert executor_expected_access_findings() == []


def test_s6_module_does_not_import_expectations_into_executors():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    executor_names = {name for name in summary_overlap.EXECUTORS.values()}
    executor_function_names = {fn.__name__ for fn in executor_names}
    forbidden_helpers = {"_expected", "_first_failure"}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in executor_function_names:
            called_names = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            assert not (called_names & forbidden_helpers)


def test_s6_static_oracle_import_controls_cover_forbidden_targets():
    observed_by_id = {control.spec.control_id: execute_control(control).observed_failures for control in CONTROL_CASES}

    assert observed_by_id["STATIC_FORBIDDEN_ENGINE_IMPORT_FROM"] == ("ORACLE_FORBIDDEN_IMPORT",)
    assert observed_by_id["STATIC_FORBIDDEN_OVERLAP_IMPORT_FROM"] == ("ORACLE_FORBIDDEN_IMPORT",)
    assert observed_by_id["STATIC_FORBIDDEN_ENGINE_IMPORT_ALIAS_CALL"] == ("ORACLE_FORBIDDEN_IMPORT",)
    assert observed_by_id["STATIC_FORBIDDEN_OVERLAP_IMPORT_ALIAS_CALL"] == ("ORACLE_FORBIDDEN_IMPORT",)


def test_s6_all_targets_invoked_and_mutations_proven():
    for control in CONTROL_CASES:
        raw = execute_control(control)
        assert raw.target_invoked is True
        assert raw.mutation_applied is True
        assert raw.fixture_hash_before != raw.fixture_hash_after


def test_s6_duplicate_fingerprints_absent():
    fingerprints = [control_fingerprint(control, execute_control(control)) for control in CONTROL_CASES]

    fingerprint_count = sum(1 for _ in fingerprints)
    unique_fingerprint_count = sum(1 for _ in set(fingerprints))
    assert fingerprint_count == unique_fingerprint_count
