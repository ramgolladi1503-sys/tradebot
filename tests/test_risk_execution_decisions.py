from __future__ import annotations

from types import SimpleNamespace

from config import config as cfg
import core.execution_guard as execution_guard_mod
from core.execution_guard import ExecutionGuard
from core.risk_engine import RiskEngine
from core.survival_gates import SurvivalGateDecision


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


def test_execution_guard_blocks_p0_on_regime_monitor_severe(monkeypatch):
    monkeypatch.setattr(cfg, "REGIME_MONITOR_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_MONITOR_P0_ON_SEVERE", True, raising=False)
    monkeypatch.setattr(
        execution_guard_mod,
        "get_regime_monitor_status",
        lambda prefer_disk=False: {"severe": True, "collapsed": True, "sample_count": 30},
    )
    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(strategy="TREND_VWAP_FALLBACK"),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )
    assert decision.allowed is False
    assert decision.reason_code == "REGIME_MONITOR_SEVERE_COLLAPSE"


def test_execution_guard_applies_regime_size_multiplier_context(monkeypatch):
    monkeypatch.setattr(cfg, "REGIME_MONITOR_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_MONITOR_P0_ON_SEVERE", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_MONITOR_BLOCK_ON_COLLAPSE", False, raising=False)
    monkeypatch.setattr(cfg, "REGIME_MONITOR_SIZE_MULT_ON_COLLAPSE", 0.4, raising=False)
    monkeypatch.setattr(
        execution_guard_mod,
        "get_regime_monitor_status",
        lambda prefer_disk=False: {"severe": False, "collapsed": True, "sample_count": 40},
    )
    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(strategy="TREND_VWAP_FALLBACK"),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )
    assert decision.allowed is True
    assert float((decision.context or {}).get("size_multiplier", 1.0)) == 0.4


def test_execution_guard_blocks_on_survival_gate_breach():
    class _StubSurvivalGates:
        def evaluate(self, **kwargs):
            del kwargs
            return SurvivalGateDecision(
                allowed_entries=False,
                breach=True,
                reason_codes=["MAX_CONSECUTIVE_LOSSES_BREACH"],
                size_multiplier=1.0,
                auto_flatten_requested=True,
                incident_id="inc-survival-1",
                context={"reason_codes": ["MAX_CONSECUTIVE_LOSSES_BREACH"], "auto_flatten_on_breach": True},
            )

    guard = ExecutionGuard(survival_gates=_StubSurvivalGates())
    decision = guard.evaluate(
        _trade(strategy="TREND_VWAP_FALLBACK"),
        {"capital": 10000.0, "loss_streak": 5, "daily_max_drawdown": -0.04},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )
    assert decision.allowed is False
    assert decision.reason_code == "SURVIVAL_GATE_BREACH"
    assert "MAX_CONSECUTIVE_LOSSES_BREACH" in list((decision.context or {}).get("reason_codes") or [])
    assert decision.context["confidence_stage"] == "final"


def test_execution_guard_allows_when_final_confidence_meets_threshold(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_GUARD_FINAL_CONFIDENCE_MIN", 0.40, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)

    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(confidence=0.55),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )

    assert decision.allowed is True
    assert decision.context["trade_confidence"] == 0.55
    assert decision.context["min_confidence"] == 0.40
    assert decision.context["confidence_stage"] == "final"


def test_execution_guard_blocks_when_final_confidence_below_threshold(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_GUARD_FINAL_CONFIDENCE_MIN", 0.40, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)

    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(confidence=0.34),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )

    assert decision.allowed is False
    assert decision.reason_code == "LOW_CONFIDENCE"
    assert decision.context["trade_confidence"] == 0.34
    assert decision.context["min_confidence"] == 0.40
    assert decision.context["confidence_stage"] == "final"


def test_execution_guard_high_confidence_can_still_fail_non_confidence_reason(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_GUARD_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)

    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(confidence=0.92, capital_at_risk=25000.0),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )

    assert decision.allowed is False
    assert decision.reason_code == "INSUFFICIENT_CAPITAL"
    assert decision.context["trade_confidence"] == 0.92
    assert decision.context["min_confidence"] == 0.30
    assert decision.context["confidence_stage"] == "final"


def test_risk_engine_extracts_builder_confidence_not_mutated_confidence():
    engine = RiskEngine()
    proba, confluence, proba_source, confluence_source = engine._extract_confidence_inputs(
        {
            "confidence": 0.41,
            "builder_confidence": 0.62,
            "confidence_raw": 0.58,
            "trade_score_detail": {"confluence_score": 0.73},
        }
    )

    assert proba == 0.62
    assert confluence == 0.73
    assert proba_source == "builder_confidence"
    assert confluence_source == "trade_score_detail.confluence_score"


def test_risk_engine_falls_back_to_confidence_raw_when_builder_confidence_missing():
    engine = RiskEngine()
    proba, confluence, proba_source, confluence_source = engine._extract_confidence_inputs(
        {
            "confidence": 0.41,
            "confidence_raw": 0.58,
            "sizing_confluence_score": 0.81,
        }
    )

    assert proba == 0.58
    assert confluence == 0.81
    assert proba_source == "confidence_raw"
    assert confluence_source == "sizing_confluence_score"
