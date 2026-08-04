from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import NormalDist
from typing import Callable, Sequence


def _finite(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}_not_finite")
    return out


@dataclass(frozen=True)
class LabelInterval:
    sample_id: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise ValueError("sample_id_missing")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("label_interval_timezone_required")
        if self.end < self.start:
            raise ValueError("label_interval_invalid")


@dataclass(frozen=True)
class PurgedSplit:
    fold: int
    train_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    purged_ids: tuple[str, ...]
    embargoed_ids: tuple[str, ...]


def purged_embargoed_splits(intervals: Sequence[LabelInterval], *, n_splits: int, embargo: timedelta) -> list[PurgedSplit]:
    if n_splits < 2:
        raise ValueError("n_splits_must_be_at_least_two")
    if embargo.total_seconds() < 0:
        raise ValueError("embargo_negative")
    ordered = sorted(intervals, key=lambda item: (item.start, item.end, item.sample_id))
    if len(ordered) < n_splits:
        raise ValueError("insufficient_samples_for_splits")
    ids = [item.sample_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_sample_id")
    fold_sizes = [len(ordered) // n_splits] * n_splits
    for index in range(len(ordered) % n_splits):
        fold_sizes[index] += 1
    boundaries = []
    cursor = 0
    for size in fold_sizes:
        boundaries.append((cursor, cursor + size))
        cursor += size
    splits: list[PurgedSplit] = []
    for fold, (start_idx, end_idx) in enumerate(boundaries):
        test = ordered[start_idx:end_idx]
        test_start = min(item.start for item in test)
        test_end = max(item.end for item in test)
        embargo_end = test_end + embargo
        train_ids: list[str] = []
        purged_ids: list[str] = []
        embargoed_ids: list[str] = []
        test_ids = {item.sample_id for item in test}
        for sample in ordered:
            if sample.sample_id in test_ids:
                continue
            overlaps = sample.start <= test_end and sample.end >= test_start
            in_embargo = test_end < sample.start <= embargo_end
            if overlaps:
                purged_ids.append(sample.sample_id)
            elif in_embargo:
                embargoed_ids.append(sample.sample_id)
            else:
                train_ids.append(sample.sample_id)
        splits.append(PurgedSplit(fold, tuple(train_ids), tuple(item.sample_id for item in test), tuple(purged_ids), tuple(embargoed_ids)))
    return splits


def probabilistic_sharpe_ratio(*, observed_sharpe: float, benchmark_sharpe: float, observations: int, skewness: float, kurtosis: float) -> float:
    sr = _finite(observed_sharpe, name="observed_sharpe")
    benchmark = _finite(benchmark_sharpe, name="benchmark_sharpe")
    skew = _finite(skewness, name="skewness")
    kurt = _finite(kurtosis, name="kurtosis")
    if observations < 2:
        raise ValueError("observations_too_small")
    denominator_term = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if denominator_term <= 0:
        raise ValueError("probabilistic_sharpe_denominator_nonpositive")
    z = (sr - benchmark) * math.sqrt(observations - 1.0) / math.sqrt(denominator_term)
    return NormalDist().cdf(z)


_EULER_MASCHERONI = 0.5772156649015329


def expected_maximum_sharpe(*, trials: int, sharpe_std: float) -> float:
    if trials < 1:
        raise ValueError("trials_must_be_positive")
    sigma = _finite(sharpe_std, name="sharpe_std")
    if sigma < 0:
        raise ValueError("sharpe_std_negative")
    if trials == 1 or sigma == 0:
        return 0.0
    normal = NormalDist()
    first = normal.inv_cdf(1.0 - 1.0 / trials)
    second = normal.inv_cdf(1.0 - 1.0 / (trials * math.e))
    return sigma * ((1.0 - _EULER_MASCHERONI) * first + _EULER_MASCHERONI * second)


def deflated_sharpe_ratio(*, observed_sharpe: float, observations: int, skewness: float, kurtosis: float, trials: int, trial_sharpe_std: float) -> dict[str, float]:
    benchmark = expected_maximum_sharpe(trials=trials, sharpe_std=trial_sharpe_std)
    probability = probabilistic_sharpe_ratio(observed_sharpe=observed_sharpe, benchmark_sharpe=benchmark, observations=observations, skewness=skewness, kurtosis=kurtosis)
    return {"observed_sharpe": float(observed_sharpe), "deflated_benchmark_sharpe": benchmark, "probability": probability, "trials": float(trials)}


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("metric_values_empty")
    return sum(values) / len(values)


def _sharpe(values: Sequence[float]) -> float:
    if len(values) < 2:
        return float("-inf")
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance <= 0:
        return float("inf") if mean > 0 else float("-inf")
    return mean / math.sqrt(variance)


def probability_of_backtest_overfitting(returns_by_period_and_strategy: Sequence[Sequence[float]], *, partitions: int, metric: str = "SHARPE") -> dict[str, object]:
    matrix = [tuple(_finite(value, name="return") for value in row) for row in returns_by_period_and_strategy]
    if not matrix:
        raise ValueError("pbo_matrix_empty")
    strategy_count = len(matrix[0])
    if strategy_count < 2 or any(len(row) != strategy_count for row in matrix):
        raise ValueError("pbo_matrix_shape_invalid")
    if partitions < 2 or partitions % 2:
        raise ValueError("partitions_must_be_even_and_at_least_two")
    if len(matrix) < partitions:
        raise ValueError("insufficient_periods_for_partitions")
    scorer: Callable[[Sequence[float]], float]
    normalized_metric = metric.strip().upper()
    if normalized_metric == "SHARPE":
        scorer = _sharpe
    elif normalized_metric == "MEAN":
        scorer = _mean
    else:
        raise ValueError(f"unsupported_pbo_metric={normalized_metric}")
    sizes = [len(matrix) // partitions] * partitions
    for index in range(len(matrix) % partitions):
        sizes[index] += 1
    blocks: list[list[int]] = []
    cursor = 0
    for size in sizes:
        blocks.append(list(range(cursor, cursor + size)))
        cursor += size
    logits: list[float] = []
    combinations_count = 0
    for train_blocks in itertools.combinations(range(partitions), partitions // 2):
        train_block_set = set(train_blocks)
        train_rows = [index for block in train_blocks for index in blocks[block]]
        test_rows = [index for block in range(partitions) if block not in train_block_set for index in blocks[block]]
        train_scores = [scorer([matrix[row][strategy] for row in train_rows]) for strategy in range(strategy_count)]
        best_strategy = max(range(strategy_count), key=lambda index: train_scores[index])
        test_scores = [scorer([matrix[row][strategy] for row in test_rows]) for strategy in range(strategy_count)]
        selected_score = test_scores[best_strategy]
        rank = 1 + sum(score < selected_score for score in test_scores)
        relative_rank = rank / (strategy_count + 1.0)
        logits.append(math.log(relative_rank / (1.0 - relative_rank)))
        combinations_count += 1
    return {"probability_of_backtest_overfitting": sum(value < 0 for value in logits) / len(logits), "logits": logits, "combinations": combinations_count, "partitions": partitions, "metric": normalized_metric}


def compare_to_baseline(strategy_returns: Sequence[float], baseline_returns: Sequence[float]) -> dict[str, float]:
    if len(strategy_returns) != len(baseline_returns) or not strategy_returns:
        raise ValueError("baseline_comparison_shape_invalid")
    strategy = [_finite(value, name="strategy_return") for value in strategy_returns]
    baseline = [_finite(value, name="baseline_return") for value in baseline_returns]
    differences = [left - right for left, right in zip(strategy, baseline)]
    mean_difference = _mean(differences)
    if len(differences) < 2:
        standard_error = 0.0
    else:
        variance = sum((value - mean_difference) ** 2 for value in differences) / (len(differences) - 1)
        standard_error = math.sqrt(variance / len(differences))
    return {"strategy_mean": _mean(strategy), "baseline_mean": _mean(baseline), "mean_incremental_return": mean_difference, "standard_error": standard_error}
