from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import pandas as pd

warnings.warn(
    "tools.legacy.replay_backtest.ReplayBacktestEngine is deprecated. "
    "Use core.replay_engine.ReplayEngine or scripts/validate_system.py as the canonical replay path.",
    DeprecationWarning,
    stacklevel=2,
)


@dataclass
class BacktestConfig:
    starting_capital: float = 100000.0
    slippage_bps: float = 5.0
    spread_bps: float = 5.0
    fee_per_trade: float = 0.0
    horizon: int = 5


class ExecutionSimulator:
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg

    def apply_cost(self, price: float, side: str) -> float:
        bps = self.cfg.slippage_bps + self.cfg.spread_bps
        if side == "BUY":
            return price * (1 + bps / 10000.0)
        return price * (1 - bps / 10000.0)


class ReplayBacktestEngine:
    def __init__(
        self,
        data: pd.DataFrame,
        strategy_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
        config: Optional[BacktestConfig] = None,
    ):
        self.data = data.reset_index(drop=True)
        self.strategy_fn = strategy_fn
        self.cfg = config or BacktestConfig()
        self.exec_sim = ExecutionSimulator(self.cfg)
        self.capital = self.cfg.starting_capital

    def run(self) -> pd.DataFrame:
        results = []

        for i in range(len(self.data)):
            if i + self.cfg.horizon >= len(self.data):
                break

            row = self.data.iloc[i]
            market = row.to_dict()

            signal = self.strategy_fn(market)
            if not signal:
                continue

            entry_price = signal["entry"]
            target = signal["target"]
            stop = signal["stop"]
            side = signal.get("side", "BUY")
            qty = signal.get("qty", 1)

            future = self.data.iloc[i + 1 : i + 1 + self.cfg.horizon]

            hit_target = (future["high"] >= target).any()
            hit_stop = (future["low"] <= stop).any()

            entry_fill = self.exec_sim.apply_cost(entry_price, "BUY")

            if hit_target and not hit_stop:
                exit_fill = self.exec_sim.apply_cost(target, "SELL")
                outcome = "TARGET"
            elif hit_stop and not hit_target:
                exit_fill = self.exec_sim.apply_cost(stop, "SELL")
                outcome = "STOP"
            else:
                exit_fill = self.exec_sim.apply_cost(future["close"].iloc[-1], "SELL")
                outcome = "TIMEOUT"

            pl = (exit_fill - entry_fill) * qty
            pl -= self.cfg.fee_per_trade * 2

            self.capital += pl

            results.append(
                {
                    "timestamp": row["timestamp"],
                    "symbol": row.get("symbol", "UNKNOWN"),
                    "entry": entry_price,
                    "target": target,
                    "stop": stop,
                    "qty": qty,
                    "pl": pl,
                    "capital": self.capital,
                    "outcome": outcome,
                }
            )

        return pd.DataFrame(results)
