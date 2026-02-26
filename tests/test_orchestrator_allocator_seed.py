from __future__ import annotations

from datetime import datetime

from config import config as cfg
from core.orchestrator import Orchestrator


def _orch_stub() -> Orchestrator:
    return Orchestrator.__new__(Orchestrator)


def test_allocator_context_seed_uses_nested_market_context_over_global(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    orch = _orch_stub()
    market_data = {
        "timestamp": datetime(2026, 2, 10, 9, 30, 0).timestamp(),
        "market_context": {"execution_mode": "PAPER", "market_open": True},
    }
    seed = orch._allocator_context_seed(market_data, "NIFTY", "S1")
    assert seed == "2026-02-10|NIFTY|S1"


def test_allocator_context_seed_live_open_returns_none(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    orch = _orch_stub()
    market_data = {
        "timestamp": datetime(2026, 2, 10, 9, 30, 0).timestamp(),
        "market_context": {"execution_mode": "LIVE", "market_open": True},
    }
    assert orch._allocator_context_seed(market_data, "NIFTY", "S1") is None


def test_allocator_seed_date_falls_back_to_now_when_timestamp_missing(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    import core.orchestrator as orchestrator_mod

    monkeypatch.setattr(
        orchestrator_mod,
        "now_ist",
        lambda: datetime(2026, 2, 11, 7, 0, 0),
    )
    orch = _orch_stub()
    market_data = {"market_context": {"execution_mode": "PAPER", "market_open": False}}
    seed = orch._allocator_context_seed(market_data, "BANKNIFTY", "S2")
    assert seed == "2026-02-11|BANKNIFTY|S2"
