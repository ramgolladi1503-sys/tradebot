from types import SimpleNamespace

from config import config as cfg
from core.regime import RegimeClassifier
from core.risk_engine import RiskEngine
from strategies.trade_builder import TradeBuilder


def test_regime_classifier_returns_expected_regimes():
    classifier = RegimeClassifier()
    trend = classifier.classify(
        {
            "atr_pct": 0.0025,
            "vwap_slope": 0.003,
            "gap_pct": 0.0005,
            "event_flag": False,
        }
    )
    assert trend == "TREND"

    range_regime = classifier.classify(
        {
            "atr_pct": 0.0012,
            "vwap_slope": 0.0002,
            "gap_pct": 0.0001,
            "event_flag": False,
        }
    )
    assert range_regime == "RANGE"

    event = classifier.classify(
        {
            "atr_pct": 0.0020,
            "vwap_slope": 0.0001,
            "gap_pct": 0.0001,
            "event_flag": True,
        }
    )
    assert event == "EVENT"


def test_strategy_router_selects_by_regime(monkeypatch):
    monkeypatch.setattr(cfg, "REGIME_ROUTER_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "REGIME_CLASSIFIER_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "REGIME_EVENT_ROUTE_ALLOW", True, raising=False)
    monkeypatch.setattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True, raising=False)
    builder = TradeBuilder()

    monkeypatch.setattr("strategies.trade_builder.ensemble_signal", lambda _md: SimpleNamespace(direction="BUY_CALL", reason="trend_route", score=0.8))
    monkeypatch.setattr("strategies.trade_builder.mean_reversion_signal", lambda *_args, **_kwargs: SimpleNamespace(direction="BUY_PUT", reason="range_route", score=0.7))
    monkeypatch.setattr("strategies.trade_builder.event_breakout_signal", lambda *_args, **_kwargs: SimpleNamespace(direction="BUY_CALL", reason="event_route", score=0.75))

    md_base = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "ltp": 25000.0,
        "vwap": 25000.0,
        "rsi_mom": 0.0,
        "atr": 10.0,
        "ltp_change_window": 0.0,
    }

    trend_sig = builder._signal_for_symbol({**md_base, "regime": "TREND"})
    assert trend_sig is not None
    assert trend_sig["reason"] == "trend_route"
    assert trend_sig["regime_day"] == "TREND"

    range_sig = builder._signal_for_symbol({**md_base, "regime": "RANGE"})
    assert range_sig is not None
    assert range_sig["reason"] == "range_route"
    assert range_sig["regime_day"] == "RANGE"

    event_sig = builder._signal_for_symbol({**md_base, "regime": "EVENT"})
    assert event_sig is not None
    assert event_sig["reason"] == "event_route"
    assert event_sig["regime_day"] == "EVENT"


def test_risk_engine_event_regime_is_stricter(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_DAILY_LOSS_PCT", 0.02, raising=False)
    monkeypatch.setattr(cfg, "MAX_OPEN_RISK_PCT", 0.02, raising=False)
    monkeypatch.setattr(cfg, "MAX_TRADES_PER_DAY", 5, raising=False)
    monkeypatch.setattr(cfg, "REGIME_EVENT_DAILY_LOSS_MULT", 0.5, raising=False)
    monkeypatch.setattr(cfg, "REGIME_EVENT_OPEN_RISK_MULT", 0.6, raising=False)
    monkeypatch.setattr(cfg, "REGIME_EVENT_MAX_TRADES_MULT", 0.6, raising=False)
    engine = RiskEngine()
    portfolio = {
        "capital": 100000,
        "equity_high": 100000,
        "daily_pnl_pct": -0.011,
        "daily_profit": 0.0,
        "daily_loss": -1100.0,
        "trades_today": 0,
        "open_risk_pct": 0.001,
        "symbol_profit": {},
    }
    ok_event, reason_event = engine.allow_trade(portfolio, regime="EVENT")
    assert ok_event is False
    assert reason_event == "Daily loss limit hit"

    ok_trend, reason_trend = engine.allow_trade(portfolio, regime="TREND")
    assert ok_trend is True
    assert reason_trend == "OK"
