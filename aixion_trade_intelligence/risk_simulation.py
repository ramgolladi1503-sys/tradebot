from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RiskSimulationResult:
    paths: int
    periods: int
    ruin_fraction: float
    median_terminal_equity: float
    median_max_drawdown: float
    worst_max_drawdown: float
    terminal_equity_quantiles: dict[str, float]

    def to_record(self) -> dict[str, object]:
        return {
            "paths": self.paths,
            "periods": self.periods,
            "ruin_fraction": self.ruin_fraction,
            "median_terminal_equity": self.median_terminal_equity,
            "median_max_drawdown": self.median_max_drawdown,
            "worst_max_drawdown": self.worst_max_drawdown,
            "terminal_equity_quantiles": dict(self.terminal_equity_quantiles),
        }


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile_values_empty")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def block_bootstrap_risk(
    session_returns: Sequence[float],
    *,
    initial_equity: float,
    ruin_equity: float,
    periods: int,
    paths: int,
    block_length: int,
    seed: int,
) -> RiskSimulationResult:
    returns = [float(value) for value in session_returns]
    if not returns or any(not math.isfinite(value) or value <= -1.0 for value in returns):
        raise ValueError("session_returns_invalid")
    if initial_equity <= 0 or ruin_equity < 0 or ruin_equity >= initial_equity:
        raise ValueError("equity_bounds_invalid")
    if periods <= 0 or paths <= 0 or block_length <= 0:
        raise ValueError("simulation_dimensions_must_be_positive")
    if block_length > len(returns):
        raise ValueError("block_length_exceeds_history")
    rng = random.Random(seed)
    terminals: list[float] = []
    drawdowns: list[float] = []
    ruined = 0
    maximum_start = len(returns) - block_length
    for _ in range(paths):
        sampled: list[float] = []
        while len(sampled) < periods:
            start = rng.randint(0, maximum_start)
            sampled.extend(returns[start : start + block_length])
        equity = initial_equity
        peak = initial_equity
        maximum_drawdown = 0.0
        path_ruined = False
        for value in sampled[:periods]:
            equity *= 1.0 + value
            peak = max(peak, equity)
            maximum_drawdown = max(maximum_drawdown, 1.0 - equity / peak)
            if equity <= ruin_equity:
                path_ruined = True
        ruined += int(path_ruined)
        terminals.append(equity)
        drawdowns.append(maximum_drawdown)
    return RiskSimulationResult(
        paths=paths,
        periods=periods,
        ruin_fraction=ruined / paths,
        median_terminal_equity=_quantile(terminals, 0.5),
        median_max_drawdown=_quantile(drawdowns, 0.5),
        worst_max_drawdown=max(drawdowns),
        terminal_equity_quantiles={
            "q05": _quantile(terminals, 0.05),
            "q25": _quantile(terminals, 0.25),
            "q50": _quantile(terminals, 0.50),
            "q75": _quantile(terminals, 0.75),
            "q95": _quantile(terminals, 0.95),
        },
    )
