from config import config as cfg
from core.risk_state import RiskState


def _configure_conservative(monkeypatch):
    monkeypatch.setattr(cfg, "RISK_PROFILE", "CONSERVATIVE", raising=False)
    monkeypatch.setattr(cfg, "MAX_DAILY_LOSS_PCT", 0.012, raising=False)
    monkeypatch.setattr(cfg, "MAX_DRAWDOWN_PCT", -0.03, raising=False)
    monkeypatch.setattr(cfg, "RISK_SOFT_HALT_FRACTION", 0.7, raising=False)
    monkeypatch.setattr(cfg, "CONSERVATIVE_PROFIT_CAPTURE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_TRIGGER_PCT", 0.005, raising=False)
    monkeypatch.setattr(cfg, "CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_DRAWDOWN_PCT", -0.01, raising=False)
    monkeypatch.setattr(cfg, "CONSERVATIVE_PROFIT_CAPTURE_RISK_MULT", 0.4, raising=False)
    monkeypatch.setattr(cfg, "CONSERVATIVE_PROFIT_CAPTURE_SOFT_HALT_FRACTION", 0.5, raising=False)


def test_conservative_profit_capture_locks_in_gains(monkeypatch):
    _configure_conservative(monkeypatch)
    rs = RiskState(start_capital=100000)

    rs.update_portfolio(
        {
            "capital": 100800.0,
            "daily_profit": 800.0,
            "daily_loss": 0.0,
            "open_risk_pct": 0.0,
            "loss_streak": 0,
        }
    )

    assert rs.conservative_profit_capture_active is True
    assert rs.effective_daily_loss_pct == 0.01
    assert rs.effective_drawdown_pct == 0.01
    assert round(rs.risk_budget_multiplier(), 3) == 0.4

    rs.update_unrealized(-1200.0)

    assert rs.mode == "HARD_HALT"
    assert rs.last_mode_reason == "hard_limit_breach"
    assert rs.to_dict()["conservative_profit_capture_active"] is True


def test_conservative_profit_capture_stays_off_below_trigger(monkeypatch):
    _configure_conservative(monkeypatch)
    rs = RiskState(start_capital=100000)

    rs.update_portfolio(
        {
            "capital": 100200.0,
            "daily_profit": 200.0,
            "daily_loss": 0.0,
            "open_risk_pct": 0.0,
            "loss_streak": 0,
        }
    )

    assert rs.conservative_profit_capture_active is False
    assert rs.effective_drawdown_pct == 0.03
    assert rs.effective_daily_loss_pct == 0.012
    assert round(rs.risk_budget_multiplier(), 3) == 1.0
