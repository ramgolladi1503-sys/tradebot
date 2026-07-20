from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest

from research.opening_range_retest_outcomes_v2.control_protocol import MutationSpec
from research.opening_range_retest_outcomes_v2.control_cases.lineage import (
    CONTRACT_SEMANTIC_FIELD_CASES,
    LINEAGE_CONTROL_CASES,
    LINEAGE_EXPECTATIONS,
    LINEAGE_MUTATION_SPECS,
    LINEAGE_SNAPSHOT_CASES,
)
from research.opening_range_retest_outcomes_v2.contract import build_contract


BASE_MAIN_SHA = "f9a8ad7d8032254b7869bc115d92cbda53d36a00"
FROZEN_CODE_SHA = "b3b3b64da8221e8f73437c32a89e2a97b330f035"
EXECUTION_SHA = "1d013219b07e971e52dcd6caa80038d9c09a96ed"
TREE_HASH = "1d5bb386f74fd38e638b20c96039620397adba7ad56f9c61d0132812d0738630"


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _set_path(payload: dict[str, Any], dotted_path: str, replacement: Any) -> None:
    current: Any = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = replacement


def _contract_fixture() -> dict[str, Any]:
    return build_contract(
        source_authority_root="/Users/madhuram/tradebot",
        base_main_sha=BASE_MAIN_SHA,
        execution_commit_sha=EXECUTION_SHA,
        frozen_code_sha=FROZEN_CODE_SHA,
        implementation_tree_hash=TREE_HASH,
    )


def _lineage_snapshot_fixture() -> dict[str, Any]:
    return {
        "frozen_sha": FROZEN_CODE_SHA,
        "head_sha": EXECUTION_SHA,
        "is_ancestor": True,
        "expected_tree_hash": TREE_HASH,
        "frozen_tree_hash": TREE_HASH,
        "head_tree_hash": TREE_HASH,
        "changed_paths": ["docs/agent_reviews/opening_range_retest_outcome_summary_v2.json"],
    }


def _apply_mutation(spec: MutationSpec) -> tuple[str, str]:
    if spec.mutation_kind == "contract_field_replace":
        fixture = _contract_fixture()
        before = _digest(fixture)
        _set_path(fixture, str(spec.mutation_payload["path"]), spec.mutation_payload["replacement"])
        return before, _digest(fixture)
    if spec.mutation_kind == "lineage_snapshot_replace":
        fixture = _lineage_snapshot_fixture()
        before = _digest(fixture)
        fixture[str(spec.mutation_payload["snapshot_key"])] = spec.mutation_payload["replacement"]
        return before, _digest(fixture)
    raise AssertionError(f"unknown mutation kind: {spec.mutation_kind}")


@pytest.mark.parametrize("case", LINEAGE_CONTROL_CASES, ids=lambda case: case.mutation.control_id)
def test_lineage_control_case_mutations_are_executable(case) -> None:
    before, after = _apply_mutation(case.mutation)

    assert before != after
    assert case.mutation.target_function in {"verify_contract_payload", "verify_lineage_snapshot"}
    assert case.expectation.control_id == case.mutation.control_id
    assert case.expectation.expected_failures


