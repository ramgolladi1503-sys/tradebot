from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from .bundle import BundleError, CertificationBundle
from .certifier import certify_bundle
from .knowledge import CuratedKnowledgeBase
from .mcp import (
    MCP_CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    contract_manifest,
    get_tool_contract,
    tool_names,
)
from .policy import CertificationPolicy, default_policy
from .report import write_report
from .source_validator import validate_source_index
from .validators import (
    validate_data_provenance,
    validate_execution_realism,
    validate_financial_reconciliation,
    validate_hashes,
    validate_manifest,
    validate_negative_controls,
    validate_source_authority,
    validate_strategy_result,
    validate_temporal_causality,
    validate_test_evidence,
    validate_wfa_integrity,
)


GateValidator = Callable[[CertificationBundle, CertificationPolicy], Any]
_GATE_VALIDATORS: dict[str, GateValidator] = {
    "bundle_manifest": validate_manifest,
    "artifact_hashes": validate_hashes,
    "source_artifact_provenance": validate_source_index,
    "source_authority": validate_source_authority,
    "data_provenance": validate_data_provenance,
    "temporal_causality": validate_temporal_causality,
    "execution_realism": validate_execution_realism,
    "financial_reconciliation": validate_financial_reconciliation,
    "walk_forward_integrity": validate_wfa_integrity,
    "negative_controls": validate_negative_controls,
    "test_evidence": validate_test_evidence,
    "strategy_result_consistency": validate_strategy_result,
}


def _configured_root(env_name: str, default: str) -> Path:
    return Path(os.getenv(env_name, default)).expanduser().resolve()


