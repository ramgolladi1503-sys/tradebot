from __future__ import annotations

import math
from statistics import NormalDist
from typing import Iterable

import numpy as np

_NORMAL = NormalDist()
_EULER_GAMMA = 0.5772156649015329


def _require_finite(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name}_must_be_finite")
    return value


def _require_probability(name: str, value: float, *, open_interval: bool = False) -> float:
    value = _require_finite(name, value)
    if open_interval:
        valid = 0.0 < value < 1.0
    else:
        valid = 0.0 <= value <= 1.0
    if not valid:
        raise ValueError(f"{name}_must_be_probability")
    return value


def _normal_cdf(x: float) -> float:
    return _NORMAL.cdf(float(x))


def _normal_ppf(p: float) -> float:
    p = _require_probability("p", p, open_interval=True)
    return _NORMAL.inv_cdf(p)


def sharpe_ratio_variance(
    sharpe: float,
    observations: int,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    autocorrelation: float = 0.0,
) -> float:
    """Generalized asymptotic variance of a Sharpe-ratio estimator.

    ``kurtosis`` is non-excess kurtosis (Gaussian == 3). ``autocorrelation``
    is the lag-1 AR(1)-style correlation used in the 2026 Sharpe framework.
    The function intentionally models a *single* trial; search adjustment is
    handled separately rather than silently mixing selection and sampling risk.
    """
    sr = _require_finite("sharpe", sharpe)
    g3 = _require_finite("skewness", skewness)
    g4 = _require_finite("kurtosis", kurtosis)
    rho = _require_finite("autocorrelation", autocorrelation)
    if observations <= 1:
        raise ValueError("observations_must_exceed_one")
    if g4 < 1.0:
        raise ValueError("kurtosis_below_mathematical_minimum")
    if not -1.0 < rho < 1.0:
        raise ValueError("autocorrelation_must_be_inside_unit_interval")

    a = 1.0 + 2.0 * rho / (1.0 - rho)
    b = 1.0 + rho / (1.0 - rho) + rho * rho / (1.0 - rho * rho)
    c = 1.0 + 2.0 * rho * rho / (1.0 - rho * rho)
    variance = (a - b * g3 * sr + c * (g4 - 1.0) * sr * sr / 4.0) / observations
    if not math.isfinite(variance) or variance <= 0.0:
        raise ValueError("sharpe_variance_not_positive")
    return float(variance)


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    benchmark_sharpe: float,
    observations: int,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    autocorrelation: float = 0.0,
) -> float:
    variance = sharpe_ratio_variance(
        benchmark_sharpe,
        observations,
        skewness=skewness,
        kurtosis=kurtosis,
        autocorrelation=autocorrelation,
    )
    z = (
        _require_finite("observed_sharpe", observed_sharpe)
        - _require_finite("benchmark_sharpe", benchmark_sharpe)
    ) / math.sqrt(variance)
    return float(_normal_cdf(z))


def minimum_track_record_length(
    observed_sharpe: float,
    benchmark_sharpe: float,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    autocorrelation: float = 0.0,
    alpha: float = 0.05,
) -> float:
    alpha = _require_probability("alpha", alpha, open_interval=True)
    observed = _require_finite("observed_sharpe", observed_sharpe)
    benchmark = _require_finite("benchmark_sharpe", benchmark_sharpe)
    if observed <= benchmark:
        return math.inf

    rho = _require_finite("autocorrelation", autocorrelation)
    if not -1.0 < rho < 1.0:
        raise ValueError("autocorrelation_must_be_inside_unit_interval")
    g3 = _require_finite("skewness", skewness)
    g4 = _require_finite("kurtosis", kurtosis)
    if g4 < 1.0:
        raise ValueError("kurtosis_below_mathematical_minimum")
    a = 1.0 + 2.0 * rho / (1.0 - rho)
    b = 1.0 + rho / (1.0 - rho) + rho * rho / (1.0 - rho * rho)
    c = 1.0 + 2.0 * rho * rho / (1.0 - rho * rho)
    unit_variance = a - b * g3 * benchmark + c * (g4 - 1.0) * benchmark * benchmark / 4.0
    if unit_variance <= 0.0 or not math.isfinite(unit_variance):
        raise ValueError("sharpe_variance_not_positive")
    z = _normal_ppf(1.0 - alpha)
    return float(unit_variance * (z / (observed - benchmark)) ** 2)


