from __future__ import annotations

import time

from core.execution.entry_pricer import resolve_execution_entry


def test_execution_entry_pricer_buy_uses_fresh_ask():
    now = time.time()
    out = resolve_execution_entry(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot={"ts": now, "bid": 100.0, "ask": 101.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
    )
    assert out.executable is True
    assert out.execution_entry == 101.0
    assert out.source == "ask"
    assert out.reason == "ok"


def test_execution_entry_pricer_sell_uses_fresh_bid():
    now = time.time()
    out = resolve_execution_entry(
        side="SELL",
        bid=100.0,
        ask=101.0,
        snapshot={"ts": now, "bid": 100.0, "ask": 101.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
    )
    assert out.executable is True
    assert out.execution_entry == 100.0
    assert out.source == "bid"
    assert out.reason == "ok"


def test_execution_entry_pricer_denies_stale_quote():
    now = time.time()
    out = resolve_execution_entry(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot={"ts": now - 5.0, "bid": 100.0, "ask": 101.0},
        evaluated_at_epoch=now,
        max_quote_age_sec=1.0,
    )
    assert out.executable is False
    assert out.execution_entry is None
    assert out.reason == "stale_quote"
