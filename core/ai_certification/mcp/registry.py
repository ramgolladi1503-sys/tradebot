from __future__ import annotations

from typing import Any

from .contracts import (
    MCP_CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    ToolAnnotations,
    ToolContract,
    ToolExecutionPolicy,
    contracts_digest,
)
from .schemas import (
    bundle_input_schema,
    certification_output_schema,
    empty_input_schema,
    gate_output_schema,
    inspect_output_schema,
    policy_output_schema,
    retrieval_input_schema,
    retrieval_output_schema,
)


_READ_ONLY = ToolAnnotations(
    title="Read-only certification operation",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=False,
)
_REPORT_WRITE = ToolAnnotations(
    title="Persist deterministic certification report",
    read_only=False,
    destructive=False,
    idempotent=True,
    open_world=False,
)
_DEFAULT_EXECUTION = ToolExecutionPolicy(
    task_support="forbidden",
    timeout_seconds=30,
    maximum_request_bytes=16_384,
    maximum_response_bytes=2_000_000,
)
_RETRIEVAL_EXECUTION = ToolExecutionPolicy(
    task_support="forbidden",
    timeout_seconds=20,
    maximum_request_bytes=32_768,
    maximum_response_bytes=1_000_000,
)
_CERTIFICATION_EXECUTION = ToolExecutionPolicy(
    task_support="forbidden",
    timeout_seconds=120,
    maximum_request_bytes=16_384,
    maximum_response_bytes=4_000_000,
)


def _read_contract(
    name: str,
    title: str,
    description: str,
    *,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    scopes: tuple[str, ...],
    execution: ToolExecutionPolicy = _DEFAULT_EXECUTION,
) -> ToolContract:
    return ToolContract(
        name=name,
        title=title,
        description=description,
        contract_version=MCP_CONTRACT_VERSION,
        input_schema=input_schema,
        output_schema=output_schema,
        annotations=ToolAnnotations(
            title=title,
            read_only=_READ_ONLY.read_only,
            destructive=_READ_ONLY.destructive,
            idempotent=_READ_ONLY.idempotent,
            open_world=_READ_ONLY.open_world,
        ),
        execution=execution,
        required_scopes=scopes,
    )


def _gate_contract(name: str, title: str, description: str) -> ToolContract:
    return _read_contract(
        name,
        title,
        description,
        input_schema=bundle_input_schema(),
        output_schema=gate_output_schema(),
        scopes=("certification:evaluate",),
    )


