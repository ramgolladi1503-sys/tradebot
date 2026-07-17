from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from case_schema import (
    ALLOWED_CERTIFICATION_TOOLS,
    PROHIBITED_TOOLS,
    AgentEvalCaseError,
    load_case_matrix,
)


MATRIX = Path(__file__).with_name("golden_case_matrix_v1.json")
EXPECTED_COUNTS = {
    "happy_path": 5,
    "missing_evidence": 6,
    "invalid_evidence": 8,
    "conflicting_evidence": 5,
    "tool_failure": 5,
    "prompt_injection": 5,
    "wrong_tool_temptation": 3,
    "loop_control": 3,
}


def test_matrix_loads_with_unique_complete_inventory():
    cases = load_case_matrix(MATRIX)
    identifiers = tuple(case.case_id for case in cases)

    assert sum(1 for _ in cases) == 40
    assert identifiers == tuple(dict.fromkeys(identifiers))
    assert Counter(case.category for case in cases) == EXPECTED_COUNTS


def test_every_case_has_bounded_safe_tool_expectations():
    for case in load_case_matrix(MATRIX):
        assert set(case.expected.required_tools).issubset(ALLOWED_CERTIFICATION_TOOLS)
        assert PROHIBITED_TOOLS.issubset(case.expected.forbidden_tools)
        assert set(case.expected.required_tools).isdisjoint(case.expected.forbidden_tools)
        assert 1 <= case.expected.max_tool_calls <= 12


def test_all_abstention_cases_withhold_strategy_claim():
    abstentions = tuple(
        case for case in load_case_matrix(MATRIX) if case.expected.must_abstain
    )

    assert abstentions != ()
    assert all(case.expected.strategy_verdict == "WITHHELD" for case in abstentions)
    assert all(case.expected.evidence_certification != "CERTIFIED" for case in abstentions)


def test_prompt_injection_cases_keep_untrusted_text_out_of_tool_authority():
    injections = tuple(
        case for case in load_case_matrix(MATRIX) if case.category == "prompt_injection"
    )

    assert sum(1 for _ in injections) == 5
    assert all(case.untrusted_text for case in injections)
    assert all(
        set(case.expected.required_tools).isdisjoint(PROHIBITED_TOOLS)
        for case in injections
    )


def test_unsafe_tool_temptations_never_require_unsafe_tool():
    temptations = tuple(
        case
        for case in load_case_matrix(MATRIX)
        if case.category == "wrong_tool_temptation"
    )

    assert sum(1 for _ in temptations) == 3
    assert all(case.expected.must_abstain for case in temptations)
    assert all(
        case.expected.required_tools == ("inspect_certification_bundle",)
        for case in temptations
    )


def test_tool_failure_cases_have_fault_injection_and_larger_bounded_budget():
    failures = tuple(
        case for case in load_case_matrix(MATRIX) if case.category == "tool_failure"
    )

    assert sum(1 for _ in failures) == 5
    assert all("transient_tool_failure" in case.faults for case in failures)
    assert all(case.expected.max_tool_calls == 8 for case in failures)
    assert all(case.expected.must_abstain for case in failures)


def test_invalid_category_is_rejected(tmp_path: Path):
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    payload["cases"][0]["category"] = "marketing_demo"
    path = tmp_path / "invalid-category.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AgentEvalCaseError, match="unsupported category"):
        load_case_matrix(path)


def test_unknown_required_tool_is_rejected(tmp_path: Path):
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    payload["cases"][0]["required_tools"].append("unknown_agent_tool")
    path = tmp_path / "invalid-tool.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AgentEvalCaseError, match="unknown required tools"):
        load_case_matrix(path)


def test_missing_prohibited_tool_guard_is_rejected(tmp_path: Path):
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    omitted = sorted(PROHIBITED_TOOLS)[0]
    payload["cases"][0]["forbidden_tools"] = sorted(PROHIBITED_TOOLS - {omitted})
    path = tmp_path / "unsafe-defaults.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AgentEvalCaseError, match="omits prohibited tools"):
        load_case_matrix(path)


def test_duplicate_case_identifier_is_rejected(tmp_path: Path):
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    path = tmp_path / "duplicate-case.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AgentEvalCaseError, match="identifiers must be unique"):
        load_case_matrix(path)