def critical_sharpe_ratio(
    benchmark_sharpe: float,
    observations: int,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    autocorrelation: float = 0.0,
    alpha: float = 0.05,
) -> float:
    alpha = _require_probability("alpha", alpha, open_interval=True)
    variance = sharpe_ratio_variance(
        benchmark_sharpe,
        observations,
        skewness=skewness,
        kurtosis=kurtosis,
        autocorrelation=autocorrelation,
    )
    return float(benchmark_sharpe + _normal_ppf(1.0 - alpha) * math.sqrt(variance))


def sharpe_ratio_power(
    benchmark_sharpe: float,
    alternative_sharpe: float,
    observations: int,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    autocorrelation: float = 0.0,
    alpha: float = 0.05,
) -> float:
    benchmark = _require_finite("benchmark_sharpe", benchmark_sharpe)
    alternative = _require_finite("alternative_sharpe", alternative_sharpe)
    if alternative <= benchmark:
        raise ValueError("alternative_sharpe_must_exceed_benchmark")
    critical = critical_sharpe_ratio(
        benchmark,
        observations,
        skewness=skewness,
        kurtosis=kurtosis,
        autocorrelation=autocorrelation,
        alpha=alpha,
    )
    variance_alt = sharpe_ratio_variance(
        alternative,
        observations,
        skewness=skewness,
        kurtosis=kurtosis,
        autocorrelation=autocorrelation,
    )
    beta = _normal_cdf((critical - alternative) / math.sqrt(variance_alt))
    return float(1.0 - beta)


def effective_rank(correlation_matrix: np.ndarray, *, eigenvalue_tolerance: float = 1e-12) -> float:
    matrix = np.asarray(correlation_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        raise ValueError("correlation_matrix_must_be_nonempty_square")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("correlation_matrix_must_be_finite")
    if not np.allclose(matrix, matrix.T, atol=1e-10):
        raise ValueError("correlation_matrix_must_be_symmetric")
    if not np.allclose(np.diag(matrix), 1.0, atol=1e-8):
        raise ValueError("correlation_matrix_diagonal_must_be_one")

    eigenvalues = np.linalg.eigvalsh(matrix)
    if np.min(eigenvalues) < -1e-8:
        raise ValueError("correlation_matrix_not_positive_semidefinite")
    positive = eigenvalues[eigenvalues > eigenvalue_tolerance]
    if positive.size == 0:
        raise ValueError("correlation_matrix_has_no_positive_spectrum")
    probabilities = positive / positive.sum()
    entropy = -float(np.sum(probabilities * np.log(probabilities)))
    return float(math.exp(entropy))


def effective_trials_from_returns(candidate_returns: np.ndarray) -> float:
    returns = np.asarray(candidate_returns, dtype=float)
    if returns.ndim != 2 or returns.shape[0] < 3 or returns.shape[1] < 1:
        raise ValueError("candidate_returns_must_be_observations_by_trials")
    if not np.all(np.isfinite(returns)):
        raise ValueError("candidate_returns_must_be_finite")
    if returns.shape[1] == 1:
        return 1.0
    std = returns.std(axis=0, ddof=1)
    if np.any(std <= 0.0):
        raise ValueError("candidate_return_series_must_have_variance")
    corr = np.corrcoef(returns, rowvar=False)
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1.0, 1.0)
    return effective_rank(corr)


