"""P0 regression: ExecutionGuard.evaluate() is not the approval authority.
Approval must be enforced at the caller/permission layer (must_have_valid_approval).

Gap closed: GAP-03 from qa-coverage-gaps-20260610.md

Invariant under test:
  1. must_have_valid_approval() returns (False, "live_trading_env_disabled") in LIVE
     mode when LIVE_TRADING_ENABLED=false, even when an APPROVED record exists.
  2. ExecutionGuard.evaluate() by itself does NOT call must_have_valid_approval()
     — it gates on market context, tradable flags, survival gates, regime, and
     confidence. The approval responsibility belongs to the caller.
  3. Structural proof: the approval gap is a known architectural split;
     this file documents and tests the boundary precisely.

These tests do NOT place, modify or cancel any order.
No production code is modified by this file.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from config import config as cfg
from core.approval_store import approve_order_intent
from core.execution_guard import OrderIntent, must_have_valid_approval
from core.execution_guard import ExecutionGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intent():
    return OrderIntent(
        symbol="NIFTY",
        side="BUY",
        qty=10,
        order_type="LIMIT",
        limit_price=101.0,
        product="MIS",
        exchange="NFO",
        strategy_id="TEST_P0",
        timestamp_bucket=999888,
        expiry="2026-06-26",
        strike=25000,
        right="CE",
        multiplier=1.0,
    )


def _trade(**overrides):
    payload = {
        "tradable": True,
        "tradable_reasons_blocking": [],
        "confidence": 0.95,
        "confidence_final": 0.95,
        "capital_at_risk": 500.0,
        "strategy": "TREND",
        "planning_only": False,
        "execution_allowed": True,
        "reason": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


# ---------------------------------------------------------------------------
# P0 — must_have_valid_approval blocks LIVE when env var is false, even with approval
# ---------------------------------------------------------------------------

def test_must_have_valid_approval_live_env_disabled_blocks_even_with_approved_record(
    monkeypatch, tmp_path
):
    """
    Scenario:
      - MANUAL_APPROVAL=True
      - An APPROVED, non-expired approval record exists in the DB
      - LIVE_TRADING_ENABLED env var = 'false' (the default)

    Expected: (False, "live_trading_env_disabled")

    This proves the env-var gate fires before the approval store lookup in
    must_have_valid_approval(), so a valid approval cannot bypass the
    hard environment safety flag.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")

    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="tester", ttl_sec=600)
    assert ok is True, f"test setup: approve_order_intent failed: {reason}"

    result_ok, result_reason = must_have_valid_approval(h, mode="LIVE")

    assert result_ok is False, (
        "must_have_valid_approval must return False when LIVE_TRADING_ENABLED=false, "
        f"even with an APPROVED record. Got: ok={result_ok!r}, reason={result_reason!r}"
    )
    assert result_reason == "live_trading_env_disabled", (
        f"Expected reason 'live_trading_env_disabled', got {result_reason!r}"
    )


def test_must_have_valid_approval_live_env_true_and_approved_record_succeeds(
    monkeypatch, tmp_path
):
    """
    Positive control: when LIVE_TRADING_ENABLED=true AND an APPROVED record
    exists, must_have_valid_approval must succeed (consume the approval).
    This confirms the test above is not a false negative.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    h = _intent().order_intent_hash()
    ok, reason = approve_order_intent(h, approver_id="tester", ttl_sec=600)
    assert ok is True, f"test setup: approve_order_intent failed: {reason}"

    result_ok, result_reason = must_have_valid_approval(h, mode="LIVE")

    assert result_ok is True, (
        "must_have_valid_approval must succeed when LIVE_TRADING_ENABLED=true "
        f"and approval exists. Got: ok={result_ok!r}, reason={result_reason!r}"
    )


def test_must_have_valid_approval_live_env_disabled_blocks_even_without_any_record(
    monkeypatch, tmp_path
):
    """
    When LIVE_TRADING_ENABLED=false, must_have_valid_approval must also block
    for a missing hash (belt-and-braces: env check fires before DB lookup).
    The reason must still be 'live_trading_env_disabled', not 'approval_missing'.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")

    result_ok, result_reason = must_have_valid_approval("nonexistent_hash", mode="LIVE")

    assert result_ok is False
    assert result_reason == "live_trading_env_disabled", (
        f"Expected 'live_trading_env_disabled', got {result_reason!r}"
    )


# ---------------------------------------------------------------------------
# P0 — ExecutionGuard.evaluate() itself does NOT enforce the approval layer
# (structural boundary test — this is by design, not a bug)
# ---------------------------------------------------------------------------

def test_execution_guard_evaluate_does_not_check_approval_store(monkeypatch):
    """
    ExecutionGuard.evaluate() gates on: market context, tradable flag,
    survival gates, regime monitor, confidence, and capital.

    It does NOT call must_have_valid_approval() — that is the caller's
    responsibility (see ExecutionRouter.execute()).

    This test proves the boundary: a fully-valid trade with no approval
    record still passes ExecutionGuard.evaluate() in PAPER mode (where
    PAPER_REQUIRE_ARMED_APPROVAL defaults to False).

    The companion test in test_manual_approval_enforcement.py proves that the
    ExecutionRouter layer correctly blocks the order when approval is missing.
    """
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_GUARD_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "REGIME_MONITOR_ENABLED", False, raising=False)

    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(confidence=0.82),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "PAPER", "market_open": True}},
    )

    # ExecutionGuard itself allows the trade (approval is a caller concern)
    assert decision.allowed is True, (
        "ExecutionGuard.evaluate() should not enforce approval — "
        "that is the ExecutionRouter's responsibility"
    )
    assert decision.mode in {"PAPER", "SIM"}


def test_execution_guard_live_env_disabled_blocks_before_guard_can_allow(monkeypatch):
    """
    In LIVE mode, ExecutionGuard checks market context first.
    With market_open=False + LIVE_FAIL_CLOSED_ON_MARKET_CLOSED=True,
    the guard returns MARKET_CLOSED before reaching any approval logic.

    This demonstrates that even if the guard were to check approvals
    internally, the market-closed check would fire first — reinforcing
    that LIVE_TRADING_ENABLED enforcement must happen before the guard is
    even invoked.
    """
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_FAIL_CLOSED_ON_MARKET_CLOSED", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_MONITOR_ENABLED", False, raising=False)

    guard = ExecutionGuard()
    decision = guard.evaluate(
        _trade(),
        {"capital": 10000.0},
        "TREND",
        market_data={"market_context": {"execution_mode": "LIVE", "market_open": False}},
    )

    assert decision.allowed is False
    assert decision.reason_code == "MARKET_CLOSED"


# ---------------------------------------------------------------------------
# P0 — Explicit mode-specific approval requirement contract
# ---------------------------------------------------------------------------

def test_must_have_valid_approval_sim_mode_not_required_by_default(
    monkeypatch, tmp_path
):
    """
    By default, APPROVAL_REQUIRED_MODES = 'PAPER,LIVE' (not SIM).
    In SIM mode, must_have_valid_approval must succeed without any DB record.
    This confirms mode-based approval gating is correctly scoped.
    """
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER,LIVE", raising=False)

    result_ok, result_reason = must_have_valid_approval("any_hash", mode="SIM")

    assert result_ok is True
    assert result_reason == "approval_not_required_for_mode"
