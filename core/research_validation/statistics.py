from __future__ import annotations

import itertools
import math
from statistics import NormalDist
from typing import Iterable, Sequence

import numpy as np

_NORMAL = NormalDist()
_EULER_GAMMA = 0.5772156649015329
_EPS = 1e-12


def _finite_1d(values: Iterable[float], *, min_size: int = 2) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    if arr.ndim != 1:
        raise ValueError("expected a one-dimensional series")
    if arr.size < min_size:
        raise ValueError(f"at least {min_size} observations are required")
    if not np.isfinite(arr).all():
        raise ValueError("all observations must be finite")
    return arr


def sample_sharpe(returns: Iterable[float]) -> float:
    """Per-period sample Sharpe ratio with ddof=1 and zero risk-free rate."""
    x = _finite_1d(returns)
    sd = float(np.std(x, ddof=1))
    if sd <= _EPS:
        raise ValueError("Sharpe ratio is undefined for zero-variance returns")
    return float(np.mean(x) / sd)


def _skew_kurtosis(x: np.ndarray) -> tuple[float, float]:
    centered = x - np.mean(x)
    m2 = float(np.mean(centered**2))
    if m2 <= _EPS:
        raise ValueError("moments are undefined for zero-variance returns")
    m3 = float(np.mean(centered**3))
    m4 = float(np.mean(centered**4))
    return m3 / (m2 ** 1.5), m4 / (m2 * m2)


def _effective_sample_size(x: np.ndarray, max_lag: int | None = None) -> float:
    """Conservative Bartlett-style effective sample size for serial dependence."""
    n = x.size
    if n < 3:
        return float(n)
    if max_lag is None:
        max_lag = max(1, min(n - 1, int(round(n ** (1 / 3)))))
    if max_lag < 0:
        raise ValueError("max_lag must be non-negative")
    centered = x - np.mean(x)
    denom = float(np.dot(centered, centered))
    if denom <= _EPS:
        return float(n)
    inflation = 1.0
    for lag in range(1, min(max_lag, n - 1) + 1):
        rho = float(np.dot(centered[:-lag], centered[lag:]) / denom)
        weight = 1.0 - lag / (max_lag + 1.0)
        inflation += 2.0 * weight * rho
    inflation = max(inflation, 1.0 / n)
    return float(min(n, max(2.0, n / inflation)))


def probabilistic_sharpe_ratio(
    returns: Iterable[float],
    *,
    benchmark_sharpe: float = 0.0,
    max_lag: int | None = None,
) -> float:
    """Probability that true Sharpe exceeds benchmark.

    Uses the Bailey/Lo-style skew/kurtosis Sharpe variance with a conservative
    effective-sample-size adjustment for serial dependence.
    """
    x = _finite_1d(returns, min_size=3)
    sr = sample_sharpe(x)
    skew, kurt = _skew_kurtosis(x)
    n_eff = _effective_sample_size(x, max_lag=max_lag)
    variance_term = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if variance_term <= 0.0:
        raise ValueError("estimated Sharpe variance is non-positive")
    se = math.sqrt(variance_term / max(n_eff - 1.0, 1.0))
    z = (sr - benchmark_sharpe) / se
    return float(_NORMAL.cdf(z))


def minimum_track_record_length(
    returns: Iterable[float],
    *,
    benchmark_sharpe: float = 0.0,
    confidence: float = 0.95,
) -> int:
    """Approximate minimum number of independent observations for Sharpe significance."""
    if not 0.5 < confidence < 1.0:
        raise ValueError("confidence must be between 0.5 and 1")
    x = _finite_1d(returns, min_size=3)
    sr = sample_sharpe(x)
    delta = sr - benchmark_sharpe
    if delta <= 0.0:
        return math.inf
    skew, kurt = _skew_kurtosis(x)
    variance_term = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if variance_term <= 0.0:
        raise ValueError("estimated Sharpe variance is non-positive")
    z = _NORMAL.inv_cdf(confidence)
    return int(math.ceil(1.0 + variance_term * (z / delta) ** 2))


