from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PBOResult:
    pbo: float
    logits: tuple[float, ...]
    selected_trial_indices: tuple[int, ...]
    split_count: int
    subgroup_count: int


def _sharpe_per_column(values: np.ndarray) -> np.ndarray:
    means = values.mean(axis=0)
    stds = values.std(axis=0, ddof=1)
    result = np.full(values.shape[1], -np.inf, dtype=float)
    valid = stds > 0.0
    result[valid] = means[valid] / stds[valid]
    return result


def _fractional_rank(values: np.ndarray, selected_index: int) -> float:
    selected = values[selected_index]
    if not math.isfinite(float(selected)):
        return 0.5
    lower = float(np.sum(values < selected))
    equal = float(np.sum(values == selected))
    rank = lower + 0.5 * equal
    n = float(values.size)
    return min(1.0 - 0.5 / n, max(0.5 / n, rank / n))


def probability_of_backtest_overfitting(
    candidate_returns: np.ndarray,
    *,
    subgroup_count: int = 8,
    max_splits: int = 5000,
) -> PBOResult:
    """Estimate PBO using Combinatorially Symmetric Cross-Validation.

    Rows are chronological observations and columns are candidate strategies.
    Each split selects the best in-sample Sharpe candidate and measures that
    candidate's relative out-of-sample rank. PBO is the share of splits whose
    OOS logit rank is <= 0 (at or below the median).
    """
    returns = np.asarray(candidate_returns, dtype=float)
    if returns.ndim != 2 or returns.shape[0] < 4 or returns.shape[1] < 2:
        raise ValueError("candidate_returns_must_have_observations_and_multiple_trials")
    if not np.all(np.isfinite(returns)):
        raise ValueError("candidate_returns_must_be_finite")
    if subgroup_count < 4 or subgroup_count % 2 != 0:
        raise ValueError("subgroup_count_must_be_even_and_at_least_four")
    if subgroup_count > returns.shape[0]:
        raise ValueError("subgroup_count_exceeds_observations")

    groups = [
        np.asarray(indexes, dtype=int)
        for indexes in np.array_split(np.arange(returns.shape[0]), subgroup_count)
    ]
    half = subgroup_count // 2
    combinations = list(itertools.combinations(range(subgroup_count), half))
    if len(combinations) > max_splits:
        raise ValueError("pbo_split_count_exceeds_safety_bound")

    logits: list[float] = []
    selected: list[int] = []
    all_groups = set(range(subgroup_count))
    for train_groups in combinations:
        train_set = set(train_groups)
        test_groups = sorted(all_groups - train_set)
        train_rows = np.concatenate([groups[i] for i in train_groups])
        test_rows = np.concatenate([groups[i] for i in test_groups])
        is_scores = _sharpe_per_column(returns[train_rows, :])
        if not np.any(np.isfinite(is_scores)):
            raise ValueError("pbo_no_finite_in_sample_scores")
        winner = int(np.nanargmax(is_scores))
        oos_scores = _sharpe_per_column(returns[test_rows, :])
        percentile = _fractional_rank(oos_scores, winner)
        logit = math.log(percentile / (1.0 - percentile))
        logits.append(float(logit))
        selected.append(winner)

    pbo = float(np.mean(np.asarray(logits) <= 0.0))
    return PBOResult(
        pbo=pbo,
        logits=tuple(logits),
        selected_trial_indices=tuple(selected),
        split_count=len(logits),
        subgroup_count=subgroup_count,
    )
