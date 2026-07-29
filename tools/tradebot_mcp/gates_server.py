from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools.tradebot_mcp.core import GateService, Settings

mcp = FastMCP(
    "tradebot-gates",
    instructions=(
        "Fail-closed evaluation of hash-backed TradeBot research evidence. These tools "
        "never run arbitrary shell commands and never trust narrative completion claims."
    ),
    json_response=True,
)
service = GateService(Settings.from_env())


@mcp.tool()
def run_bootstrap_gate(evidence_path: str) -> dict:
    """Evaluate the bootstrap gate from a machine evidence manifest."""
    return service.evaluate("bootstrap", evidence_path)


@mcp.tool()
def run_wave1_gate(evidence_path: str) -> dict:
    """Evaluate source, pipeline, statistics, microstructure and lock authority."""
    return service.evaluate("wave1", evidence_path)


@mcp.tool()
def run_temporal_gate(evidence_path: str) -> dict:
    """Evaluate completed-candle, next-bar, session and future-mutation evidence."""
    return service.evaluate("temporal", evidence_path)


@mcp.tool()
def run_candidate_freeze_gate(evidence_path: str) -> dict:
    """Evaluate whether a candidate is immutable and holdout-safe."""
    return service.evaluate("candidate_freeze", evidence_path)


@mcp.tool()
def run_wfa_gate(evidence_path: str) -> dict:
    """Evaluate chronological WFA, costs, controls, concentration and latency."""
    return service.evaluate("wfa", evidence_path)


@mcp.tool()
def run_determinism_gate(evidence_path: str) -> dict:
    """Evaluate two-run semantic equality evidence."""
    return service.evaluate("determinism", evidence_path)


@mcp.tool()
def run_oracle_gate(evidence_path: str) -> dict:
    """Evaluate independent-oracle and perturbation evidence."""
    return service.evaluate("oracle", evidence_path)


@mcp.tool()
def run_publication_gate(evidence_path: str) -> dict:
    """Evaluate all publication prerequisites without altering production code."""
    return service.evaluate("publication", evidence_path)


@mcp.tool()
def run_all_gates(evidence_path: str) -> dict:
    """Evaluate every registered gate; all must pass for the aggregate PASS."""
    return service.evaluate_all(evidence_path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
