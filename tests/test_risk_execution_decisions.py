from __future__ import annotations

from types import SimpleNamespace

from config import config as cfg
from core.execution_guard import ExecutionGuard
from core.risk_engine import RiskEngine


def _trade(**overrides):
    payload = {
        "tradable": True,
        "tradable_reasons_blocking": [],
        "confidence": 0.95,
        "capital_at_risk": 500.0,
        "strategy": "TREND",
        "planning_only": False,
        "execution_allowed": True,
        "reason": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_risk_engine_evaluate_trade_exposes_reason_code_and_keeps_tuple_api():
    engine = RiskEngine()
    portfolio = {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "trades_today": 0,
        "open_risk_pct": 0.001,
    }
    decision = engine.evaluate_trade(portfolio)
    assert decision.allowed is False
    assert decision.reason_code == "RISK_DATA_UNAVAILABLE:daily_pnl_pct"
    ok, reason = engine.allow_trade(portfolio)
    assert ok is False
    assert reason == "RISK_DATA_UNAVAILABLE:daily_pnl_pct"


def test_execution_guard_live_closed_fails_closed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_FAIL_CLOSED_ON_MARKET_CLOSED", True, raising=False)
    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": False}},
    )
    assert decision.allowed is False
    assert decision.reason_code == "MARKET_CLOSED"
    ok, reason = guard.validate(
        _trade(),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": False}},
    )
    assert ok is False
    assert reason == "Market closed"


def test_execution_guard_paper_planning_is_allowed_with_explicit_reason(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_GUARD_ALLOW_PLANNING", True, raising=False)
    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(planning_only=True, execution_allowed=False),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "PAPER", "market_open": False}},
    )
    assert decision.allowed is True
    assert decision.planning_only is True
    assert decision.reason_code == "PLANNING_ONLY_MODE"
