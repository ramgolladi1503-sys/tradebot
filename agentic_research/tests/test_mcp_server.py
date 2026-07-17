import asyncio

from agentic_research.mcp_server import create_mcp_server


def test_mcp_surface_exposes_exactly_six_read_only_research_tools(tmp_path):
    server = create_mcp_server(tmp_path)
    definitions = asyncio.run(server.list_tools())
    names = {tool.name for tool in definitions}
    assert names == {
        "get_strategy_contract",
        "validate_dataset",
        "run_temporal_semantics_tests",
        "run_structural_backtest",
        "run_wfa",
        "create_certification_bundle",
    }
    assert not any("order" in name or "broker" in name or "risk" in name for name in names)
