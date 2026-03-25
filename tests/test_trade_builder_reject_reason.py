from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


def test_trade_builder_backfills_reject_reason_when_missing():
    tb = TradeBuilder()
    tb._reject_ctx = {}

    reason = tb._ensure_reject_reason({"symbol": "NIFTY"})

    assert reason == "unspecified_trade_builder_reject"
    assert tb._reject_ctx.get("reason") == "unspecified_trade_builder_reject"
    assert tb._reject_ctx.get("symbol") == "NIFTY"


def test_trade_builder_build_sets_reject_reason_for_quick_live(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    tb = TradeBuilder()

    trade = tb.build({"symbol": "NIFTY"}, quick_mode=True)

    assert trade is None
    assert tb._reject_ctx.get("reason") == "quick_mode_live_blocked"
    assert tb._reject_ctx.get("symbol") == "NIFTY"


def test_trade_builder_build_with_trace_uses_reject_reason(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    tb = TradeBuilder()

    trade, trace = tb.build_with_trace({"symbol": "NIFTY"}, quick_mode=True)

    assert trade is None
    assert "QUICK_MODE_LIVE_BLOCKED" in trace.reasons
    assert "UNSPECIFIED_TRADE_BUILDER_REJECT" not in trace.reasons
