from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "module_name",
    [
        "tools.tradebot_mcp.evidence_server",
        "tools.tradebot_mcp.data_audit_server",
        "tools.tradebot_mcp.gates_server",
        "tools.tradebot_mcp.git_audit_server",
    ],
)
def test_mcp_server_imports(module_name: str) -> None:
    pytest.importorskip("mcp")
    module = importlib.import_module(module_name)
    assert module.mcp is not None
