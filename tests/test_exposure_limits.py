from types import SimpleNamespace

from core.risk_engine import RiskEngine


def _base_portfolio():
    return {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "daily_profit": 0.0,
        "daily_loss": 0.0,
        "daily_pnl_pct": 0.0,
        "trades_today": 0,
        "open_risk_pct": 0.001,
        "symbol_profit": {},
    }


def _trade():
    return SimpleNamespace(
        symbol="NIFTY",
        underlying="NIFTY",
        instrument="OPT",
        instrument_type="OPT",
        expiry="2026-02-27",
        strike=25200,
        option_type="CE",
        right="CE",
        entry_price=100.0,
        qty=1,
        qty_units=50,
        capital_at_risk=5000.0,
    )


def test_underlying_exposure_limit_blocks_trade(monkeypatch):
    monkeypatch.setattr("config.config.MAX_UNDERLYING_EXPOSURE_PCT", 0.40, raising=False)
    monkeypatch.setattr("config.config.MAX_POSITIONS_PER_UNDERLYING", 10, raising=False)
    monkeypatch.setattr("config.config.MAX_EXPIRY_CONCENTRATION_PCT", 0.99, raising=False)

    portfolio = _base_portfolio()
    exposure_state = {
        "exposure_by_underlying": {"NIFTY": 39000.0},
        "exposure_by_expiry": {"2026-02-27": 20000.0},
        "open_positions_count_by_underlying": {"NIFTY": 1},
        "total_open_exposure": 50000.0,
    }

    ok, reason = RiskEngine().allow_trade(portfolio, trade=_trade(), exposure_state=exposure_state)
    assert ok is False
    assert reason == "PORTFOLIO_LIMIT:UNDERLYING_EXPOSURE"


def test_positions_per_underlying_limit_blocks_trade(monkeypatch):
    monkeypatch.setattr("config.config.MAX_UNDERLYING_EXPOSURE_PCT", 0.99, raising=False)
    monkeypatch.setattr("config.config.MAX_POSITIONS_PER_UNDERLYING", 2, raising=False)
    monkeypatch.setattr("config.config.MAX_EXPIRY_CONCENTRATION_PCT", 0.99, raising=False)

    portfolio = _base_portfolio()
    exposure_state = {
        "exposure_by_underlying": {"NIFTY": 10000.0},
        "exposure_by_expiry": {"2026-02-27": 5000.0},
        "open_positions_count_by_underlying": {"NIFTY": 2},
        "total_open_exposure": 10000.0,
    }

    ok, reason = RiskEngine().allow_trade(portfolio, trade=_trade(), exposure_state=exposure_state)
    assert ok is False
    assert reason == "PORTFOLIO_LIMIT:POSITIONS_PER_UNDERLYING"


def test_net_delta_limit_blocks_trade(monkeypatch):
    monkeypatch.setattr("config.config.MAX_UNDERLYING_EXPOSURE_PCT", 0.99, raising=False)
    monkeypatch.setattr("config.config.MAX_POSITIONS_PER_UNDERLYING", 10, raising=False)
    monkeypatch.setattr("config.config.MAX_EXPIRY_CONCENTRATION_PCT", 0.99, raising=False)
    monkeypatch.setattr("config.config.MAX_NET_DELTA", 40.0, raising=False)
    monkeypatch.setattr("config.config.MAX_NET_VEGA", 500.0, raising=False)
    monkeypatch.setattr("config.config.EVENT_NET_DELTA_MULT", 0.5, raising=False)
    monkeypatch.setattr("config.config.EVENT_NET_VEGA_MULT", 0.5, raising=False)

    portfolio = _base_portfolio()
    exposure_state = {
        "exposure_by_underlying": {"NIFTY": 10000.0},
        "exposure_by_expiry": {"2026-02-27": 6000.0},
        "open_positions_count_by_underlying": {"NIFTY": 1},
        "total_open_exposure": 10000.0,
        "net_delta": 35.0,
        "net_vega": 10.0,
    }
    trade = _trade()
    trade.delta = 10.0

    ok, reason = RiskEngine().allow_trade(portfolio, regime="TREND", trade=trade, exposure_state=exposure_state)
    assert ok is False
    assert reason == "PORTFOLIO_LIMIT:NET_DELTA"


def test_event_regime_uses_tighter_delta_limit(monkeypatch):
    monkeypatch.setattr("config.config.MAX_UNDERLYING_EXPOSURE_PCT", 0.99, raising=False)
    monkeypatch.setattr("config.config.MAX_POSITIONS_PER_UNDERLYING", 10, raising=False)
    monkeypatch.setattr("config.config.MAX_EXPIRY_CONCENTRATION_PCT", 0.99, raising=False)
    monkeypatch.setattr("config.config.MAX_NET_DELTA", 40.0, raising=False)
    monkeypatch.setattr("config.config.MAX_NET_VEGA", 500.0, raising=False)
    monkeypatch.setattr("config.config.EVENT_NET_DELTA_MULT", 0.6, raising=False)
    monkeypatch.setattr("config.config.EVENT_NET_VEGA_MULT", 0.6, raising=False)

    portfolio = _base_portfolio()
    exposure_state = {
        "exposure_by_underlying": {"NIFTY": 5000.0},
        "exposure_by_expiry": {"2026-02-27": 4000.0},
        "open_positions_count_by_underlying": {"NIFTY": 1},
        "total_open_exposure": 5000.0,
        "net_delta": 20.0,
        "net_vega": 10.0,
    }
    trade = _trade()
    trade.delta = 10.0

    ok_trend, reason_trend = RiskEngine().allow_trade(portfolio, regime="TREND", trade=trade, exposure_state=exposure_state)
    assert ok_trend is True
    assert reason_trend == "OK"

    ok_event, reason_event = RiskEngine().allow_trade(portfolio, regime="EVENT", trade=trade, exposure_state=exposure_state)
    assert ok_event is False
    assert reason_event == "PORTFOLIO_LIMIT:NET_DELTA"
