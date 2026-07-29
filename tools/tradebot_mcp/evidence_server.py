from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools.tradebot_mcp.core import EvidenceService, Settings

mcp = FastMCP(
    "tradebot-evidence",
    instructions=(
        "Read-only access to TradeBot research contracts, evidence registries, "
        "candidate fingerprints, handoffs and artifact hashes. Narrative status "
        "must never override machine evidence."
    ),
    json_response=True,
)
service = EvidenceService(Settings.from_env())


@mcp.tool()
def list_research_contexts() -> dict:
    """List available research context directories without reading secrets."""
    return service.list_research_contexts()


@mcp.tool()
def get_research_status(context_dir: str | None = None) -> dict:
    """Read the machine cycle-status record for one explicit research context."""
    return service.get_research_status(context_dir)


@mcp.tool()
def get_contract(context_dir: str | None = None) -> dict:
    """Read the immutable research contract and its SHA-256."""
    return service.get_contract(context_dir)


@mcp.tool()
def get_safety_boundaries(context_dir: str | None = None) -> dict:
    """Read the research safety boundaries and their SHA-256."""
    return service.get_safety_boundaries(context_dir)


@mcp.tool()
def list_source_manifests() -> dict:
    """List candidate manifest, registry, authority and inventory artifacts."""
    return service.list_source_manifests()


@mcp.tool()
def inspect_source_manifest(path: str) -> dict:
    """Read a JSON source manifest from an approved root."""
    return service.inspect_source_manifest(path)


@mcp.tool()
def verify_artifact_hash(path: str, expected_sha256: str) -> dict:
    """Stream-hash one approved artifact and compare it with the expected digest."""
    return service.verify_artifact_hash(path, expected_sha256)


@mcp.tool()
def get_consumed_evidence_registry(context_dir: str | None = None) -> dict:
    """Read the consumed-development, validation, holdout and confirmation registry."""
    return service.get_consumed_evidence_registry(context_dir)


@mcp.tool()
def get_holdout_status(context_dir: str | None = None) -> dict:
    """Return cycle and consumed-evidence records relevant to holdout access."""
    return service.get_holdout_status(context_dir)


@mcp.tool()
def get_candidate_fingerprint(context_dir: str | None = None) -> dict:
    """Read the frozen-candidate registry; this tool cannot create or alter candidates."""
    return service.get_candidate_fingerprint(context_dir)


@mcp.tool()
def list_agent_attempts(context_dir: str | None = None) -> dict:
    """Read all registered subagent attempts without trusting their conclusions."""
    return service.list_agent_attempts(context_dir)


@mcp.tool()
def list_agent_handoffs(context_dir: str | None = None) -> dict:
    """List handoff artifacts and hashes for primary-agent verification."""
    return service.list_agent_handoffs(context_dir)


@mcp.tool()
def get_agent_handoff(path: str) -> dict:
    """Read one approved text or JSON handoff and its hash."""
    return service.get_agent_handoff(path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
