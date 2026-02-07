from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.risk_engine import RiskEngine
from core.risk_utils import to_pct


def _check_case(label, portfolio, expected_ok):
    engine = RiskEngine()
    ok, reason = engine.allow_trade(portfolio)
    print(f"{label}: ok={ok} reason={reason} daily_pnl_pct={portfolio.get('daily_pnl_pct'):.4f}")
    assert ok == expected_ok, f"{label} failed: expected {expected_ok}, got {ok} ({reason})"


if __name__ == "__main__":
    equity_high = 100000.0
    engine = RiskEngine()
    max_loss_pct = getattr(engine, "max_daily_loss_pct", getattr(cfg, "MAX_DAILY_LOSS_PCT", getattr(cfg, "MAX_DAILY_LOSS", 0.15)))

    # Case A: loss breaches MAX_DAILY_LOSS_PCT
    daily_pnl = -(max_loss_pct + 0.01) * equity_high  # breach by 1%
    portfolio_a = {
        # keep equity_high == capital to isolate daily loss threshold from drawdown lock
        "capital": equity_high,
        "equity_high": equity_high,
        "daily_profit": 0.0,
        "daily_loss": daily_pnl,
        "daily_pnl_pct": to_pct(daily_pnl, equity_high),
        "trades_today": 0,
    }
    _check_case("breach_daily_loss", portfolio_a, expected_ok=False)

    # Case B: loss within MAX_DAILY_LOSS_PCT
    daily_pnl_b = -(max_loss_pct * 0.5) * equity_high  # half of limit
    portfolio_b = {
        "capital": equity_high,
        "equity_high": equity_high,
        "daily_profit": 0.0,
        "daily_loss": daily_pnl_b,
        "daily_pnl_pct": to_pct(daily_pnl_b, equity_high),
        "trades_today": 0,
    }
    _check_case("within_daily_loss", portfolio_b, expected_ok=True)

    print(f"MAX_DAILY_LOSS_PCT={max_loss_pct}")
    print("Risk unit verification complete.")
