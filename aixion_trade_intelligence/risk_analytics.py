from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence


def _finite_returns(values: Sequence[float]) -> list[float]:
    rows = [float(value) for value in values]
    if not rows or any(not math.isfinite(value) or value <= -1.0 for value in rows):
        raise ValueError("session_returns_invalid")
    return rows


def _max_drawdown(equity: Sequence[float]) -> tuple[float, int]:
    peak = equity[0]
    maximum = 0.0
    duration = 0
    current_duration = 0
    for value in equity:
        if value >= peak:
            peak = value
            current_duration = 0
        else:
            current_duration += 1
            duration = max(duration, current_duration)
            maximum = max(maximum, (peak - value) / peak)
    return maximum, duration


def _longest_losing_streak(returns: Sequence[float]) -> int:
    best = current = 0
    for value in returns:
        if value < 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


@dataclass(frozen=True)
class RiskSimulation:
    paths: int
    periods_per_path: int
    ruin_fraction: float
    ruin_probability: float
    drawdown_thresholds: dict[float, float]
    median_terminal_capital: float
    median_max_drawdown: float
    median_drawdown_duration: float
    median_longest_losing_streak: float

    def to_record(self) -> dict[str, object]:
        return {"paths": self.paths, "periods_per_path": self.periods_per_path, "ruin_fraction": self.ruin_fraction, "ruin_probability": self.ruin_probability, "drawdown_thresholds": {str(key): value for key, value in self.drawdown_thresholds.items()}, "median_terminal_capital": self.median_terminal_capital, "median_max_drawdown": self.median_max_drawdown, "median_drawdown_duration": self.median_drawdown_duration, "median_longest_losing_streak": self.median_longest_losing_streak}


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def block_bootstrap_risk(session_returns: Sequence[float], *, initial_capital: float, block_length: int, periods_per_path: int, paths: int, ruin_fraction: float, drawdown_thresholds: Sequence[float], seed: int) -> RiskSimulation:
    returns = _finite_returns(session_returns)
    capital = float(initial_capital)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("initial_capital_invalid")
    if block_length <= 0 or block_length > len(returns):
        raise ValueError("block_length_invalid")
    if periods_per_path <= 0 or paths <= 0:
        raise ValueError("simulation_shape_invalid")
    ruin = float(ruin_fraction)
    if not 0 < ruin < 1:
        raise ValueError("ruin_fraction_out_of_range")
    thresholds = [float(value) for value in drawdown_thresholds]
    if not thresholds or any(not 0 < value < 1 for value in thresholds):
        raise ValueError("drawdown_thresholds_invalid")
    rng = random.Random(seed)
    starts = list(range(0, len(returns) - block_length + 1))
    terminal_values: list[float] = []
    drawdowns: list[float] = []
    durations: list[float] = []
    streaks: list[float] = []
    ruined = 0
    threshold_hits = {value: 0 for value in thresholds}
    ruin_capital = capital * ruin
    for _ in range(paths):
        path_returns: list[float] = []
        while len(path_returns) < periods_per_path:
            start = rng.choice(starts)
            path_returns.extend(returns[start:start + block_length])
        path_returns = path_returns[:periods_per_path]
        equity = [capital]
        is_ruined = False
        for value in path_returns:
            equity.append(equity[-1] * (1.0 + value))
            if equity[-1] <= ruin_capital:
                is_ruined = True
        maximum, duration = _max_drawdown(equity)
        for threshold in thresholds:
            if maximum >= threshold:
                threshold_hits[threshold] += 1
        ruined += int(is_ruined)
        terminal_values.append(equity[-1])
        drawdowns.append(maximum)
        durations.append(float(duration))
        streaks.append(float(_longest_losing_streak(path_returns)))
    return RiskSimulation(paths, periods_per_path, ruin, ruined / paths, {threshold: threshold_hits[threshold] / paths for threshold in thresholds}, _median(terminal_values), _median(drawdowns), _median(durations), _median(streaks))
