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


def _finite_scalar(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def sample_sharpe(returns: Iterable[float]) -> float:
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
    m3 = float(np.mean(centered**3)); m4 = float(np.mean(centered**4))
    return m3 / (m2 ** 1.5), m4 / (m2 * m2)


def _effective_sample_size(x: np.ndarray, max_lag: int | None = None) -> float:
    n = x.size
    if max_lag is not None and (type(max_lag) is not int or max_lag < 0):
        raise ValueError("max_lag must be a non-negative integer")
    if n < 3: return float(n)
    if max_lag is None: max_lag = max(1, min(n - 1, int(round(n ** (1 / 3)))))
    centered = x - np.mean(x); denom = float(np.dot(centered, centered))
    if denom <= _EPS: return float(n)
    inflation = 1.0
    for lag in range(1, min(max_lag, n - 1) + 1):
        rho = float(np.dot(centered[:-lag], centered[lag:]) / denom)
        inflation += 2.0 * (1.0 - lag / (max_lag + 1.0)) * rho
    inflation = max(inflation, 1.0 / n)
    return float(min(n, max(2.0, n / inflation)))


def probabilistic_sharpe_ratio(returns: Iterable[float], *, benchmark_sharpe: float = 0.0, max_lag: int | None = None) -> float:
    benchmark = _finite_scalar(benchmark_sharpe, "benchmark_sharpe")
    x = _finite_1d(returns, min_size=3); sr = sample_sharpe(x); skew, kurt = _skew_kurtosis(x)
    n_eff = _effective_sample_size(x, max_lag=max_lag)
    variance_term = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if variance_term <= 0.0 or not math.isfinite(variance_term): raise ValueError("estimated Sharpe variance is non-positive or non-finite")
    return float(_NORMAL.cdf((sr - benchmark) / math.sqrt(variance_term / max(n_eff - 1.0, 1.0))))


def minimum_track_record_length(returns: Iterable[float], *, benchmark_sharpe: float = 0.0, confidence: float = 0.95) -> int:
    benchmark = _finite_scalar(benchmark_sharpe, "benchmark_sharpe"); confidence = _finite_scalar(confidence, "confidence")
    if not 0.5 < confidence < 1.0: raise ValueError("confidence must be between 0.5 and 1")
    x = _finite_1d(returns, min_size=3); sr = sample_sharpe(x); delta = sr - benchmark
    if delta <= 0.0: return math.inf
    skew, kurt = _skew_kurtosis(x); variance_term = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if variance_term <= 0.0 or not math.isfinite(variance_term): raise ValueError("estimated Sharpe variance is non-positive or non-finite")
    return int(math.ceil(1.0 + variance_term * (_NORMAL.inv_cdf(confidence) / delta) ** 2))


def effective_rank(correlation_matrix: Sequence[Sequence[float]]) -> float:
    matrix = np.asarray(correlation_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0: raise ValueError("correlation_matrix must be non-empty and square")
    if not np.isfinite(matrix).all(): raise ValueError("correlation_matrix must be finite")
    if np.any(np.abs(matrix) > 1.0 + 1e-8): raise ValueError("correlation entries must be within [-1, 1]")
    if not np.allclose(matrix, matrix.T, atol=1e-10): raise ValueError("correlation_matrix must be symmetric")
    if not np.allclose(np.diag(matrix), 1.0, atol=1e-8): raise ValueError("correlation_matrix diagonal must be one")
    eig = np.linalg.eigvalsh(matrix)
    if float(np.min(eig)) < -1e-8: raise ValueError("correlation_matrix must be positive semidefinite")
    eig = np.clip(eig, 0.0, None); p = eig[eig > _EPS] / float(np.sum(eig))
    return float(math.exp(-float(np.sum(p * np.log(p)))))


def _expected_max_standard_normal(n_eff: float) -> float:
    if n_eff <= 1.0 + _EPS: return 0.0
    p1 = min(1.0 - _EPS, max(_EPS, 1.0 - 1.0 / n_eff)); p2 = min(1.0 - _EPS, max(_EPS, 1.0 - 1.0 / (n_eff * math.e)))
    return (1.0 - _EULER_GAMMA) * _NORMAL.inv_cdf(p1) + _EULER_GAMMA * _NORMAL.inv_cdf(p2)


def deflated_sharpe_ratio(selected_returns: Iterable[float], trial_sharpes: Iterable[float], *, effective_trials: float | None = None, max_lag: int | None = None) -> float:
    """Bailey-Lopez de Prado DSR using SR0=sqrt(Var(trial SRs))*E[max Z]."""
    trials = _finite_1d(trial_sharpes, min_size=2)
    if effective_trials is None: effective_trials = float(trials.size)
    effective_trials = _finite_scalar(effective_trials, "effective_trials")
    if effective_trials < 1.0 or effective_trials > trials.size: raise ValueError("effective_trials must be within [1, raw trial count]")
    trial_sd = float(np.std(trials, ddof=1))
    if trial_sd <= _EPS: raise ValueError("trial Sharpe distribution must have non-zero variance")
    benchmark = trial_sd * _expected_max_standard_normal(effective_trials)
    return probabilistic_sharpe_ratio(selected_returns, benchmark_sharpe=benchmark, max_lag=max_lag)


def bonferroni_rejections(p_values: Iterable[float], *, alpha: float = 0.05) -> list[bool]:
    alpha = _finite_scalar(alpha, "alpha")
    if not 0.0 < alpha < 1.0: raise ValueError("alpha must be between 0 and 1")
    p = _finite_p_values(p_values); threshold = alpha / len(p)
    return [value <= threshold for value in p]


def benjamini_hochberg(p_values: Iterable[float], *, q: float = 0.05) -> list[bool]:
    q = _finite_scalar(q, "q")
    if not 0.0 < q < 1.0: raise ValueError("q must be between 0 and 1")
    p = _finite_p_values(p_values); order = sorted(range(len(p)), key=p.__getitem__); cutoff_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p[idx] <= q * rank / len(p): cutoff_rank = rank
    if not cutoff_rank: return [False] * len(p)
    cutoff = p[order[cutoff_rank - 1]]
    return [value <= cutoff for value in p]


def _finite_p_values(p_values: Iterable[float]) -> list[float]:
    raw = list(p_values)
    if not raw: raise ValueError("at least one p-value is required")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in raw): raise ValueError("p-values must be real numbers, not booleans or strings")
    p = [float(v) for v in raw]
    if any((not math.isfinite(v)) or v < 0.0 or v > 1.0 for v in p): raise ValueError("p-values must be finite and within [0, 1]")
    return p


def _column_sharpes(matrix: np.ndarray) -> np.ndarray:
    means = np.mean(matrix, axis=0); sds = np.std(matrix, axis=0, ddof=1)
    return np.divide(means, sds, out=np.full_like(means, np.nan), where=sds > _EPS)


def _average_rank_ascending(values: np.ndarray, selected_index: int) -> float:
    selected = values[selected_index]
    less = int(np.sum(values < selected)); equal = int(np.sum(values == selected))
    return less + (equal + 1.0) / 2.0


def cscv_probability_of_backtest_overfitting(strategy_returns: Sequence[Sequence[float]], *, blocks: int = 8) -> float:
    """Published CSCV/PBO structure: evaluate every S choose S/2 symmetric combination."""
    matrix = np.asarray(strategy_returns, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 4 or matrix.shape[1] < 2: raise ValueError("strategy_returns must be a 2D matrix with >=4 rows and >=2 strategies")
    if not np.isfinite(matrix).all(): raise ValueError("strategy_returns must be finite")
    if type(blocks) is not int or blocks < 4 or blocks % 2: raise ValueError("blocks must be an even integer >= 4")
    if matrix.shape[0] % blocks != 0: raise ValueError("CSCV requires equal-sized contiguous blocks")
    if matrix.shape[0] < blocks * 2: raise ValueError("need at least two observations per block")
    index_blocks = np.split(np.arange(matrix.shape[0]), blocks); half = blocks // 2; lower_half_count = comparisons = 0
    for train_blocks in itertools.combinations(range(blocks), half):
        train_set = set(train_blocks); test_blocks = [i for i in range(blocks) if i not in train_set]
        train_idx = np.concatenate([index_blocks[i] for i in train_blocks]); test_idx = np.concatenate([index_blocks[i] for i in test_blocks])
        train_scores = _column_sharpes(matrix[train_idx, :]); test_scores = _column_sharpes(matrix[test_idx, :])
        if not np.isfinite(train_scores).all() or not np.isfinite(test_scores).all(): raise ValueError("all strategy performance statistics must be defined in every CSCV split")
        winner = int(np.argmax(train_scores)); rank = _average_rank_ascending(test_scores, winner)
        omega = rank / (matrix.shape[1] + 1.0)
        if omega <= 0.5: lower_half_count += 1
        comparisons += 1
    if comparisons != math.comb(blocks, half): raise RuntimeError("incomplete CSCV combination enumeration")
    return lower_half_count / comparisons
