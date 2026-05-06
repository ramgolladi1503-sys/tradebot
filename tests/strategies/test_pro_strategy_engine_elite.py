from __future__ import annotations

from unittest.mock import Mock

import strategies.pro_layer.pro_strategy_engine as pro_engine_mod
from strategies.pro_layer.pro_strategy_engine import ProStrategyEngine, StrategyBase


class _BrokenStrategy(StrategyBase):
    family = "broken_family"
    regimes = {"TREND", "NEUTRAL"}

    def generate(self, market_data):
        raise RuntimeError("boom")


def test_strategy_exceptions_are_logged_and_reported(monkeypatch):
    engine = ProStrategyEngine()
    monkeypatch.setattr(engine, "strategies", [_BrokenStrategy()])
    exception_spy = Mock()
    monkeypatch.setattr(pro_engine_mod.logger, "exception", exception_spy)

    errors: list[str] = []
    signals = engine.run({"regime": "TREND"}, error_sink=errors)

    assert signals == []
    assert len(errors) == 1
    assert errors[0].startswith("strategy_failed:broken_family:RuntimeError:boom")
    assert exception_spy.call_count == 1


def test_time_window_never_emits_without_primary_confirmation():
    engine = ProStrategyEngine()
    market_data = {
        "regime": "TREND",
        "hour": 9,
        "minute": 35,
        "ltp_change_window": 0.9,
        "ltp": 100.0,
        "vwap": 100.0,
        "atr": 0.0,
        "vol_z": 0.0,
        "quote_age_sec": 1.0,
        "spread_pct": 0.008,
    }
    assert engine.run(market_data) == []


def test_precision_rules_fail_closed_on_stale_or_weak_context():
    engine = ProStrategyEngine()
    market_data = {
        "regime": "TREND",
        "atr": 2.0,
        "ltp_change_window": 1.6,
        "vol_z": 2.2,
        "bid_qty": 900,
        "ask_qty": 100,
        "quote_age_sec": 12.0,
        "spread_pct": 0.038,
    }
    assert engine.run(market_data) == []


def test_aggregator_keeps_only_top_non_tied_signal():
    engine = ProStrategyEngine()
    market_data = {
        "regime": "TREND",
        "atr": 2.4,
        "ltp_change_window": 1.8,
        "vol_z": 2.5,
        "bid_qty": 1400,
        "ask_qty": 100,
        "call_oi_delta": 120,
        "put_oi_delta": 10,
        "iv_change": 0.09,
        "quote_age_sec": 1.0,
        "spread_pct": 0.007,
        "ltp": 102.0,
        "vwap": 100.0,
        "rsi": 0.08,
    }
    signals = engine.run(market_data)
    assert len(signals) <= 1