def effective_rank(correlation_matrix: Sequence[Sequence[float]]) -> float:
    """Entropy/eigenvalue effective rank of a correlation matrix."""
    matrix = np.asarray(correlation_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        raise ValueError("correlation_matrix must be non-empty and square")
    if not np.isfinite(matrix).all():
        raise ValueError("correlation_matrix must be finite")
    if not np.allclose(matrix, matrix.T, atol=1e-10):
        raise ValueError("correlation_matrix must be symmetric")
    if not np.allclose(np.diag(matrix), 1.0, atol=1e-8):
        raise ValueError("correlation_matrix diagonal must be one")
    eig = np.linalg.eigvalsh(matrix)
    if float(np.min(eig)) < -1e-8:
        raise ValueError("correlation_matrix must be positive semidefinite")
    eig = np.clip(eig, 0.0, None)
    total = float(np.sum(eig))
    if total <= _EPS:
        raise ValueError("correlation_matrix has zero spectral mass")
    p = eig[eig > _EPS] / total
    entropy = -float(np.sum(p * np.log(p)))
    return float(math.exp(entropy))


def _expected_max_standard_normal(n_eff: float) -> float:
    if n_eff <= 1.0 + _EPS:
        return 0.0
    p1 = min(1.0 - _EPS, max(_EPS, 1.0 - 1.0 / n_eff))
    p2 = min(1.0 - _EPS, max(_EPS, 1.0 - 1.0 / (n_eff * math.e)))
    return (1.0 - _EULER_GAMMA) * _NORMAL.inv_cdf(p1) + _EULER_GAMMA * _NORMAL.inv_cdf(p2)


def deflated_sharpe_ratio(
    selected_returns: Iterable[float],
    trial_sharpes: Iterable[float],
    *,
    effective_trials: float | None = None,
    max_lag: int | None = None,
) -> float:
    """PSR of the selected strategy against the expected maximum searched Sharpe."""
    trials = _finite_1d(trial_sharpes, min_size=2)
    if effective_trials is None:
        effective_trials = float(trials.size)
    if not math.isfinite(effective_trials) or effective_trials < 1.0:
        raise ValueError("effective_trials must be finite and >= 1")
    effective_trials = min(float(trials.size), effective_trials)
    trial_sd = float(np.std(trials, ddof=1))
    benchmark = float(np.mean(trials)) + trial_sd * _expected_max_standard_normal(effective_trials)
    return probabilistic_sharpe_ratio(
        selected_returns,
        benchmark_sharpe=benchmark,
        max_lag=max_lag,
    )


def bonferroni_rejections(p_values: Iterable[float], *, alpha: float = 0.05) -> list[bool]:
    p = _finite_p_values(p_values)
    threshold = alpha / len(p)
    return [value <= threshold for value in p]


def benjamini_hochberg(p_values: Iterable[float], *, q: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg step-up FDR decisions in original order."""
    p = _finite_p_values(p_values)
    if not 0.0 < q < 1.0:
        raise ValueError("q must be between 0 and 1")
    order = sorted(range(len(p)), key=p.__getitem__)
    cutoff_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p[idx] <= q * rank / len(p):
            cutoff_rank = rank
    rejected = [False] * len(p)
    if cutoff_rank:
        cutoff = p[order[cutoff_rank - 1]]
        rejected = [value <= cutoff for value in p]
    return rejected


def _finite_p_values(p_values: Iterable[float]) -> list[float]:
    p = [float(v) for v in p_values]
    if not p:
        raise ValueError("at least one p-value is required")
    if any((not math.isfinite(v)) or v < 0.0 or v > 1.0 for v in p):
        raise ValueError("p-values must be finite and within [0, 1]")
    return p


def _column_sharpes(matrix: np.ndarray) -> np.ndarray:
    means = np.mean(matrix, axis=0)
    sds = np.std(matrix, axis=0, ddof=1)
    return np.divide(means, sds, out=np.full_like(means, -np.inf), where=sds > _EPS)


def cscv_probability_of_backtest_overfitting(
    strategy_returns: Sequence[Sequence[float]],
    *,
    blocks: int = 8,
) -> float:
    """Combinatorially Symmetric Cross-Validation estimate of PBO.

    Rows are chronological observations and columns are strategy/configuration returns.
    The sample is split into an even number of contiguous blocks. For each symmetric
    train/test combination the in-sample winner is ranked out-of-sample; PBO is the
    fraction of winner ranks falling in the lower half OOS.
    """
    matrix = np.asarray(strategy_returns, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 4 or matrix.shape[1] < 2:
        raise ValueError("strategy_returns must be a 2D matrix with >=4 rows and >=2 strategies")
    if not np.isfinite(matrix).all():
        raise ValueError("strategy_returns must be finite")
    if blocks < 4 or blocks % 2:
        raise ValueError("blocks must be an even integer >= 4")
    if matrix.shape[0] < blocks * 2:
        raise ValueError("need at least two observations per block")

    index_blocks = [idx for idx in np.array_split(np.arange(matrix.shape[0]), blocks) if idx.size]
    half = blocks // 2
    lower_half_count = 0
    comparisons = 0
    for train_blocks in itertools.combinations(range(blocks), half):
        train_set = set(train_blocks)
        # Count each complementary partition once.
        if 0 not in train_set:
            continue
        test_blocks = [i for i in range(blocks) if i not in train_set]
        train_idx = np.concatenate([index_blocks[i] for i in train_blocks])
        test_idx = np.concatenate([index_blocks[i] for i in test_blocks])
        train_scores = _column_sharpes(matrix[train_idx, :])
        winner = int(np.argmax(train_scores))
        test_scores = _column_sharpes(matrix[test_idx, :])
        winner_score = test_scores[winner]
        # rank=1 is worst, rank=n_strategies is best. Ties receive conservative lower rank.
        rank = 1 + int(np.sum(test_scores < winner_score))
        omega = rank / (matrix.shape[1] + 1.0)
        if omega <= 0.5:
            lower_half_count += 1
        comparisons += 1

    if comparisons == 0:
        raise ValueError("no CSCV comparisons were generated")
    return lower_half_count / comparisons
