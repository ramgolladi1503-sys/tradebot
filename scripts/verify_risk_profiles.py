import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.risk_state import RiskState


def _print_state(label, rs):
    print(
        f"{label}: mode={rs.mode} daily_pnl_pct={rs.daily_pnl_pct:.4f} "
        f"dd={rs.daily_max_drawdown:.4f} entropy={rs.current_regime_entropy:.3f} "
        f"shock={rs.current_shock_score:.3f} mult={rs.risk_budget_multiplier():.2f}"
    )


def main():
    # Guard: pilot limits must remain conservative.
    assert cfg.RISK_PROFILE in ("PILOT", "NORMAL", "AGGRESSIVE")
    if cfg.RISK_PROFILE == "PILOT":
        assert cfg.MAX_DAILY_LOSS_PCT <= 0.02, "PILOT must not exceed 2% daily loss"

    rs = RiskState(start_capital=100000)
    portfolio = {
        "capital": 100000,
        "equity_high": 100000,
        "daily_profit": 0.0,
        "daily_loss": 0.0,
        "open_risk_pct": 0.0,
        "loss_streak": 0,
    }

    # Soft-halt near limit
    portfolio["daily_loss"] = -0.7 * cfg.MAX_DAILY_LOSS_PCT * portfolio["equity_high"]
    rs.update_portfolio(portfolio)
    _print_state("soft_halt_near_limit", rs)
    assert rs.mode == "SOFT_HALT", "Expected SOFT_HALT near daily loss limit"

    # Hard-halt breach
    portfolio["daily_loss"] = -1.05 * cfg.MAX_DAILY_LOSS_PCT * portfolio["equity_high"]
    rs.update_portfolio(portfolio)
    _print_state("hard_halt_breach", rs)
    assert rs.mode == "HARD_HALT", "Expected HARD_HALT after daily loss breach"

    # Next session recovery mode (reset daily PnL on new day)
    rs._current_day = date.today().replace(day=date.today().day - 1)
    portfolio["daily_loss"] = 0.0
    portfolio["daily_profit"] = 0.0
    rs.update_portfolio(portfolio)
    _print_state("recovery_mode", rs)
    assert rs.mode == "RECOVERY_MODE", "Expected RECOVERY_MODE on new day after hard halt"

    # Event regime scaling
    rs.update_market("NIFTY", {"primary_regime": "EVENT", "regime_entropy": 1.0, "shock_score": 0.7})
    mult_event = rs.risk_budget_multiplier()
    _print_state("event_mult", rs)
    assert mult_event <= 0.6, "Expected reduced risk multiplier in EVENT regime"

    # High entropy scaling
    rs.update_market("NIFTY", {"primary_regime": "RANGE", "regime_entropy": 1.6, "shock_score": 0.1})
    mult_entropy = rs.risk_budget_multiplier()
    _print_state("entropy_mult", rs)
    assert mult_entropy <= 0.7, "Expected reduced risk multiplier for high entropy"

    # Loss streak scaling
    rs.mode = "NORMAL"
    rs.loss_streak = max(3, cfg.LOSS_STREAK_DOWNSIZE)
    mult_loss = rs.risk_budget_multiplier()
    _print_state("loss_streak_mult", rs)
    assert mult_loss <= 0.6, "Expected reduced risk multiplier for loss streak"

    print("verify_risk_profiles: PASS")


if __name__ == "__main__":
    main()
