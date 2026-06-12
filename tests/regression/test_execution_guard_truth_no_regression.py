from __future__ import annotations

import time
from types import SimpleNamespace

from config import config as cfg
import core.execution_guard as execution_guard_mod
from core.execution.execution_guard import evaluate_execution_guard
from core.execution_guard import ExecutionGuard, must_have_valid_approval


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


def test_execution_guard_regression_future_quote_timestamp_stays_blocked():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot={"ts": now + 30.0, "bid": 100.0, "ask": 101.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )
    assert decision.execution_allowed is False
    assert decision.reasons == ["future_quote_timestamp"]


def test_execution_guard_regression_risk_halt_still_blocks_clean_trade():
    class _RiskState:
        def approve(self, trade):
            del trade
            return False, "halt_active"

    guard = ExecutionGuard(risk_state=_RiskState())
    decision = guard.evaluate(
        _trade(),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": True}},
    )

    assert decision.allowed is False
    assert decision.reason_code == "RISKSTATE:_HALT_ACTIVE"


def test_execution_guard_regression_manual_approval_missing_never_becomes_approved(monkeypatch):
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER,LIVE", raising=False)
    monkeypatch.setattr(
        execution_guard_mod,
        "consume_valid_approval",
        lambda **kwargs: (False, "approval_missing"),
    )

    ok, reason = must_have_valid_approval("intent-hash", mode="PAPER")

    assert ok is False
    assert reason == "manual_approval_required:approval_missing"
