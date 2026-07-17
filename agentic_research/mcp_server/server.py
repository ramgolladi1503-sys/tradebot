from __future__ import annotations

from pathlib import Path

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
    def run_temporal_semantics_tests(research_id: str) -> dict:
        return tools.run_temporal_semantics_tests(research_id).model_dump(mode="json")

    @mcp.tool()
    def run_structural_backtest(research_id: str, dataset_path: str) -> dict:
        return tools.run_structural_backtest(research_id, dataset_path).model_dump(mode="json")

    @mcp.tool()
    def run_wfa(research_id: str, dataset_path: str) -> dict:
        return tools.run_wfa(research_id, dataset_path).model_dump(mode="json")

    return mcp
