from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_research.contracts import ToolResult
from agentic_research.tools import TradeBotReadOnlyTools


def create_mcp_server(repo_root: Path):
    from mcp.server.fastmcp import FastMCP

    tools = TradeBotReadOnlyTools(repo_root)
    mcp = FastMCP("tradebot-read-only-research")

    @mcp.tool()
    def get_strategy_contract(research_id: str, strategy_id: str = "trend_pullback_v1") -> dict:
        return tools.get_strategy_contract(research_id, strategy_id).model_dump(mode="json")

    @mcp.tool()
    def validate_dataset(research_id: str, dataset_path: str) -> dict:
        return tools.validate_dataset(research_id, dataset_path).model_dump(mode="json")

    @mcp.tool()
    def audit_existing_research_report(research_id: str, report_path: str, strategy_id: str = "trend_pullback_v1") -> dict:
        return tools.audit_existing_research_report(research_id, report_path, strategy_id).model_dump(mode="json")

    @mcp.tool()
    def run_temporal_semantics_tests(research_id: str) -> dict:
        return tools.run_temporal_semantics_tests(research_id).model_dump(mode="json")

    @mcp.tool()
    def run_structural_backtest(research_id: str, dataset_path: str) -> dict:
        return tools.run_structural_backtest(research_id, dataset_path).model_dump(mode="json")

    @mcp.tool()
    def run_wfa(research_id: str, dataset_path: str) -> dict:
        return tools.run_wfa(research_id, dataset_path).model_dump(mode="json")

    @mcp.tool()
    def run_adversarial_review(research_id: str, results: dict[str, dict[str, Any]]) -> dict:
        parsed = {name: ToolResult.model_validate(value) for name, value in results.items()}
        return tools.run_adversarial_review(research_id, parsed).model_dump(mode="json")

    @mcp.tool()
    def create_certification_bundle(research_id: str, results: dict[str, dict[str, Any]]) -> dict:
        parsed = {name: ToolResult.model_validate(value) for name, value in results.items()}
        return tools.create_certification_bundle(research_id, parsed).model_dump(mode="json")

    @mcp.tool()
    def propose_next_hypotheses(research_id: str, strategy_id: str, results: dict[str, dict[str, Any]]) -> dict:
        parsed = {name: ToolResult.model_validate(value) for name, value in results.items()}
        return tools.propose_next_hypotheses(research_id, strategy_id, parsed).model_dump(mode="json")

    return mcp
