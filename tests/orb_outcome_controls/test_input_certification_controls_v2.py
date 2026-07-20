from __future__ import annotations

import ast
import inspect

import pytest

from research.opening_range_retest_outcomes_v2.control_cases import input_certification
from research.opening_range_retest_outcomes_v2.control_cases.input_certification import (
    execute_input_certification_control,
    inspect_input_certification_mutation,
    input_certification_mutations,
    verify_clean_input_fixture,
)

EXPECTATIONS = {
    "INPUT_SIDECAR_SOURCE_MANIFEST": ("INPUT_SIDECAR_MISMATCH:source_manifest",),
    "INPUT_SIDECAR_CANDIDATE_LEDGER": ("INPUT_SIDECAR_MISMATCH:candidate_ledger",),
    "INPUT_SIDECAR_PHASE1_SUMMARY": ("INPUT_SIDECAR_MISMATCH:phase1_summary",),
    "INPUT_SIDECAR_RECONCILIATION": ("INPUT_SIDECAR_MISMATCH:reconciliation",),
    "INPUT_SIDECAR_PHASE1_CERTIFICATION": ("INPUT_SIDECAR_MISMATCH:phase1_certification",),
    "INPUT_SOURCE_MANIFEST_HASH": ("INPUT_SOURCE_MANIFEST_MISMATCH",),
    "INPUT_SOURCE_MANIFEST_COUNT": ("INPUT_SOURCE_MANIFEST_MISMATCH",),
    "INPUT_CANDIDATE_LEDGER_CORE_HASH": ("INPUT_CANDIDATE_LEDGER_MISMATCH",),
    "INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH": ("INPUT_CANDIDATE_LEDGER_MISMATCH",),
    "INPUT_CANDIDATE_LEDGER_COUNT": ("INPUT_CANDIDATE_LEDGER_MISMATCH",),
    "INPUT_SUMMARY_VERDICT": ("INPUT_SUMMARY_VERDICT_MISMATCH",),
    "INPUT_RECONCILIATION_VERDICT": ("INPUT_RECONCILIATION_MISMATCH",),
    "INPUT_RECONCILIATION_V1_COUNT": ("INPUT_RECONCILIATION_MISMATCH",),
    "INPUT_RECONCILIATION_V2_COUNT": ("INPUT_RECONCILIATION_MISMATCH",),
    "INPUT_DECEPTIVE_CERTIFICATION": ("INPUT_CERTIFICATION_MISMATCH",),
}


def test_clean_input_fixture_passes_before_any_mutation() -> None:
    assert verify_clean_input_fixture() == ()


@pytest.mark.parametrize("spec", input_certification_mutations(), ids=lambda spec: spec.control_id)
def test_input_certification_control_reports_exact_raw_failures(spec) -> None:
    raw = execute_input_certification_control(spec)

    assert raw.observed_failures == EXPECTATIONS[spec.control_id]
    assert raw.target_invoked is True
    assert raw.mutation_applied is True
    assert raw.fixture_hash_before != raw.fixture_hash_after
    assert raw.target_output_hash


def test_input_certification_control_inventory_is_complete_and_unique() -> None:
    specs = input_certification_mutations()
    control_ids = [spec.control_id for spec in specs]

    spec_count = sum(1 for _ in specs)
    assert spec_count == 15
    assert sorted(control_ids) == sorted(EXPECTATIONS)
    unique_control_id_count = sum(1 for _ in set(control_ids))
    assert unique_control_id_count == spec_count
    assert {spec.category for spec in specs} == {"input_certification"}
    assert {spec.target_function for spec in specs} == {"oracle.verify_input_bundle"}


@pytest.mark.parametrize("spec", input_certification_mutations(), ids=lambda spec: spec.control_id)
def test_input_certification_sidecar_and_content_mutations_are_isolated(spec) -> None:
    result = inspect_input_certification_mutation(spec)
    observed = set(result["failures"])
    input_name = spec.mutation_payload["input_name"]
    before = result["before"]
    after = result["after"]

    if spec.mutation_kind == "sidecar_hash":
        assert observed == {f"INPUT_SIDECAR_MISMATCH:{input_name}"}
        assert before[input_name]["artifact"] == after[input_name]["artifact"]
        assert before[input_name]["sidecar"] != after[input_name]["sidecar"]
    else:
        assert all(not failure.startswith("INPUT_SIDECAR_MISMATCH:") for failure in observed)
        assert before[input_name]["artifact"] != after[input_name]["artifact"]
        assert after[input_name]["sidecar"].split()[0] == after[input_name]["artifact"]


def test_input_certification_executor_has_no_expectation_access() -> None:
    source = inspect.getsource(input_certification)
    tree = ast.parse(source)
    forbidden_names = {
        "expected",
        "expectation",
        "expected_failure",
        "expected_failures",
        "ControlExpectation",
        "_first_failure",
    }

    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            leaks.append(node.id)
        if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
            leaks.append(node.attr)

    assert leaks == []
