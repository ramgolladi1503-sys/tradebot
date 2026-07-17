import asyncio

from agentic_research.mcp_server import create_mcp_server


def test_mcp_surface_exposes_only_read_only_research_tools(tmp_path):
    names = {tool.name for tool in asyncio.run(create_mcp_server(tmp_path).list_tools())}
    assert names == {
        "get_strategy_contract",
        "validate_dataset",
        "audit_existing_research_report",
        "run_temporal_semantics_tests",
        "run_structural_backtest",
        "run_wfa",
        "run_adversarial_review",
        "create_certification_bundle",
        "propose_next_hypotheses",
    }
    assert not any("order" in name or "broker" in name or "risk" in name or "modify" in name for name in names)
