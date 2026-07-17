from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .bundle import BundleError, CertificationBundle
from .certifier import certify_bundle
from .policy import default_policy
from .report import write_report


def _configured_root(env_name: str, default: str) -> Path:
    return Path(os.getenv(env_name, default)).expanduser().resolve()


def resolve_allowed_bundle(bundle_id: str, evidence_root: str | Path) -> Path:
    if not bundle_id or Path(bundle_id).is_absolute() or any(part in ("..", "") for part in Path(bundle_id).parts):
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
    return {
        "run_id": bundle.manifest.get("run_id"),
        "strategy_id": bundle.manifest.get("strategy_id"),
        "repository_commit": bundle.manifest.get("repository_commit"),
        "policy_version": bundle.manifest.get("policy_version"),
        "artifacts": sorted(bundle.artifacts),
        "bundle_digest": bundle.digest(),
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
            "Read-only certification tools for frozen TradeBot backtest evidence. "
            "The server has no broker, order, risk override, shell, or code mutation tools."
        ),
        json_response=True,
    )

    @mcp.tool()
    def inspect_certification_bundle(bundle_id: str) -> dict[str, Any]:
        """Inspect one frozen evidence bundle under the configured allowlisted root."""
        return inspect_bundle(bundle_id, evidence_root=evidence_root)

    @mcp.tool()
    def certify_backtest_bundle(bundle_id: str) -> dict[str, Any]:
        """Run deterministic certification gates and write only the resulting report."""
        return certify_bundle_tool(
            bundle_id,
            evidence_root=evidence_root,
            report_root=report_root,
            repository_root=repository_root,
        )

    @mcp.tool()
    def get_backtest_certification_policy() -> dict[str, Any]:
        """Return the active deterministic certification policy."""
        return default_policy().to_dict()

    @mcp.resource("tradebot://certification/policies/backtest-v1")
    def policy_resource() -> str:
        return json.dumps(default_policy().to_dict(), sort_keys=True)

    return mcp


def main() -> None:
    build_server().run(transport=os.getenv("TRADEBOT_AI_CERT_MCP_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
