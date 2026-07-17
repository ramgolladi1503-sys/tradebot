from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CASE_ID_RE = re.compile(r"^AGENT-[A-Z]+-[0-9]{3}$")
ALLOWED_CATEGORIES = {
    "happy_path",
    "missing_evidence",
    "invalid_evidence",
    "conflicting_evidence",
    "tool_failure",
    "prompt_injection",
    "wrong_tool_temptation",
    "loop_control",
}
ALLOWED_EVIDENCE_STATUSES = {
    "CERTIFIED",
    "CONDITIONALLY_CERTIFIED",
    "REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "AGENT_ERROR",
}
ALLOWED_STRATEGY_VERDICTS = {
    "STRUCTURAL_EDGE_SUPPORTED",
    "CONDITIONALLY_SUPPORTED",
    "INSUFFICIENT_TRADES",
    "NO_STRUCTURAL_EDGE",
    "INVALID_DUE_TO_DATA",
    "INVALID_DUE_TO_LEAKAGE",
    "WITHHELD",
}
ALLOWED_CERTIFICATION_TOOLS = {
    "certify_backtest_bundle",
    "get_backtest_certification_policy",
    "inspect_certification_bundle",
    "retrieve_certification_policy_context",
    "validate_artifact_hashes",
    "validate_bundle_manifest",
    "validate_data_provenance_gate",
    "validate_execution_realism_gate",
    "validate_financial_reconciliation_gate",
    "validate_negative_controls_gate",
    "validate_source_authority_gate",
    "validate_source_provenance",
    "validate_strategy_result_gate",
    "validate_temporal_causality_gate",
    "validate_test_evidence_gate",
    "validate_walk_forward_integrity_gate",
}
PROHIBITED_TOOLS = {
    "place_order",
    "override_risk",
    "mutate_strategy",
    "run_shell",
    "git_push",
    "write_database",
}


class AgentEvalCaseError(ValueError):
    pass


@dataclass(frozen=True)
class ExpectedOutcome:
    evidence_certification: str
    strategy_verdict: str
    required_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    must_abstain: bool
    max_tool_calls: int


@dataclass(frozen=True)
class AgentEvalCase:
    case_id: str
    schema_version: str
    category: str
    request: str
    fixture: str
    faults: tuple[str, ...]
    untrusted_text: str | None
    expected: ExpectedOutcome


def load_case_matrix(path: str | Path) -> tuple[AgentEvalCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AgentEvalCaseError("evaluation matrix must be a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "1.0":
        raise AgentEvalCaseError(f"unsupported evaluation schema: {schema_version!r}")
    defaults = payload.get("defaults")
    rows = payload.get("cases")
    if not isinstance(defaults, dict) or not isinstance(rows, list):
        raise AgentEvalCaseError("evaluation matrix requires defaults and cases")
    cases = tuple(_parse_case(row, schema_version, defaults) for row in rows)
    identifiers = [case.case_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise AgentEvalCaseError("evaluation case identifiers must be unique")
    return cases


def _parse_case(row: Any, schema_version: str, defaults: dict[str, Any]) -> AgentEvalCase:
    if not isinstance(row, dict):
        raise AgentEvalCaseError("each evaluation case must be an object")
    case_id = str(row.get("case_id") or "")
    if not CASE_ID_RE.fullmatch(case_id):
        raise AgentEvalCaseError(f"invalid evaluation case id: {case_id!r}")
    category = str(row.get("category") or "")
    if category not in ALLOWED_CATEGORIES:
        raise AgentEvalCaseError(f"unsupported category for {case_id}: {category!r}")
    request = str(row.get("request") or "").strip()
    fixture = str(row.get("fixture") or "").strip()
    if not request or not fixture:
        raise AgentEvalCaseError(f"{case_id} requires request and fixture")

    evidence = str(row.get("evidence") or "")
    verdict = str(row.get("verdict") or "")
    if evidence not in ALLOWED_EVIDENCE_STATUSES:
        raise AgentEvalCaseError(f"invalid evidence status for {case_id}: {evidence!r}")
    if verdict not in ALLOWED_STRATEGY_VERDICTS:
        raise AgentEvalCaseError(f"invalid strategy verdict for {case_id}: {verdict!r}")

    required_tools = _string_tuple(row.get("required_tools"), f"{case_id}.required_tools")
    unknown_tools = sorted(set(required_tools) - ALLOWED_CERTIFICATION_TOOLS)
    if unknown_tools:
        raise AgentEvalCaseError(f"unknown required tools for {case_id}: {unknown_tools}")
    forbidden_tools = _string_tuple(
        row.get("forbidden_tools", defaults.get("forbidden_tools")),
        f"{case_id}.forbidden_tools",
    )
    if not PROHIBITED_TOOLS.issubset(forbidden_tools):
        missing = sorted(PROHIBITED_TOOLS - set(forbidden_tools))
        raise AgentEvalCaseError(f"{case_id} omits prohibited tools: {missing}")
    if set(required_tools) & set(forbidden_tools):
        raise AgentEvalCaseError(f"{case_id} requires a forbidden tool")

    max_tool_calls = int(row.get("max_tool_calls", defaults.get("max_tool_calls", 0)))
    if not 1 <= max_tool_calls <= 12:
        raise AgentEvalCaseError(f"{case_id} has invalid tool budget: {max_tool_calls}")
    must_abstain = bool(row.get("must_abstain", defaults.get("must_abstain", False)))
    faults = _string_tuple(row.get("faults", defaults.get("faults", [])), f"{case_id}.faults")
    untrusted = row.get("untrusted_text")
    if untrusted is not None and not isinstance(untrusted, str):
        raise AgentEvalCaseError(f"{case_id}.untrusted_text must be a string or null")
    if category == "prompt_injection" and not str(untrusted or "").strip():
        raise AgentEvalCaseError(f"{case_id} requires adversarial untrusted text")
    if must_abstain and verdict != "WITHHELD":
        raise AgentEvalCaseError(f"{case_id} abstention must withhold strategy verdict")

    return AgentEvalCase(
        case_id=case_id,
        schema_version=schema_version,
        category=category,
        request=request,
        fixture=fixture,
        faults=faults,
        untrusted_text=untrusted,
        expected=ExpectedOutcome(
            evidence_certification=evidence,
            strategy_verdict=verdict,
            required_tools=required_tools,
            forbidden_tools=forbidden_tools,
            must_abstain=must_abstain,
            max_tool_calls=max_tool_calls,
        ),
    )


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise AgentEvalCaseError(f"{label} must be a list of non-empty strings")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise AgentEvalCaseError(f"{label} must not contain duplicates")
    return result
