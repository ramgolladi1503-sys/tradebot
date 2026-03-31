from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any

import pandas as pd

from core.multi_strategy_backtest import (
    MultiStrategyConfig,
    StrategyAdapter,
    MultiStrategyBacktestEngine,
)


@dataclass
class AdaptiveStrategyState:
    name: str
    enabled: bool = True
    rolling_window: int = 20
    min_trades_for_eval: int = 5
    decay_threshold: float = -0.02
    cooldown_trades: int = 10
    recent_pl: list[float] = field(default_factory=list)
    cooldown_remaining: int = 0
    last_score: float = 0.0

    def on_trade_close(self, pl: float) -> None:
        self.recent_pl.append(float(pl))
        if len(self.recent_pl) > self.rolling_window:
            self.recent_pl = self.recent_pl[-self.rolling_window :]
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1
        self.last_score = self.score()
        if len(self.recent_pl) >= self.min_trades_for_eval and self.last_score <= self.decay_threshold:
            self.enabled = False
            self.cooldown_remaining = self.cooldown_trades

    def maybe_reenable(self) -> None:
        if not self.enabled and self.cooldown_remaining <= 0:
            self.enabled = True
            self.recent_pl = []
            self.last_score = 0.0

    def score(self) -> float:
        if not self.recent_pl:
            return 0.0
        total = sum(self.recent_pl)
        denom = sum(abs(x) for x in self.recent_pl) or 1.0
        return float(total / denom)


@dataclass
class AdaptivePortfolioConfig(MultiStrategyConfig):
    rolling_window: int = 20
    min_trades_for_eval: int = 5
    decay_threshold: float = -0.02
    cooldown_trades: int = 10
    selection_top_k: int = 2


class AdaptiveStrategyAdapter(StrategyAdapter):
    def __init__(self, name: str, fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]], allowed_regimes: tuple[str, ...] | None = None):
        super().__init__(name=name, fn=fn, allowed_regimes=allowed_regimes)
        self.state: Optional[AdaptiveStrategyState] = None


class AdaptivePortfolioEngine(MultiStrategyBacktestEngine):
    def __init__(self, data: pd.DataFrame, strategies: list[AdaptiveStrategyAdapter], config: Optional[AdaptivePortfolioConfig] = None):
        self.adaptive_cfg = config or AdaptivePortfolioConfig()
        super().__init__(data=data, strategies=strategies, config=self.adaptive_cfg)
        self.strategy_states: dict[str, AdaptiveStrategyState] = {}
        for strat in self.strategies:
            state = AdaptiveStrategyState(
                name=strat.name,
                rolling_window=self.adaptive_cfg.rolling_window,
                min_trades_for_eval=self.adaptive_cfg.min_trades_for_eval,
                decay_threshold=self.adaptive_cfg.decay_threshold,
                cooldown_trades=self.adaptive_cfg.cooldown_trades,
            )
            strat.state = state
            self.strategy_states[strat.name] = state

    def run(self) -> pd.DataFrame:
        results = super().run()
        if results.empty:
            return results
        for _, row in results.iterrows():
            state = self.strategy_states.get(str(row.get("strategy_name")))
            if state:
                state.on_trade_close(float(row.get("pl", 0.0)))
                state.maybe_reenable()
        return results

    def _eligible_strategies(self, regime: str) -> list[AdaptiveStrategyAdapter]:
        ranked: list[tuple[float, AdaptiveStrategyAdapter]] = []
        for strat in self.strategies:
            state = self.strategy_states[strat.name]
            state.maybe_reenable()
            if not state.enabled:
                continue
            if strat.allowed_regimes and regime not in strat.allowed_regimes:
                continue
            ranked.append((state.score(), strat))
        ranked.sort(key=lambda x: x[0], reverse=True)
        top_k = max(1, int(self.adaptive_cfg.selection_top_k))
        return [s for _, s in ranked[:top_k]]

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

            for strat in self._eligible_strategies(regime):
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
        frame = pd.DataFrame(results)
        if not frame.empty:
            for _, row in frame.iterrows():
                state = self.strategy_states.get(str(row.get("strategy_name")))
                if state:
                    state.on_trade_close(float(row.get("pl", 0.0)))
                    state.maybe_reenable()
            frame["strategy_score"] = frame["strategy_name"].map(lambda n: self.strategy_states[str(n)].last_score if str(n) in self.strategy_states else 0.0)
            frame["strategy_enabled"] = frame["strategy_name"].map(lambda n: self.strategy_states[str(n)].enabled if str(n) in self.strategy_states else True)
        return frame
