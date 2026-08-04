from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import NormalDist
from typing import Iterable, Sequence


@dataclass(frozen=True)
class TimedSample:
    sample_id: str
    start_time: datetime
    end_time: datetime

    def __post_init__(self) -> None:
        if not self.sample_id:
            raise ValueError("sample_id_missing")
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("sample_times_must_be_timezone_aware")
        if self.end_time < self.start_time:
            raise ValueError("sample_interval_invalid")


@dataclass(frozen=True)
class PurgedSplit:
    train_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    purged_ids: tuple[str, ...]
    embargoed_ids: tuple[str, ...]


def purged_embargo_split(
    samples: Sequence[TimedSample],
    *,
    validation_start: datetime,
    validation_end: datetime,
    embargo: timedelta,
) -> PurgedSplit:
    if validation_start.tzinfo is None or validation_end.tzinfo is None:
        raise ValueError("validation_times_must_be_timezone_aware")
    if validation_end < validation_start:
        raise ValueError("validation_interval_invalid")
    if embargo < timedelta(0):
        raise ValueError("embargo_negative")
    validation: list[str] = []
    train: list[str] = []
    purged: list[str] = []
    embargoed: list[str] = []
    embargo_end = validation_end + embargo
    for sample in samples:
        overlaps_validation = not (
            sample.end_time < validation_start or sample.start_time > validation_end
        )
        starts_in_embargo = validation_end < sample.start_time <= embargo_end
        if validation_start <= sample.start_time <= validation_end:
            validation.append(sample.sample_id)
        elif overlaps_validation:
            purged.append(sample.sample_id)
        elif starts_in_embargo:
            embargoed.append(sample.sample_id)
        else:
            train.append(sample.sample_id)
    return PurgedSplit(tuple(train), tuple(validation), tuple(purged), tuple(embargoed))


def _moments(values: Sequence[float]) -> tuple[float, float, float, float]:
    if len(values) < 3:
        raise ValueError("at_least_three_returns_required")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("returns_not_finite")
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    variance = sum(value * value for value in centered) / (len(values) - 1)
    if variance <= 0:
        raise ValueError("return_variance_nonpositive")
    std = math.sqrt(variance)
    skew = sum((value / std) ** 3 for value in centered) / len(values)
    kurtosis = sum((value / std) ** 4 for value in centered) / len(values)
    return mean, std, skew, kurtosis


def probabilistic_sharpe_ratio(
    returns: Sequence[float],
    *,
    benchmark_sharpe: float = 0.0,
    annualization_factor: float = 1.0,
) -> float:
    if annualization_factor <= 0:
        raise ValueError("annualization_factor_nonpositive")
    mean, std, skew, kurtosis = _moments(returns)
    observed = mean / std * math.sqrt(annualization_factor)
    denominator_term = 1.0 - skew * observed + ((kurtosis - 1.0) / 4.0) * observed * observed
    if denominator_term <= 0:
        raise ValueError("probabilistic_sharpe_denominator_nonpositive")
    statistic = (observed - benchmark_sharpe) * math.sqrt(len(returns) - 1.0) / math.sqrt(denominator_term)
    return NormalDist().cdf(statistic)


def expected_maximum_sharpe(
    *,
    independent_trials: int,
    sharpe_std: float,
) -> float:
    if independent_trials <= 0:
        raise ValueError("independent_trials_nonpositive")
    if sharpe_std < 0 or not math.isfinite(sharpe_std):
        raise ValueError("sharpe_std_invalid")
    if independent_trials == 1 or sharpe_std == 0:
        return 0.0
    euler_gamma = 0.5772156649015329
    normal = NormalDist()
    first = normal.inv_cdf(1.0 - 1.0 / independent_trials)
    second = normal.inv_cdf(1.0 - 1.0 / (independent_trials * math.e))
    return sharpe_std * ((1.0 - euler_gamma) * first + euler_gamma * second)


def deflated_sharpe_probability(
    returns: Sequence[float],
    *,
    independent_trials: int,
    trial_sharpe_std: float,
    annualization_factor: float = 1.0,
) -> dict[str, float]:
    benchmark = expected_maximum_sharpe(
        independent_trials=independent_trials,
        sharpe_std=trial_sharpe_std,
    )
    probability = probabilistic_sharpe_ratio(
        returns,
        benchmark_sharpe=benchmark,
        annualization_factor=annualization_factor,
    )
    mean, std, _, _ = _moments(returns)
    observed = mean / std * math.sqrt(annualization_factor)
    return {
        "observed_sharpe": observed,
        "deflated_benchmark_sharpe": benchmark,
        "deflated_sharpe_probability": probability,
    }


@dataclass(frozen=True)
class PBOResult:
    combinations: int
    overfit_combinations: int
    probability_backtest_overfitting: float
    logit_values: tuple[float, ...]


def probability_of_backtest_overfitting(
    performance_by_slice: Sequence[Sequence[float]],
) -> PBOResult:
    if len(performance_by_slice) < 4 or len(performance_by_slice) % 2:
        raise ValueError("pbo_requires_even_number_of_at_least_four_slices")
    strategy_count = len(performance_by_slice[0])
    if strategy_count < 2:
        raise ValueError("pbo_requires_multiple_strategies")
    if any(len(row) != strategy_count for row in performance_by_slice):
        raise ValueError("pbo_slice_width_mismatch")
    if any(not math.isfinite(value) for row in performance_by_slice for value in row):
        raise ValueError("pbo_values_not_finite")
    slice_count = len(performance_by_slice)
    train_size = slice_count // 2
    logits: list[float] = []
    overfit = 0
    combinations = 0
    all_indices = set(range(slice_count))
    for train_indices_tuple in itertools.combinations(range(slice_count), train_size):
        train_indices = set(train_indices_tuple)
        validation_indices = sorted(all_indices - train_indices)
        train_means = [
            sum(performance_by_slice[index][strategy] for index in train_indices) / train_size
            for strategy in range(strategy_count)
        ]
        selected = max(range(strategy_count), key=lambda strategy: (train_means[strategy], -strategy))
        validation_means = [
            sum(performance_by_slice[index][strategy] for index in validation_indices) / train_size
            for strategy in range(strategy_count)
        ]
        ranked = sorted(range(strategy_count), key=lambda strategy: (validation_means[strategy], strategy))
        rank = ranked.index(selected) + 1
        relative_rank = (rank - 0.5) / strategy_count
        logit = math.log(relative_rank / (1.0 - relative_rank))
        logits.append(logit)
        combinations += 1
        if logit <= 0:
            overfit += 1
    return PBOResult(
        combinations=combinations,
        overfit_combinations=overfit,
        probability_backtest_overfitting=overfit / combinations,
        logit_values=tuple(logits),
    )
