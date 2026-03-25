from __future__ import annotations

from core.market_context import derive_market_context


def test_planning_only_offhours_only():
    sim_ctx = derive_market_context({"execution_mode": "SIM", "market_open": True})
    paper_ctx = derive_market_context({"execution_mode": "PAPER", "market_open": True})
    live_ctx = derive_market_context({"execution_mode": "LIVE", "market_open": True})
    off_ctx = derive_market_context({"execution_mode": "LIVE", "market_open": False})

    assert sim_ctx.planning_only is False
    assert paper_ctx.planning_only is False
    assert live_ctx.planning_only is False
    assert off_ctx.planning_only is True