def expected_maximum_sharpe_ratio(
    effective_trials: float,
    sharpe_variance_across_trials: float,
    *,
    benchmark_sharpe: float = 0.0,
) -> float:
    k = _require_finite("effective_trials", effective_trials)
    variance = _require_finite("sharpe_variance_across_trials", sharpe_variance_across_trials)
    benchmark = _require_finite("benchmark_sharpe", benchmark_sharpe)
    if k < 1.0:
        raise ValueError("effective_trials_must_be_at_least_one")
    if variance < 0.0:
        raise ValueError("sharpe_variance_across_trials_must_be_nonnegative")
    if k <= 1.0 + 1e-12 or variance == 0.0:
        return benchmark

    p1 = 1.0 - 1.0 / k
    p2 = 1.0 - 1.0 / (k * math.e)
    expected_standard_max = (
        (1.0 - _EULER_GAMMA) * _normal_ppf(p1)
        + _EULER_GAMMA * _normal_ppf(p2)
    )
    return float(benchmark + math.sqrt(variance) * expected_standard_max)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    observations: int,
    *,
    effective_trials: float,
    sharpe_variance_across_trials: float,
    benchmark_sharpe: float = 0.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    autocorrelation: float = 0.0,
) -> tuple[float, float]:
    adjusted_benchmark = expected_maximum_sharpe_ratio(
        effective_trials,
        sharpe_variance_across_trials,
        benchmark_sharpe=benchmark_sharpe,
    )
    dsr = probabilistic_sharpe_ratio(
        observed_sharpe,
        adjusted_benchmark,
        observations,
        skewness=skewness,
        kurtosis=kurtosis,
        autocorrelation=autocorrelation,
    )
    return float(dsr), float(adjusted_benchmark)


def _pvalues(values: Iterable[float]) -> np.ndarray:
    p = np.asarray(list(values), dtype=float)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("p_values_must_be_nonempty_vector")
    if not np.all(np.isfinite(p)) or np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("p_values_must_be_probabilities")
    return p


def adjust_pvalues_bonferroni(values: Iterable[float]) -> np.ndarray:
    p = _pvalues(values)
    return np.minimum(1.0, p * p.size)


def adjust_pvalues_sidak(values: Iterable[float]) -> np.ndarray:
    p = _pvalues(values)
    return 1.0 - np.power(1.0 - p, p.size)


def adjust_pvalues_holm(values: Iterable[float]) -> np.ndarray:
    p = _pvalues(values)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    m = p.size
    for rank, index in enumerate(order):
        candidate = min(1.0, (m - rank) * p[index])
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def adjust_pvalues_benjamini_hochberg(values: Iterable[float]) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted p-values."""
    p = _pvalues(values)
    order = np.argsort(p)
    ranked = p[order]
    m = p.size
    raw = ranked * m / np.arange(1, m + 1, dtype=float)
    adjusted_ranked = np.minimum.accumulate(raw[::-1])[::-1]
    adjusted_ranked = np.clip(adjusted_ranked, 0.0, 1.0)
    adjusted = np.empty_like(p)
    adjusted[order] = adjusted_ranked
    return adjusted


def adjust_pvalues_benjamini_yekutieli(values: Iterable[float]) -> np.ndarray:
    """Dependence-robust Benjamini-Yekutieli FDR-adjusted p-values."""
    p = _pvalues(values)
    harmonic = float(np.sum(1.0 / np.arange(1, p.size + 1, dtype=float)))
    order = np.argsort(p)
    ranked = p[order]
    raw = ranked * p.size * harmonic / np.arange(1, p.size + 1, dtype=float)
    adjusted_ranked = np.minimum.accumulate(raw[::-1])[::-1]
    adjusted_ranked = np.clip(adjusted_ranked, 0.0, 1.0)
    adjusted = np.empty_like(p)
    adjusted[order] = adjusted_ranked
    return adjusted


def one_sided_pvalue_from_psr(psr: float) -> float:
    psr = _require_probability("psr", psr)
    return float(1.0 - psr)
