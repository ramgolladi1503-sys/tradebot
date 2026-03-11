from __future__ import annotations

import time

from core.execution.execution_guard import evaluate_execution_guard


def test_execution_guard_allows_fresh_best_ask():
    now = time.time()
    out = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot={"ts": now, "bid": 100.0, "ask": 101.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
        reference_price=101.0,
    )
    assert out.execution_allowed is True
    assert out.execution_entry == 101.0
    assert out.reasons == []


def test_execution_guard_denies_wide_spread_but_keeps_execution_entry():
    now = time.time()
    out = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=110.0,
        snapshot={"ts": now, "bid": 100.0, "ask": 110.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.02,
        reference_price=110.0,
    )
    assert out.execution_allowed is False
    assert out.execution_entry == 110.0
    assert "spread_too_wide" in out.reasons


def test_execution_guard_denies_stale_quote_with_reason():
    now = time.time()
    out = evaluate_execution_guard(
        side="SELL",
        bid=100.0,
        ask=101.0,
        snapshot={"ts": now - 10.0, "bid": 100.0, "ask": 101.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=1.0,
        max_spread_pct=0.05,
        reference_price=100.0,
    )
    assert out.execution_allowed is False
    assert out.execution_entry is None
    assert "stale_quote" in out.reasons