def resolve_allowed_bundle(bundle_id: str, evidence_root: str | Path) -> Path:
    if (
        not bundle_id
        or Path(bundle_id).is_absolute()
        or any(part in ("..", "") for part in Path(bundle_id).parts)
    ):
        raise BundleError("bundle_id must be a safe relative identifier")
    root = Path(evidence_root).resolve()
    candidate = (root / bundle_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise BundleError("bundle_id escapes the configured evidence root") from exc
    return candidate


def inspect_bundle(bundle_id: str, *, evidence_root: str | Path) -> dict[str, Any]:
    bundle = CertificationBundle.load(resolve_allowed_bundle(bundle_id, evidence_root))
    manifest = contract_manifest()
    return {
        "run_id": bundle.manifest.get("run_id"),
        "strategy_id": bundle.manifest.get("strategy_id"),
        "repository_commit": bundle.manifest.get("repository_commit"),
        "policy_version": bundle.manifest.get("policy_version"),
        "artifacts": sorted(bundle.artifacts),
        "bundle_digest": bundle.digest(),
        "available_gates": sorted(_GATE_VALIDATORS),
        "available_tools": list(tool_names()),
        "mcp_contract_version": MCP_CONTRACT_VERSION,
        "mcp_protocol_version": MCP_PROTOCOL_VERSION,
        "mcp_contract_digest": manifest["contract_digest"],
    }


def evaluate_gate(
    bundle_id: str,
    gate: str,
    *,
    evidence_root: str | Path,
) -> dict[str, Any]:
    validator = _GATE_VALIDATORS.get(gate)
    if validator is None:
        raise BundleError(f"unknown certification gate: {gate}")
    bundle = CertificationBundle.load(resolve_allowed_bundle(bundle_id, evidence_root))
    return validator(bundle, default_policy()).to_dict()


def retrieve_policy_context(
    query: str,
    *,
    repository_root: str | Path,
    limit: int = 4,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("retrieval query cannot be empty")
    knowledge = CuratedKnowledgeBase.from_repository(repository_root)
    chunks = knowledge.retrieve(query, limit=max(1, min(int(limit), 8)))
    return {
        "query": query,
        "results": [
            {
                "citation": chunk.citation,
                "authority": chunk.authority,
                "heading": chunk.heading,
                "text": chunk.text,
            }
            for chunk in chunks
        ],
    }


def certify_bundle_tool(
    bundle_id: str,
    *,
    evidence_root: str | Path,
    report_root: str | Path,
    repository_root: str | Path,
) -> dict[str, Any]:
    bundle_path = resolve_allowed_bundle(bundle_id, evidence_root)
    report = certify_bundle(bundle_path, repository_root=repository_root)
    outputs = write_report(report, report_root)
    return {"report": report.to_dict(), "outputs": outputs}


def build_server():
    """Build the optional FastMCP adapter without making MCP a core dependency."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is optional. Install requirements-ai-certification.txt to run the server."
        ) from exc

    evidence_root = _configured_root(
        "TRADEBOT_AI_CERT_EVIDENCE_ROOT",
        ".runtime/ai_certification/bundles",
    )
    report_root = _configured_root(
        "TRADEBOT_AI_CERT_REPORT_ROOT",
        ".runtime/ai_certification/reports",
    )
    repository_root = _configured_root("TRADEBOT_REPOSITORY_ROOT", ".")
    mcp = FastMCP(
        "TradeBot AI QA Certification",
        instructions=(
            "Inspect frozen evidence, retrieve authoritative policy context, run targeted "
            "read-only gates, then request the final deterministic certification. The "
            "server has no broker, order, risk override, shell, or code mutation tools."
        ),
        json_response=True,
    )

    def registered_tool(name: str):
        contract = get_tool_contract(name)
        return mcp.tool(
            name=contract.name,
            annotations=contract.annotations.to_mcp_dict(),
        )

    @registered_tool("inspect_certification_bundle")
    def inspect_certification_bundle(bundle_id: str) -> dict[str, Any]:
        """Inspect a frozen bundle and discover the available validation gates."""
        return inspect_bundle(bundle_id, evidence_root=evidence_root)

    @registered_tool("validate_bundle_manifest")
    def validate_bundle_manifest(bundle_id: str) -> dict[str, Any]:
        """Validate schema, policy version, inventory, and safe artifact paths."""
        return evaluate_gate(bundle_id, "bundle_manifest", evidence_root=evidence_root)

    @registered_tool("validate_artifact_hashes")
    def validate_artifact_hashes(bundle_id: str) -> dict[str, Any]:
        """Verify that every frozen artifact still matches its SHA-256 identity."""
        return evaluate_gate(bundle_id, "artifact_hashes", evidence_root=evidence_root)

    @registered_tool("validate_source_provenance")
    def validate_source_provenance(bundle_id: str) -> dict[str, Any]:
        """Verify the raw WFA, partition, control, test, and dataset source index."""
        return evaluate_gate(
            bundle_id,
            "source_artifact_provenance",
            evidence_root=evidence_root,
        )

    @registered_tool("validate_source_authority_gate")
    def validate_source_authority_gate(bundle_id: str) -> dict[str, Any]:
        """Verify strict engine, WFA, and research-mode ownership."""
        return evaluate_gate(bundle_id, "source_authority", evidence_root=evidence_root)

    @registered_tool("validate_data_provenance_gate")
    def validate_data_provenance_gate(bundle_id: str) -> dict[str, Any]:
        """Validate dataset identity, chronology, quotes, and contract metadata."""
        return evaluate_gate(bundle_id, "data_provenance", evidence_root=evidence_root)

    @registered_tool("validate_temporal_causality_gate")
    def validate_temporal_causality_gate(bundle_id: str) -> dict[str, Any]:
        """Check signal chronology, legal entry timing, and future-mutation controls."""
        return evaluate_gate(bundle_id, "temporal_causality", evidence_root=evidence_root)

    @registered_tool("validate_execution_realism_gate")
    def validate_execution_realism_gate(bundle_id: str) -> dict[str, Any]:
        """Check executable quote sides, strict liquidity, and cost monotonicity."""
        return evaluate_gate(bundle_id, "execution_realism", evidence_root=evidence_root)

    @registered_tool("validate_financial_reconciliation_gate")
    def validate_financial_reconciliation_gate(bundle_id: str) -> dict[str, Any]:
        """Reconcile gross P&L, costs, net P&L, trade counts, and ambiguity."""
        return evaluate_gate(
            bundle_id,
            "financial_reconciliation",
            evidence_root=evidence_root,
        )

    @registered_tool("validate_walk_forward_integrity_gate")
    def validate_walk_forward_integrity_gate(bundle_id: str) -> dict[str, Any]:
        """Check partition chronology, buffers, holdout isolation, and contamination."""
        return evaluate_gate(
            bundle_id,
            "walk_forward_integrity",
            evidence_root=evidence_root,
        )

    @registered_tool("validate_negative_controls_gate")
    def validate_negative_controls_gate(bundle_id: str) -> dict[str, Any]:
        """Check future mutation, timing shift, and cost sensitivity controls."""
        return evaluate_gate(bundle_id, "negative_controls", evidence_root=evidence_root)

    @registered_tool("validate_test_evidence_gate")
    def validate_test_evidence_gate(bundle_id: str) -> dict[str, Any]:
        """Check focused test results and repository-commit identity."""
        return evaluate_gate(bundle_id, "test_evidence", evidence_root=evidence_root)

    @registered_tool("validate_strategy_result_gate")
    def validate_strategy_result_gate(bundle_id: str) -> dict[str, Any]:
        """Check that the declared strategy conclusion matches policy metrics."""
        return evaluate_gate(
            bundle_id,
            "strategy_result_consistency",
            evidence_root=evidence_root,
        )

    @registered_tool("retrieve_certification_policy_context")
    def retrieve_certification_policy_context(
        query: str,
        limit: int = 4,
    ) -> dict[str, Any]:
        """Retrieve authority-ranked policy and audit context with citations."""
        return retrieve_policy_context(
            query,
            repository_root=repository_root,
            limit=limit,
        )

    @registered_tool("certify_backtest_bundle")
    def certify_backtest_bundle(bundle_id: str) -> dict[str, Any]:
        """Run all deterministic gates and write only the final report."""
        return certify_bundle_tool(
            bundle_id,
            evidence_root=evidence_root,
            report_root=report_root,
            repository_root=repository_root,
        )

    @registered_tool("get_backtest_certification_policy")
    def get_backtest_certification_policy() -> dict[str, Any]:
        """Return the active deterministic certification policy."""
        return default_policy().to_dict()

    @mcp.resource("tradebot://certification/policies/backtest-v1")
    def policy_resource() -> str:
        return json.dumps(default_policy().to_dict(), sort_keys=True)

    @mcp.resource("tradebot://certification/mcp/contracts/v1")
    def contract_manifest_resource() -> str:
        return json.dumps(contract_manifest(), sort_keys=True, separators=(",", ":"))

    return mcp


def main() -> None:
    build_server().run(
        transport=os.getenv("TRADEBOT_AI_CERT_MCP_TRANSPORT", "stdio")
    )


if __name__ == "__main__":
    main()
