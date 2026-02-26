from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _features):
        return 0.9


def _builder() -> TradeBuilder:
    return TradeBuilder(predictor=_PredictorStub())


def test_trade_intent_flags_paper_planning_allows_stale(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)

    builder = _builder()
    flags = builder.trade_intent_flags(
        {
            "symbol": "NIFTY",
            "market_open": True,
            "chain_source": "synthetic_offhours",
            "quote_ok": True,
            "ltp": 25000.0,
            "ltp_source": "cached",
            "market_context": {"execution_mode": "PAPER", "market_open": True},
        },
        opt={
            "quote_ok": True,
            "quote_age_sec": None,
            "quote_source": "synthetic_offhours",
        },
    )

    assert flags["planning_only"] is True
    assert flags["execution_allowed"] is False
    assert flags["tradable"] is True
    assert flags["tradable_reasons_blocking"] == []


def test_trade_intent_flags_live_open_remains_strict(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)

    builder = _builder()
    flags = builder.trade_intent_flags(
        {
            "symbol": "NIFTY",
            "market_open": True,
            "chain_source": "synthetic_offhours",
            "quote_ok": False,
            "ltp": 0.0,
            "ltp_source": "cached",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
        },
        opt={"quote_ok": False, "quote_age_sec": None},
    )

    assert flags["planning_only"] is False
    assert flags["execution_allowed"] is False
    assert "chain_not_live" in flags["tradable_reasons_blocking"]
    assert "quote_not_ok" in flags["tradable_reasons_blocking"]
