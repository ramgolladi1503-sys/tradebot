from __future__ import annotations

from strategies.trade_builder import TradeBuilder


def test_trade_builder_backfills_reject_reason_when_missing():
    tb = TradeBuilder()
    tb._reject_ctx = {}

    reason = tb._ensure_reject_reason({"symbol": "NIFTY"})

    assert reason == "unspecified_trade_builder_reject"
    assert tb._reject_ctx.get("reason") == "unspecified_trade_builder_reject"
    assert tb._reject_ctx.get("symbol") == "NIFTY"
