from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import config as cfg


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


@dataclass
class CapitalControlState:
    initial_capital: float
    current_equity: float
    peak_equity: float
    drawdown_pct: float
    consecutive_losses: int
    trading_halted: bool
    size_multiplier: float
    last_reason: str


class PaperCapitalController:
    def __init__(self) -> None:
        self.initial_capital = float(getattr(cfg, "CAPITAL", 100000) or 100000)
        self.current_equity = float(self.initial_capital)
        self.peak_equity = float(self.initial_capital)
        self.consecutive_losses = 0
        self.max_daily_loss_pct = float(getattr(cfg, "MAX_DAILY_LOSS_PCT", 0.02) or 0.02)
        self.max_drawdown_pct = abs(float(getattr(cfg, "MAX_DRAWDOWN_PCT", -0.06) or -0.06))
        self.loss_streak_downsize = int(getattr(cfg, "LOSS_STREAK_DOWNSIZE", 3) or 3)
        self.max_consecutive_losses = max(self.loss_streak_downsize + 1, 4)
        self.last_reason = "OK"

    def state(self) -> CapitalControlState:
        drawdown_pct = self._drawdown_pct()
        halted, reason = self._halt_state(drawdown_pct)
        return CapitalControlState(
            initial_capital=round(self.initial_capital, 4),
            current_equity=round(self.current_equity, 4),
            peak_equity=round(self.peak_equity, 4),
            drawdown_pct=round(drawdown_pct, 6),
            consecutive_losses=int(self.consecutive_losses),
            trading_halted=bool(halted),
            size_multiplier=round(self.size_multiplier(), 4),
            last_reason=str(reason),
        )

    def can_open_trade(self) -> tuple[bool, str]:
        drawdown_pct = self._drawdown_pct()
        halted, reason = self._halt_state(drawdown_pct)
        self.last_reason = str(reason)
        return (not halted), str(reason)

    def size_multiplier(self) -> float:
        drawdown_pct = self._drawdown_pct()
        multiplier = 1.0
        if self.consecutive_losses >= self.loss_streak_downsize:
            multiplier *= 0.5
        elif self.consecutive_losses == max(0, self.loss_streak_downsize - 1):
            multiplier *= 0.75

        if drawdown_pct >= (self.max_drawdown_pct * 0.75):
            multiplier *= 0.5
        elif drawdown_pct >= (self.max_drawdown_pct * 0.50):
            multiplier *= 0.75

        return max(0.25, min(1.0, multiplier))

    def apply_quantity_multiplier(self, qty: int) -> int:
        scaled = int(max(1, round(int(max(1, qty)) * self.size_multiplier())))
        return scaled

    def record_closed_trade(self, realized_pnl: float) -> CapitalControlState:
        pnl = _safe_float(realized_pnl, 0.0)
        self.current_equity += pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)
        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0
        state = self.state()
        self.last_reason = state.last_reason
        return state

    def _drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.current_equity) / self.peak_equity)

    def _halt_state(self, drawdown_pct: float) -> tuple[bool, str]:
        realized_loss_pct = max(0.0, (self.initial_capital - self.current_equity) / max(self.initial_capital, 1e-6))
        if realized_loss_pct >= self.max_daily_loss_pct:
            return True, "daily_loss_limit"
        if drawdown_pct >= self.max_drawdown_pct:
            return True, "max_drawdown_limit"
        if self.consecutive_losses >= self.max_consecutive_losses:
            return True, "consecutive_losses_limit"
        return False, "OK"
