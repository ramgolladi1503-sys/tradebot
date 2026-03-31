from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import pandas as pd

from core.replay_backtest_v2 import ExecutionSimulatorV2
from core.replay_backtest_v3 import BacktestConfigV3, PortfolioRiskManager


@dataclass
class MultiStrategyConfig(BacktestConfigV3):
    max_open_positions: int = 2
    per_symbol_max_positions: int = 1
    portfolio_heat_pct: float = 0.30
    correlation_threshold: float = 0.80
    regime_col: str = "regime"
    allowed_regimes: tuple[str, ...] = ("trend", "volatile", "sideways")


class StrategyAdapter:
    def __init__(self, name: str, fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]], allowed_regimes: tuple[str, ...] | None = None):
        self.name = name
        self.fn = fn
        self.allowed_regimes = tuple(r.lower() for r in (allowed_regimes or ()))

    def generate(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        signal = self.fn(market)
        if not signal:
            return None
        out = dict(signal)
        out.setdefault("strategy_name", self.name)
        return out


class SimpleRegimeClassifier:
    def __init__(self, lookback: int = 20):
        self.lookback = int(lookback)

    def classify(self, data: pd.DataFrame, index: int) -> str:
        if index < max(2, self.lookback):
            return "unknown"
        window = data.iloc[index - self.lookback : index + 1]
        close = window["close"].astype(float)
        ret = close.pct_change().dropna()
        if ret.empty:
            return "unknown"
        vol = float(ret.std())
        trend = abs(float(close.iloc[-1] / max(close.iloc[0], 1e-6) - 1.0))
        if vol > 0.012:
            return "volatile"
        if trend > 0.015:
            return "trend"
        return "sideways"


class CorrelationGate:
    def __init__(self, threshold: float = 0.80, lookback: int = 30):
        self.threshold = float(threshold)
        self.lookback = int(lookback)

    def too_correlated(self, data: pd.DataFrame, index: int, open_positions: list[dict], symbol: str) -> bool:
        if not open_positions:
            return False
        if index < self.lookback + 1:
            return False
        if "symbol" not in data.columns:
            return False
        target = data[data["symbol"] == symbol].iloc[max(0, index - self.lookback): index + 1]
        if len(target) < 5:
            return False
        target_ret = target["close"].astype(float).pct_change().dropna()
        if target_ret.empty:
            return False
        for pos in open_positions:
            other_symbol = pos.get("symbol")
            if other_symbol == symbol:
                return True
            other = data[data["symbol"] == other_symbol].iloc[max(0, index - self.lookback): index + 1]
            if len(other) < 5:
                continue
            other_ret = other["close"].astype(float).pct_change().dropna()
            joined = pd.concat([target_ret.reset_index(drop=True), other_ret.reset_index(drop=True)], axis=1).dropna()
            if len(joined) < 5:
                continue
            corr = joined.iloc[:, 0].corr(joined.iloc[:, 1])
            if pd.notna(corr) and abs(float(corr)) >= self.threshold:
                return True
        return False


class MultiStrategyBacktestEngine:
    def __init__(self, data: pd.DataFrame, strategies: list[StrategyAdapter], config: Optional[MultiStrategyConfig] = None):
        self.data = data.reset_index(drop=True)
        self.strategies = strategies
        self.cfg = config or MultiStrategyConfig()
        self.exec_sim = ExecutionSimulatorV2(self.cfg)
        self.risk = PortfolioRiskManager(self.cfg)
        self.regime = SimpleRegimeClassifier()
        self.corr_gate = CorrelationGate(self.cfg.correlation_threshold)
        self.capital = float(self.cfg.starting_capital)
        self.open_positions: list[dict] = []

    def run(self) -> pd.DataFrame:
        results: list[dict] = []
        latency = max(0, int(self.cfg.latency_bars))

        for i in range(len(self.data)):
            self._close_due_positions(i, results)
            if i + latency >= len(self.data):
                break

            row = self.data.iloc[i]
            ts = row["timestamp"]
            symbol = row.get("symbol", "UNKNOWN")
            regime = self.regime.classify(self.data, i)
            market = row.to_dict()
            market[self.cfg.regime_col] = regime

            allowed, risk_reason = self.risk.can_trade(i, ts, self.capital)
            if not allowed:
                continue
            if len(self.open_positions) >= self.cfg.max_open_positions:
                continue
            if sum(1 for p in self.open_positions if p.get("symbol") == symbol) >= self.cfg.per_symbol_max_positions:
                continue
            if self.corr_gate.too_correlated(self.data, i, self.open_positions, symbol):
                continue

            for strat in self.strategies:
                if strat.allowed_regimes and regime not in strat.allowed_regimes:
                    continue
                signal = strat.generate(market)
                if not signal:
                    continue

                entry_index = i + latency
                if entry_index + self.cfg.horizon >= len(self.data):
                    continue
                entry_bar = self.data.iloc[entry_index].to_dict()
                entry_ref = float(signal.get("entry") or row.get("close") or 0.0)
                stop = float(signal["stop"])
                requested_qty = self.risk.size_trade(self.capital, entry_ref, stop)
                if requested_qty <= 0:
                    continue
                sized_signal = dict(signal)
                sized_signal["qty"] = min(requested_qty, int(signal.get("qty", requested_qty) or requested_qty))
                entry_exec = self.exec_sim.simulate_entry(sized_signal, entry_bar)
                fill_qty = int(entry_exec["fill_qty"])
                if fill_qty <= 0:
                    continue
                notional = float(entry_exec["fill_price"]) * fill_qty
                open_notional = sum(float(p.get("entry_fill", 0.0)) * int(p.get("filled_qty", 0)) for p in self.open_positions)
                if (open_notional + notional) > (self.capital * self.cfg.portfolio_heat_pct):
                    continue

                self.open_positions.append({
                    "strategy_name": strat.name,
                    "symbol": symbol,
                    "regime": regime,
                    "side": str(signal.get("side", "BUY")).upper(),
                    "entry_index": entry_index,
                    "exit_due_index": entry_index + int(self.cfg.horizon),
                    "entry_timestamp": entry_bar.get("timestamp"),
                    "entry_fill": float(entry_exec["fill_price"]),
                    "entry_signal": float(entry_ref),
                    "target": float(signal["target"]),
                    "stop": float(signal["stop"]),
                    "requested_qty": int(sized_signal["qty"]),
                    "filled_qty": fill_qty,
                    "fill_fraction": float(entry_exec["fill_fraction"]),
                    "entry_impact_bps": float(entry_exec["impact_bps"]),
                    "risk_gate": risk_reason,
                    "opened_index": i,
                })
                if len(self.open_positions) >= self.cfg.max_open_positions:
                    break

        self._close_due_positions(len(self.data), results, force=True)
        return pd.DataFrame(results)

    def _close_due_positions(self, index: int, results: list[dict], force: bool = False) -> None:
        if not self.open_positions:
            return
        remaining: list[dict] = []
        for pos in self.open_positions:
            if not force and index <= int(pos["entry_index"]):
                remaining.append(pos)
                continue
            if not force and index < int(pos["exit_due_index"]):
                bar = self.data.iloc[index].to_dict()
                hit_target = float(bar.get("high") or 0.0) >= float(pos["target"])
                hit_stop = float(bar.get("low") or 0.0) <= float(pos["stop"])
                if not (hit_target or hit_stop):
                    remaining.append(pos)
                    continue
                if hit_target and not hit_stop:
                    raw_exit = float(pos["target"])
                    outcome = "TARGET"
                elif hit_stop and not hit_target:
                    raw_exit = float(pos["stop"])
                    outcome = "STOP"
                else:
                    raw_exit = float(bar.get("close") or pos["entry_fill"])
                    outcome = "TIMEOUT"
                exit_bar = bar
            else:
                exit_idx = min(max(int(pos["exit_due_index"]), 0), len(self.data) - 1)
                exit_bar = self.data.iloc[exit_idx].to_dict()
                raw_exit = float(exit_bar.get("close") or pos["entry_fill"])
                outcome = "TIMEOUT" if not force else "FORCED_CLOSE"

            exit_exec = self.exec_sim.simulate_exit(str(pos["side"]), raw_exit, exit_bar, int(pos["filled_qty"]))
            exit_fill = float(exit_exec["fill_price"])
            if str(pos["side"]) == "BUY":
                pl = (exit_fill - float(pos["entry_fill"])) * int(pos["filled_qty"])
            else:
                pl = (float(pos["entry_fill"]) - exit_fill) * int(pos["filled_qty"])
            pl -= self.cfg.fee_per_trade * 2.0
            self.capital += pl
            self.risk.on_trade_close(index, self.capital, pl)
            results.append({
                "strategy_name": pos["strategy_name"],
                "symbol": pos["symbol"],
                "regime": pos["regime"],
                "signal_timestamp": self.data.iloc[int(pos["opened_index"])]["timestamp"],
                "entry_timestamp": pos["entry_timestamp"],
                "entry": pos["entry_signal"],
                "entry_fill": pos["entry_fill"],
                "target": pos["target"],
                "stop": pos["stop"],
                "requested_qty": pos["requested_qty"],
                "filled_qty": pos["filled_qty"],
                "fill_fraction": pos["fill_fraction"],
                "entry_impact_bps": pos["entry_impact_bps"],
                "exit_impact_bps": exit_exec["impact_bps"],
                "risk_gate": pos["risk_gate"],
                "capital": float(self.capital),
                "daily_loss_pct": self.risk.daily_loss_pct(self.capital),
                "drawdown_pct": self.risk.drawdown_pct(self.capital),
                "pl": float(pl),
                "outcome": outcome,
            })
        self.open_positions = remaining
