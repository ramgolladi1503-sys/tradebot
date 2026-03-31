from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any

import pandas as pd


@dataclass
class RetailSafetyConfig:
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    max_symbol_exposure_pct: float = 0.15
    max_portfolio_exposure_pct: float = 0.35
    max_quote_age_seconds: float = 3.0
    min_time_between_trades_seconds: float = 30.0
    block_on_duplicate_signal_window_seconds: float = 120.0
    max_consecutive_losses: int = 3
    paper_only_by_default: bool = True


@dataclass
class SafetyState:
    starting_capital: float
    capital: float
    equity_peak: float
    daily_start_capital: float
    current_day: object | None = None
    consecutive_losses: int = 0
    last_trade_ts_by_symbol: dict[str, pd.Timestamp] = field(default_factory=dict)
    last_signal_fp_by_symbol: dict[str, tuple[pd.Timestamp, str]] = field(default_factory=dict)


class RetailLiveSafetyGate:
    def __init__(self, cfg: RetailSafetyConfig, starting_capital: float = 100000.0):
        self.cfg = cfg
        self.state = SafetyState(
            starting_capital=float(starting_capital),
            capital=float(starting_capital),
            equity_peak=float(starting_capital),
            daily_start_capital=float(starting_capital),
        )

    def update_capital(self, capital: float, timestamp) -> None:
        ts = pd.Timestamp(timestamp)
        day = ts.date()
        if self.state.current_day != day:
            self.state.current_day = day
            self.state.daily_start_capital = float(capital)
        self.state.capital = float(capital)
        self.state.equity_peak = max(self.state.equity_peak, float(capital))

    def record_trade_result(self, symbol: str, timestamp, pl: float) -> None:
        ts = pd.Timestamp(timestamp)
        self.state.last_trade_ts_by_symbol[str(symbol)] = ts
        if pl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

    def can_submit(self, *, order: Dict[str, Any], market: Dict[str, Any], broker_ok: bool, mode: str = "PAPER") -> tuple[bool, str]:
        ts = pd.Timestamp(market.get("timestamp"))
        self.update_capital(self.state.capital, ts)

        if self.cfg.paper_only_by_default and str(mode).upper() != "PAPER":
            return False, "paper_only_default"
        if not broker_ok:
            return False, "broker_unhealthy"
        if self.daily_loss_pct() >= self.cfg.max_daily_loss_pct:
            return False, "daily_loss_limit"
        if self.drawdown_pct() >= self.cfg.max_drawdown_pct:
            return False, "drawdown_limit"
        if self.state.consecutive_losses >= self.cfg.max_consecutive_losses:
            return False, "consecutive_loss_limit"
        if self.quote_age_too_old(market):
            return False, "stale_quote"
        if self.trade_too_soon(str(order.get("symbol", "UNKNOWN")), ts):
            return False, "trade_cooldown"
        if self.duplicate_signal(order, ts):
            return False, "duplicate_signal"
        if self.symbol_exposure_too_large(order):
            return False, "symbol_exposure_limit"
        if self.portfolio_exposure_too_large(order):
            return False, "portfolio_exposure_limit"
        return True, "ok"

    def acknowledge_signal(self, order: Dict[str, Any], timestamp) -> None:
        ts = pd.Timestamp(timestamp)
        symbol = str(order.get("symbol", "UNKNOWN"))
        fp = self._fingerprint(order)
        self.state.last_signal_fp_by_symbol[symbol] = (ts, fp)

    def daily_loss_pct(self) -> float:
        base = max(self.state.daily_start_capital, 1e-6)
        return max(0.0, (self.state.daily_start_capital - self.state.capital) / base)

    def drawdown_pct(self) -> float:
        peak = max(self.state.equity_peak, 1e-6)
        return max(0.0, (peak - self.state.capital) / peak)

    def quote_age_too_old(self, market: Dict[str, Any]) -> bool:
        age = market.get("quote_age_sec")
        if age is None:
            return False
        try:
            return float(age) > float(self.cfg.max_quote_age_seconds)
        except Exception:
            return False

    def trade_too_soon(self, symbol: str, now_ts: pd.Timestamp) -> bool:
        prev = self.state.last_trade_ts_by_symbol.get(symbol)
        if prev is None:
            return False
        return (now_ts - prev).total_seconds() < float(self.cfg.min_time_between_trades_seconds)

    def duplicate_signal(self, order: Dict[str, Any], now_ts: pd.Timestamp) -> bool:
        symbol = str(order.get("symbol", "UNKNOWN"))
        prev = self.state.last_signal_fp_by_symbol.get(symbol)
        if prev is None:
            return False
        prev_ts, prev_fp = prev
        if (now_ts - prev_ts).total_seconds() > float(self.cfg.block_on_duplicate_signal_window_seconds):
            return False
        return prev_fp == self._fingerprint(order)

    def symbol_exposure_too_large(self, order: Dict[str, Any]) -> bool:
        notional = self._notional(order)
        return notional > (self.state.capital * float(self.cfg.max_symbol_exposure_pct))

    def portfolio_exposure_too_large(self, order: Dict[str, Any]) -> bool:
        notional = self._notional(order)
        return notional > (self.state.capital * float(self.cfg.max_portfolio_exposure_pct))

    def _fingerprint(self, order: Dict[str, Any]) -> str:
        return "|".join([
            str(order.get("symbol", "UNKNOWN")),
            str(order.get("side", "BUY")),
            str(round(float(order.get("entry", 0.0)), 4)),
            str(round(float(order.get("stop", 0.0)), 4)),
            str(round(float(order.get("target", 0.0)), 4)),
        ])

    def _notional(self, order: Dict[str, Any]) -> float:
        qty = max(0, int(order.get("qty", 0)))
        entry = max(0.0, float(order.get("entry", 0.0)))
        return qty * entry
