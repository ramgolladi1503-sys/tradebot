from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import pandas as pd

from core.replay_backtest_v2 import ExecutionSimulatorV2, BacktestConfigV2


@dataclass
class RiskConfig:
    starting_capital: float = 100000.0
    risk_per_trade_pct: float = 0.01
    max_notional_pct: float = 0.20
    max_open_positions: int = 1
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.12
    cooldown_bars_after_loss: int = 3


@dataclass
class BacktestConfigV3(BacktestConfigV2):
    risk_per_trade_pct: float = 0.01
    max_notional_pct: float = 0.20
    max_open_positions: int = 1
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.12
    cooldown_bars_after_loss: int = 3


class PortfolioRiskManager:
    def __init__(self, cfg: BacktestConfigV3):
        self.cfg = cfg
        self.equity_peak = float(cfg.starting_capital)
        self.cooldown_until_index = -1
        self.current_day = None
        self.daily_start_capital = float(cfg.starting_capital)

    def reset_day_if_needed(self, timestamp, capital: float):
        day = pd.Timestamp(timestamp).date()
        if self.current_day != day:
            self.current_day = day
            self.daily_start_capital = float(capital)

    def can_trade(self, index: int, timestamp, capital: float) -> tuple[bool, str]:
        self.reset_day_if_needed(timestamp, capital)
        if index <= self.cooldown_until_index:
            return False, "cooldown"
        if self.daily_loss_pct(capital) >= self.cfg.max_daily_loss_pct:
            return False, "daily_loss_limit"
        drawdown_pct = self.drawdown_pct(capital)
        if drawdown_pct >= self.cfg.max_drawdown_pct:
            return False, "max_drawdown_limit"
        return True, "ok"

    def size_trade(self, capital: float, entry_price: float, stop_price: float) -> int:
        entry_price = max(float(entry_price), 1e-6)
        stop_price = float(stop_price)
        risk_per_unit = abs(entry_price - stop_price)
        if risk_per_unit <= 0:
            return 0
        risk_budget = capital * self.cfg.risk_per_trade_pct
        qty_by_risk = int(risk_budget / risk_per_unit)
        max_notional = capital * self.cfg.max_notional_pct
        qty_by_notional = int(max_notional / entry_price)
        return max(0, min(qty_by_risk, qty_by_notional))

    def on_trade_close(self, index: int, capital: float, pl: float):
        self.equity_peak = max(self.equity_peak, float(capital))
        if pl < 0:
            self.cooldown_until_index = max(self.cooldown_until_index, index + int(self.cfg.cooldown_bars_after_loss))

    def daily_loss_pct(self, capital: float) -> float:
        base = max(self.daily_start_capital, 1e-6)
        return max(0.0, (self.daily_start_capital - capital) / base)

    def drawdown_pct(self, capital: float) -> float:
        peak = max(self.equity_peak, 1e-6)
        return max(0.0, (peak - capital) / peak)


class ReplayBacktestEngineV3:
    def __init__(
        self,
        data: pd.DataFrame,
        strategy_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
        config: Optional[BacktestConfigV3] = None,
    ):
        self.data = data.reset_index(drop=True)
        self.strategy_fn = strategy_fn
        self.cfg = config or BacktestConfigV3()
        self.exec_sim = ExecutionSimulatorV2(self.cfg)
        self.capital = float(self.cfg.starting_capital)
        self.risk = PortfolioRiskManager(self.cfg)

    def run(self) -> pd.DataFrame:
        results = []
        latency = max(0, int(self.cfg.latency_bars))

        for i in range(len(self.data)):
            entry_index = i + latency
            if entry_index >= len(self.data):
                break
            if entry_index + self.cfg.horizon >= len(self.data):
                break

            signal_bar = self.data.iloc[i]
            signal_ts = signal_bar["timestamp"]
            allowed, reason = self.risk.can_trade(i, signal_ts, self.capital)
            if not allowed:
                continue

            signal_market = signal_bar.to_dict()
            signal = self.strategy_fn(signal_market)
            if not signal:
                continue

            side = str(signal.get("side", "BUY")).upper()
            entry_ref = float(signal.get("entry") or signal_bar.get("close") or 0.0)
            stop = float(signal["stop"])
            target = float(signal["target"])
            risk_qty = self.risk.size_trade(self.capital, entry_ref, stop)
            requested_qty = min(max(1, int(signal.get("qty", 1))), risk_qty if risk_qty > 0 else 0)
            if requested_qty <= 0:
                continue

            entry_bar = self.data.iloc[entry_index].to_dict()
            sized_signal = dict(signal)
            sized_signal["qty"] = requested_qty
            entry_exec = self.exec_sim.simulate_entry(sized_signal, entry_bar)
            entry_fill = float(entry_exec["fill_price"])
            fill_qty = int(entry_exec["fill_qty"])
            if fill_qty <= 0:
                continue

            future = self.data.iloc[entry_index + 1 : entry_index + 1 + self.cfg.horizon]
            hit_target = (future["high"] >= target).any()
            hit_stop = (future["low"] <= stop).any()

            if hit_target and not hit_stop:
                raw_exit = target
                outcome = "TARGET"
                exit_bar = future[future["high"] >= target].iloc[0].to_dict()
            elif hit_stop and not hit_target:
                raw_exit = stop
                outcome = "STOP"
                exit_bar = future[future["low"] <= stop].iloc[0].to_dict()
            else:
                raw_exit = float(future["close"].iloc[-1])
                outcome = "TIMEOUT"
                exit_bar = future.iloc[-1].to_dict()

            exit_exec = self.exec_sim.simulate_exit(side, raw_exit, exit_bar, fill_qty)
            exit_fill = float(exit_exec["fill_price"])
            if side == "BUY":
                pl = (exit_fill - entry_fill) * fill_qty
            else:
                pl = (entry_fill - exit_fill) * fill_qty
            pl -= self.cfg.fee_per_trade * 2.0
            self.capital += pl
            self.risk.on_trade_close(i, self.capital, pl)

            results.append(
                {
                    "signal_timestamp": signal_ts,
                    "entry_timestamp": entry_bar.get("timestamp"),
                    "symbol": signal_bar.get("symbol", "UNKNOWN"),
                    "risk_gate": reason,
                    "entry": entry_ref,
                    "entry_fill": entry_fill,
                    "target": target,
                    "stop": stop,
                    "requested_qty": requested_qty,
                    "filled_qty": fill_qty,
                    "fill_fraction": entry_exec["fill_fraction"],
                    "entry_impact_bps": entry_exec["impact_bps"],
                    "exit_impact_bps": exit_exec["impact_bps"],
                    "pl": float(pl),
                    "capital": float(self.capital),
                    "daily_loss_pct": self.risk.daily_loss_pct(self.capital),
                    "drawdown_pct": self.risk.drawdown_pct(self.capital),
                    "outcome": outcome,
                }
            )

        return pd.DataFrame(results)
