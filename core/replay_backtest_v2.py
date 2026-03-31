from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import pandas as pd


@dataclass
class BacktestConfigV2:
    starting_capital: float = 100000.0
    fee_per_trade: float = 0.0
    horizon: int = 5
    latency_bars: int = 1
    base_slippage_bps: float = 4.0
    spread_slippage_mult: float = 0.50
    participation_rate: float = 0.10
    impact_bps_per_participation: float = 12.0
    min_fill_fraction: float = 0.25
    default_bar_volume: int = 1000


class ExecutionSimulatorV2:
    def __init__(self, cfg: BacktestConfigV2):
        self.cfg = cfg

    def simulate_entry(self, signal: Dict[str, Any], bar: Dict[str, Any]) -> Dict[str, Any]:
        side = str(signal.get("side", "BUY")).upper()
        open_px = float(bar.get("open") or bar.get("close") or 0.0)
        close_px = float(bar.get("close") or open_px)
        desired_qty = max(1, int(signal.get("qty", 1)))
        bar_volume = max(1, int(bar.get("volume") or self.cfg.default_bar_volume))
        spread_pct = self._spread_pct(bar)

        max_fill_qty = max(1, int(bar_volume * self.cfg.participation_rate))
        fill_qty = min(desired_qty, max_fill_qty)
        fill_fraction = max(self.cfg.min_fill_fraction, fill_qty / max(desired_qty, 1))
        fill_qty = max(1, int(round(desired_qty * fill_fraction)))

        participation = fill_qty / max(bar_volume, 1)
        impact_bps = self.cfg.base_slippage_bps + (spread_pct * 10000.0 * self.cfg.spread_slippage_mult) + (participation * 10000.0 * self.cfg.impact_bps_per_participation)

        ref_price = open_px if open_px > 0 else close_px
        if side == "BUY":
            fill_price = ref_price * (1.0 + impact_bps / 10000.0)
        else:
            fill_price = ref_price * (1.0 - impact_bps / 10000.0)

        return {
            "fill_price": float(fill_price),
            "fill_qty": int(fill_qty),
            "fill_fraction": float(fill_qty / max(desired_qty, 1)),
            "impact_bps": float(impact_bps),
            "spread_pct": float(spread_pct),
        }

    def simulate_exit(self, side: str, exit_price: float, bar: Dict[str, Any], qty: int) -> Dict[str, Any]:
        spread_pct = self._spread_pct(bar)
        bar_volume = max(1, int(bar.get("volume") or self.cfg.default_bar_volume))
        participation = qty / max(bar_volume, 1)
        impact_bps = self.cfg.base_slippage_bps + (spread_pct * 10000.0 * self.cfg.spread_slippage_mult) + (participation * 10000.0 * self.cfg.impact_bps_per_participation)
        if str(side).upper() == "BUY":
            fill_price = float(exit_price) * (1.0 - impact_bps / 10000.0)
        else:
            fill_price = float(exit_price) * (1.0 + impact_bps / 10000.0)
        return {
            "fill_price": float(fill_price),
            "impact_bps": float(impact_bps),
            "spread_pct": float(spread_pct),
        }

    def _spread_pct(self, bar: Dict[str, Any]) -> float:
        high = float(bar.get("high") or bar.get("close") or 0.0)
        low = float(bar.get("low") or bar.get("close") or 0.0)
        close = max(float(bar.get("close") or 0.0), 1e-6)
        intrabar_range_pct = max(0.0, high - low) / close
        return max(0.0005, min(0.02, intrabar_range_pct * 0.15))


class ReplayBacktestEngineV2:
    def __init__(
        self,
        data: pd.DataFrame,
        strategy_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
        config: Optional[BacktestConfigV2] = None,
    ):
        self.data = data.reset_index(drop=True)
        self.strategy_fn = strategy_fn
        self.cfg = config or BacktestConfigV2()
        self.exec_sim = ExecutionSimulatorV2(self.cfg)
        self.capital = float(self.cfg.starting_capital)

    def run(self) -> pd.DataFrame:
        results = []
        start_index = max(0, int(self.cfg.latency_bars))

        for i in range(len(self.data)):
            entry_index = i + start_index
            if entry_index >= len(self.data):
                break
            if entry_index + self.cfg.horizon >= len(self.data):
                break

            signal_bar = self.data.iloc[i]
            signal_market = signal_bar.to_dict()
            signal = self.strategy_fn(signal_market)
            if not signal:
                continue

            side = str(signal.get("side", "BUY")).upper()
            desired_qty = max(1, int(signal.get("qty", 1)))
            entry_bar = self.data.iloc[entry_index].to_dict()
            entry_exec = self.exec_sim.simulate_entry(signal, entry_bar)
            entry_fill = float(entry_exec["fill_price"])
            fill_qty = int(entry_exec["fill_qty"])

            target = float(signal["target"])
            stop = float(signal["stop"])
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

            results.append(
                {
                    "signal_timestamp": signal_bar["timestamp"],
                    "entry_timestamp": entry_bar.get("timestamp"),
                    "symbol": signal_bar.get("symbol", "UNKNOWN"),
                    "entry": float(signal.get("entry", entry_fill)),
                    "entry_fill": entry_fill,
                    "target": target,
                    "stop": stop,
                    "desired_qty": desired_qty,
                    "filled_qty": fill_qty,
                    "fill_fraction": entry_exec["fill_fraction"],
                    "entry_impact_bps": entry_exec["impact_bps"],
                    "exit_impact_bps": exit_exec["impact_bps"],
                    "pl": float(pl),
                    "capital": float(self.capital),
                    "outcome": outcome,
                }
            )

        return pd.DataFrame(results)
