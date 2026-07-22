from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd


def profit_factor(values: np.ndarray) -> float:
    wins = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0.0:
        return math.inf if wins > 0 else 0.0
    return wins / abs(losses)


def t_stat(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    standard = float(np.std(values, ddof=1))
    if standard == 0.0:
        return math.inf if float(np.mean(values)) > 0 else 0.0
    return float(np.mean(values)) / (standard / math.sqrt(len(values)))


def bootstrap_lower(
    values: np.ndarray,
    *,
    iterations: int,
    seed: int,
) -> float:
    if len(values) < 2:
        return -math.inf
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(values), size=(iterations, len(values)))
    means = values[indexes].mean(axis=1)
    return float(np.quantile(means, 0.025))


def chronological_fold_fraction(
    rows: pd.DataFrame,
    outcome_column: str,
    folds: int = 4,
) -> tuple[float, list[float]]:
    ordered = rows.sort_values("session_date", kind="mergesort")
    boundaries = np.linspace(0, len(ordered), folds + 1, dtype=int)
    means: list[float] = []
    for index in range(folds):
        chunk = ordered.iloc[boundaries[index] : boundaries[index + 1]]
        means.append(
            math.nan
            if len(chunk) < 5
            else float(chunk[outcome_column].mean())
        )
    valid = [value for value in means if math.isfinite(value)]
    if len(valid) != folds:
        return 0.0, means
    return float(sum(value > 0 for value in valid) / folds), means


def max_stat_pvalue(
    features: pd.DataFrame,
    masks: Sequence[pd.Series],
    outcome_column: str,
    observed_max_t: float,
    *,
    iterations: int,
    seed: int,
) -> float:
    rng = np.random.default_rng(seed)
    outcomes = features[outcome_column].to_numpy(dtype=float)
    mask_arrays = [mask.to_numpy(dtype=bool) for mask in masks]
    max_stats = np.zeros(iterations, dtype=float)
    for index in range(iterations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(features))
        permuted = outcomes * signs
        stats: list[float] = []
        for mask in mask_arrays:
            values = permuted[mask]
            values = values[np.isfinite(values)]
            stats.append(t_stat(values))
        max_stats[index] = max(stats) if stats else 0.0
    return float(
        (1 + np.sum(max_stats >= observed_max_t)) / (iterations + 1)
    )
