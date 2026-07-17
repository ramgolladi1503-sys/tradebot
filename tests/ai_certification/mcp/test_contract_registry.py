from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from core.ai_certification.mcp import (
    JSON_SCHEMA_DRAFT,
    MCP_CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    MCPContractError,
    SemanticVersion,
    TOOL_CONTRACTS,
    ToolAnnotations,
    assert_backward_compatible,
    contract_manifest,
    contracts_digest,
    get_tool_contract,
    is_backward_compatible,
    tool_names,
)


EXPECTED_TOOL_NAMES = (
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
)


def test_registry_has_unique_deterministic_tool_order():
    assert tool_names() == EXPECTED_TOOL_NAMES
    assert len(tool_names()) == len(set(tool_names()))
    assert tool_names() == tuple(sorted(tool_names()))


def test_every_tool_declares_versioned_object_schemas_and_closed_execution():
    for contract in TOOL_CONTRACTS:
        assert contract.contract_version == MCP_CONTRACT_VERSION
        assert contract.input_schema["$schema"] == JSON_SCHEMA_DRAFT
        assert contract.output_schema["$schema"] == JSON_SCHEMA_DRAFT
        assert contract.input_schema["type"] == "object"
        assert contract.output_schema["type"] == "object"
        assert "additionalProperties" in contract.input_schema
        assert "additionalProperties" in contract.output_schema
        assert contract.execution.task_support == "forbidden"
        assert contract.execution.timeout_seconds > 0
        assert contract.execution.maximum_request_bytes > 0
        assert contract.execution.maximum_response_bytes > 0


def test_only_final_certification_tool_can_write_and_it_is_safe_idempotent():
    writers = [contract for contract in TOOL_CONTRACTS if not contract.annotations.read_only]
    assert [contract.name for contract in writers] == ["certify_backtest_bundle"]
    writer = writers[0]
    assert writer.annotations.destructive is False
    assert writer.annotations.idempotent is True
    assert writer.annotations.open_world is False
    assert writer.required_scopes == ("certification:report:write",)

    for contract in TOOL_CONTRACTS:
        if contract is writer:
            continue
        assert contract.annotations.read_only is True
        assert contract.annotations.destructive is False
        assert contract.annotations.idempotent is True
        assert contract.annotations.open_world is False


def test_registry_exposes_no_live_trade_or_runtime_mutation_tools():
    forbidden_names = {
        "place_order",
        "submit_order",
        "change_risk",
        "override_risk",
        "mutate_strategy",
        "run_shell",
        "write_database",
        "git_push",
    }
    assert forbidden_names.isdisjoint(tool_names())
    assert all(
        scope
        in {
            "certification:evaluate",
            "certification:inspect",
            "certification:report:write",
            "certification:retrieve",
        }
        for contract in TOOL_CONTRACTS
        for scope in contract.required_scopes
    )


def test_contract_manifest_is_stable_and_self_identifying():
    first = contract_manifest()
    second = contract_manifest()

    assert first == second
    assert first["manifest_schema_version"] == "1.0"
    assert first["contract_version"] == MCP_CONTRACT_VERSION
    assert first["mcp_protocol_version"] == MCP_PROTOCOL_VERSION
    assert first["contract_digest"] == contracts_digest(TOOL_CONTRACTS)
    assert len(first["contract_digest"]) == 64
    assert [tool["name"] for tool in first["tools"]] == list(EXPECTED_TOOL_NAMES)


def test_contract_lookup_fails_closed_for_unknown_tool():
    with pytest.raises(KeyError, match="unknown MCP tool contract"):
        get_tool_contract("unknown_tool")


def test_semantic_version_requires_three_numeric_components():
    assert str(SemanticVersion.parse("1.2.3")) == "1.2.3"
    with pytest.raises(MCPContractError):
        SemanticVersion.parse("1.2")
    with pytest.raises(MCPContractError):
        SemanticVersion.parse("v1.2.3")


def test_additive_optional_input_is_backward_compatible():
    previous = get_tool_contract("retrieve_certification_policy_context")
    schema = copy.deepcopy(previous.input_schema)
    schema["properties"]["strategy_id"] = {"type": "string"}
    current = replace(previous, contract_version="1.1.0", input_schema=schema)

    assert is_backward_compatible(previous, current) is True
    assert_backward_compatible(previous, current)


def test_new_required_input_is_breaking_without_major_version():
    previous = get_tool_contract("retrieve_certification_policy_context")
    schema = copy.deepcopy(previous.input_schema)
    schema["properties"]["strategy_id"] = {"type": "string"}
    schema["required"].append("strategy_id")
    current = replace(previous, contract_version="1.1.0", input_schema=schema)

    assert is_backward_compatible(previous, current) is False
    with pytest.raises(MCPContractError, match="new required input"):
        assert_backward_compatible(previous, current)


def test_removed_or_changed_output_is_breaking_without_major_version():
    previous = get_tool_contract("inspect_certification_bundle")
    schema = copy.deepcopy(previous.output_schema)
    del schema["properties"]["bundle_digest"]
    schema["required"].remove("bundle_digest")
    current = replace(previous, contract_version="1.1.0", output_schema=schema)

    with pytest.raises(MCPContractError, match="output property changed or removed"):
        assert_backward_compatible(previous, current)


def test_safety_annotations_cannot_weaken_in_minor_version():
    previous = get_tool_contract("inspect_certification_bundle")
    unsafe = ToolAnnotations(
        title=previous.annotations.title,
        read_only=False,
        destructive=False,
        idempotent=True,
        open_world=False,
    )
    current = replace(previous, contract_version="1.1.0", annotations=unsafe)

    with pytest.raises(MCPContractError, match="read-only guarantee"):
        assert_backward_compatible(previous, current)


def test_scope_change_requires_major_version():
    previous = get_tool_contract("inspect_certification_bundle")
    current = replace(
        previous,
        contract_version="1.1.0",
        required_scopes=("certification:evaluate",),
    )

    with pytest.raises(MCPContractError, match="required scopes changed"):
        assert_backward_compatible(previous, current)


def test_payload_or_timeout_expansion_requires_major_version():
    previous = get_tool_contract("inspect_certification_bundle")
    expanded = replace(
        previous.execution,
        timeout_seconds=previous.execution.timeout_seconds + 1,
    )
    current = replace(previous, contract_version="1.1.0", execution=expanded)

    with pytest.raises(MCPContractError, match="timeout expanded"):
        assert_backward_compatible(previous, current)