TOOL_CONTRACTS: tuple[ToolContract, ...] = tuple(
    sorted(
        (
            _read_contract(
                "get_backtest_certification_policy",
                "Get certification policy",
                "Return the active deterministic certification policy without changing it.",
                input_schema=empty_input_schema(),
                output_schema=policy_output_schema(),
                scopes=("certification:retrieve",),
            ),
            _read_contract(
                "inspect_certification_bundle",
                "Inspect certification bundle",
                "Inspect one allowlisted frozen bundle and discover available gates and tools.",
                input_schema=bundle_input_schema(),
                output_schema=inspect_output_schema(),
                scopes=("certification:inspect",),
            ),
            _read_contract(
                "retrieve_certification_policy_context",
                "Retrieve certification policy context",
                "Retrieve authority-ranked policy and audit context from the curated repository corpus.",
                input_schema=retrieval_input_schema(),
                output_schema=retrieval_output_schema(),
                scopes=("certification:retrieve",),
                execution=_RETRIEVAL_EXECUTION,
            ),
            _gate_contract(
                "validate_artifact_hashes",
                "Validate artifact hashes",
                "Verify every frozen artifact against its recorded SHA-256 identity.",
            ),
            _gate_contract(
                "validate_bundle_manifest",
                "Validate bundle manifest",
                "Validate bundle schema, policy version, inventory and safe artifact paths.",
            ),
            _gate_contract(
                "validate_data_provenance_gate",
                "Validate data provenance",
                "Validate dataset identity, chronology, quote completeness and contract metadata.",
            ),
            _gate_contract(
                "validate_execution_realism_gate",
                "Validate execution realism",
                "Validate executable quote sides, strict liquidity and cost monotonicity.",
            ),
            _gate_contract(
                "validate_financial_reconciliation_gate",
                "Validate financial reconciliation",
                "Reconcile gross P&L, costs, net P&L, trade counts and ambiguity.",
            ),
            _gate_contract(
                "validate_negative_controls_gate",
                "Validate negative controls",
                "Validate future mutation, timing shift and cost-sensitivity controls.",
            ),
            _gate_contract(
                "validate_source_authority_gate",
                "Validate source authority",
                "Validate strict option-replay engine, WFA owner and research-mode authority.",
            ),
            _gate_contract(
                "validate_source_provenance",
                "Validate source provenance",
                "Validate frozen raw WFA, partition, control, test and dataset source evidence.",
            ),
            _gate_contract(
                "validate_strategy_result_gate",
                "Validate strategy result",
                "Validate that the declared strategy conclusion agrees with policy metrics.",
            ),
            _gate_contract(
                "validate_temporal_causality_gate",
                "Validate temporal causality",
                "Validate signal chronology, legal entry timing and future-mutation stability.",
            ),
            _gate_contract(
                "validate_test_evidence_gate",
                "Validate test evidence",
                "Validate focused test results and repository-commit identity.",
            ),
            _gate_contract(
                "validate_walk_forward_integrity_gate",
                "Validate walk-forward integrity",
                "Validate chronological partitions, purge and embargo, holdout isolation and contamination.",
            ),
            ToolContract(
                name="certify_backtest_bundle",
                title="Certify backtest bundle",
                description=(
                    "Run every deterministic certification gate and persist only the reproducible "
                    "JSON and Markdown certification reports under the configured report root."
                ),
                contract_version=MCP_CONTRACT_VERSION,
                input_schema=bundle_input_schema(),
                output_schema=certification_output_schema(),
                annotations=ToolAnnotations(
                    title="Certify backtest bundle",
                    read_only=_REPORT_WRITE.read_only,
                    destructive=_REPORT_WRITE.destructive,
                    idempotent=_REPORT_WRITE.idempotent,
                    open_world=_REPORT_WRITE.open_world,
                ),
                execution=_CERTIFICATION_EXECUTION,
                required_scopes=("certification:report:write",),
            ),
        ),
        key=lambda contract: contract.name,
    )
)

_CONTRACTS_BY_NAME = {contract.name: contract for contract in TOOL_CONTRACTS}
if len(_CONTRACTS_BY_NAME) != len(TOOL_CONTRACTS):
    raise RuntimeError("duplicate MCP tool contracts")


GATE_TOOL_TO_GATE: dict[str, str] = {
    "validate_artifact_hashes": "artifact_hashes",
    "validate_bundle_manifest": "bundle_manifest",
    "validate_data_provenance_gate": "data_provenance",
    "validate_execution_realism_gate": "execution_realism",
    "validate_financial_reconciliation_gate": "financial_reconciliation",
    "validate_negative_controls_gate": "negative_controls",
    "validate_source_authority_gate": "source_authority",
    "validate_source_provenance": "source_artifact_provenance",
    "validate_strategy_result_gate": "strategy_result_consistency",
    "validate_temporal_causality_gate": "temporal_causality",
    "validate_test_evidence_gate": "test_evidence",
    "validate_walk_forward_integrity_gate": "walk_forward_integrity",
}


def get_tool_contract(name: str) -> ToolContract:
    try:
        return _CONTRACTS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"unknown MCP tool contract: {name}") from exc


def tool_names() -> tuple[str, ...]:
    return tuple(contract.name for contract in TOOL_CONTRACTS)


def contract_manifest() -> dict[str, Any]:
    return {
        "manifest_schema_version": "1.0",
        "contract_version": MCP_CONTRACT_VERSION,
        "mcp_protocol_version": MCP_PROTOCOL_VERSION,
        "contract_digest": contracts_digest(TOOL_CONTRACTS),
        "tools": [contract.to_dict() for contract in TOOL_CONTRACTS],
    }