def test_lineage_contract_cases_cover_every_semantic_field_once() -> None:
    expected_paths = {
        "schema_version",
        "contract_version",
        "mode",
        "decision",
        "reason",
        "source",
        "base_main_sha",
        "frozen_code_sha",
        "implementation_tree_hash",
        "implementation_tree_hash_algorithm",
        "implementation_tree_paths",
        "inputs.source_count",
        "inputs.source_semantic_hash",
        "inputs.candidate_count",
        "inputs.candidate_core_semantic_hash",
        "inputs.candidate_provenance_semantic_hash",
        "source_authority.logical_prefix",
        "source_authority.mutate",
        "source_authority.copy",
        "source_authority.symlink",
        "bars.label",
        "bars.session_timezone",
        "bars.session_start",
        "bars.session_last_start",
        "bars.cadence_seconds",
        "entry.primary_rule",
        "entry.price",
        "entry.same_timestamp_bar_disposition",
        "horizons_minutes",
        "horizon_terminal_rule.1",
        "horizon_terminal_rule.3",
        "horizon_terminal_rule.5",
        "horizon_terminal_rule.15",
        "horizon_terminal_rule.30",
        "horizon_terminal_rule.selection",
        "returns.BUY_CALL",
        "returns.BUY_PUT",
        "returns.unsigned",
        "mfe_mae.interval",
        "mfe_mae.BUY_CALL_MFE",
        "mfe_mae.BUY_CALL_MAE",
        "mfe_mae.BUY_PUT_MFE",
        "mfe_mae.BUY_PUT_MAE",
        "mfe_mae.mae_signed",
        "overlap.interval",
        "overlap.canonical",
        "claim_boundary",
        "read_only",
        "append",
        "is_order_action",
        "broker_api_called",
        "allowed_for_live_execution",
    }
    actual_paths = {str(case.mutation.mutation_payload["path"]) for case in CONTRACT_SEMANTIC_FIELD_CASES}

    assert actual_paths == expected_paths
    assert len(actual_paths) == len(CONTRACT_SEMANTIC_FIELD_CASES)


def test_lineage_snapshot_cases_cover_ancestry_tree_hashes_and_post_freeze_paths() -> None:
    expected_keys = {"frozen_sha", "head_sha", "is_ancestor", "frozen_tree_hash", "head_tree_hash", "changed_paths"}
    actual_keys = {str(case.mutation.mutation_payload["snapshot_key"]) for case in LINEAGE_SNAPSHOT_CASES}

    assert actual_keys == expected_keys


def test_lineage_control_fingerprints_are_unique() -> None:
    fingerprints = [
        _digest(
            {
                "control_id": case.mutation.control_id,
                "category": case.mutation.category,
                "mutation_kind": case.mutation.mutation_kind,
                "mutation_payload": case.mutation.mutation_payload,
                "target_function": case.mutation.target_function,
            }
        )
        for case in LINEAGE_CONTROL_CASES
    ]

    assert len(fingerprints) == len(set(fingerprints))


def test_lineage_mutation_specs_do_not_carry_expected_results() -> None:
    forbidden_terms = ("expected", "expected_failure", "expected_failures", "ControlExpectation")

    for spec in LINEAGE_MUTATION_SPECS:
        encoded = json.dumps(
            {
                "control_id": spec.control_id,
                "category": spec.category,
                "mutation_kind": spec.mutation_kind,
                "mutation_payload": spec.mutation_payload,
                "target_function": spec.target_function,
            },
            sort_keys=True,
        )
        assert not any(term in encoded for term in forbidden_terms)


def test_lineage_expectations_are_separate_from_mutation_specs() -> None:
    specs_by_id = {spec.control_id: spec for spec in LINEAGE_MUTATION_SPECS}
    expectations_by_id = {expectation.control_id: expectation for expectation in LINEAGE_EXPECTATIONS}

    assert set(specs_by_id) == set(expectations_by_id)
    assert len(specs_by_id) == len(LINEAGE_CONTROL_CASES)
    for control_id, spec in specs_by_id.items():
        expectation = expectations_by_id[control_id]
        assert expectation is not spec
        assert all(failure.startswith(("CONTRACT_FIELD_MISMATCH:", "FROZEN_CODE_SHA_NOT_ANCESTOR", "IMPLEMENTATION_TREE_HASH_MISMATCH", "POST_FREEZE_UNEXPECTED_PATH")) for failure in expectation.expected_failures)


def test_lineage_fixture_builder_does_not_mutate_source_fixture_between_cases() -> None:
    first = _contract_fixture()
    second = copy.deepcopy(first)
    _set_path(second, "returns.BUY_CALL", "wrong")

    assert first["returns"]["BUY_CALL"] != second["returns"]["BUY_CALL"]
    assert _contract_fixture()["returns"]["BUY_CALL"] == first["returns"]["BUY_CALL"]

