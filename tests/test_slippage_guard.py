from __future__ import annotations

from dataclasses import dataclass

from config import config as cfg
from core.slippage_guard import evaluate_slippage_budget


@dataclass
class _Trade:
    instrument: str = "OPT"
    opt_bid: float = 100.0
    opt_ask: float = 101.0
    qty: int = 2
    regime: str = "TREND"


class _Engine:
    def __init__(self, expected_abs: float):
        self._expected_abs = expected_abs

    def estimate_slippage(self, *_args, **_kwargs):
        return float(self._expected_abs)


def test_slippage_guard_blocks_wide_spread_live(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.005, raising=False)
    trade = _Trade(opt_bid=100.0, opt_ask=102.0, qty=1, regime="TREND")
    md = {"market_context": {"execution_mode": "LIVE", "market_open": True}, "volume": 5000, "vol_z": 0.5}
    out = evaluate_slippage_budget(trade, md, _Engine(expected_abs=0.2))
    assert out.allowed is False
    assert out.reason_code == "WIDE_SPREAD"


def test_slippage_guard_blocks_budget_breach_live(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENFORCE_LIVE_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.05, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_BPS_BY_REGIME", {"DEFAULT": 5.0, "TREND": 5.0}, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_BPS_VOL_Z_MULT", 0.0, raising=False)
    trade = _Trade(opt_bid=100.0, opt_ask=100.4, qty=3, regime="TREND")
    md = {"market_context": {"execution_mode": "LIVE", "market_open": True}, "volume": 1200, "vol_z": 0.0}
    out = evaluate_slippage_budget(trade, md, _Engine(expected_abs=0.25))
    assert out.allowed is False
    assert out.reason_code == "SLIPPAGE_BUDGET_BREACH"
    assert (out.expected_slippage_bps or 0.0) > (out.budget_bps or 0.0)


def test_slippage_guard_skips_non_live(monkeypatch):
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "EXEC_SLIPPAGE_BUDGET_ENFORCE_LIVE_ONLY", True, raising=False)
    trade = _Trade(opt_bid=100.0, opt_ask=100.3, qty=1, regime="RANGE")
    md = {"market_context": {"execution_mode": "PAPER", "market_open": True}, "volume": 1000, "vol_z": 1.0}
    out = evaluate_slippage_budget(trade, md, _Engine(expected_abs=5.0))
    assert out.allowed is True
    assert out.reason_code == "SLIPPAGE_BUDGET_SKIPPED_NON_LIVE"

