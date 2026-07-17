from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.ai_certification.mcp import (
    MCPContractValidationError,
    tool_names,
    validate_tool_input,
    validate_tool_output,
)


def test_bundle_input_accepts_safe_identifier():
    validate_tool_input(
        "inspect_certification_bundle",
        {"bundle_id": "orb/run-001"},
    )


def test_bundle_input_rejects_unknown_property():
    with pytest.raises(MCPContractValidationError, match="unexpected properties"):
        validate_tool_input(
            "inspect_certification_bundle",
            {"bundle_id": "orb-run-001", "unsafe_override": True},
        )


def test_retrieval_input_rejects_empty_query_and_limit_above_contract():
    with pytest.raises(MCPContractValidationError, match="shorter than minLength"):
        validate_tool_input(
            "retrieve_certification_policy_context",
            {"query": "", "limit": 4},
        )
    with pytest.raises(MCPContractValidationError, match="above maximum"):
        validate_tool_input(
            "retrieve_certification_policy_context",
            {"query": "timing", "limit": 9},
        )


def test_gate_output_accepts_complete_typed_result():
    validate_tool_output(
        "validate_temporal_causality_gate",
        {
            "gate": "temporal_causality",
            "status": "PASS",
            "reason_code": "TEMPORAL_CAUSALITY_VALID",
            "summary": "Temporal evidence passed.",
            "mandatory": True,
            "evidence_refs": [
                {
                    "artifact": "timing_evidence.json",
                    "pointer": "",
                    "sha256": "a" * 64,
                }
            ],
            "details": {},
        },
    )


def test_gate_output_rejects_unknown_status_and_missing_reason():
    with pytest.raises(MCPContractValidationError, match="value must be one of"):
        validate_tool_output(
            "validate_temporal_causality_gate",
            {
                "gate": "temporal_causality",
                "status": "SUCCESS",
                "reason_code": "TEMPORAL_CAUSALITY_VALID",
                "summary": "Temporal evidence passed.",
                "mandatory": True,
                "evidence_refs": [],
                "details": {},
            },
        )
    with pytest.raises(MCPContractValidationError, match="missing required properties"):
        validate_tool_output(
            "validate_temporal_causality_gate",
            {
                "gate": "temporal_causality",
                "status": "PASS",
                "summary": "Temporal evidence passed.",
                "mandatory": True,
                "evidence_refs": [],
                "details": {},
            },
        )


def test_response_payload_budget_is_enforced():
    with pytest.raises(MCPContractValidationError, match="response payload exceeds"):
        validate_tool_output(
            "get_backtest_certification_policy",
            {"oversized": "x" * 2_100_000},
        )


def test_server_decorators_and_registry_cannot_drift():
    root = Path(__file__).resolve().parents[3]
    source = (root / "core/ai_certification/mcp_server.py").read_text(encoding="utf-8")
    registered = tuple(sorted(re.findall(r'@registered_tool\("([^"]+)"\)', source)))

    assert registered == tool_names()
    assert "tradebot://certification/mcp/contracts/v1" in source


def test_server_has_no_unguarded_tool_decorators():
    root = Path(__file__).resolve().parents[3]
    source = (root / "core/ai_certification/mcp_server.py").read_text(encoding="utf-8")

    assert "@mcp.tool(" not in source
    assert source.count("@registered_tool(") == len(tool_names())
