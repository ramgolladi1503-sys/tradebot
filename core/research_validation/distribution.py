from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DistributionDiagnostics:
    observations: int
    mean: float
    standard_deviation: float
    skewness: float
    kurtosis: float
    lag1_autocorrelation: float
    finite: bool
    heavy_tail_warning: bool
    inference_model_status: str


def diagnose_returns(
    returns: np.ndarray,
    *,
    minimum_observations: int = 30,
    kurtosis_warning_threshold: float = 10.0,
) -> DistributionDiagnostics:
    """Compute descriptive diagnostics without claiming population moments exist.

    A finite historical sample cannot prove that a population fourth moment is
    finite. Extreme sample kurtosis therefore produces a review requirement,
    not a false claim that heavy-tail Sharpe asymptotics are valid or invalid.
    """
    values = np.asarray(returns, dtype=float).reshape(-1)
    finite = bool(values.size and np.all(np.isfinite(values)))
    if not finite:
        return DistributionDiagnostics(
            observations=int(values.size),
            mean=float("nan"),
            standard_deviation=float("nan"),
            skewness=float("nan"),
            kurtosis=float("nan"),
            lag1_autocorrelation=float("nan"),
            finite=False,
            heavy_tail_warning=True,
            inference_model_status="INFERENCE_MODEL_INVALID_NONFINITE_RETURNS",
        )
    if values.size < 2:
        raise ValueError("return_series_too_short")
    mean = float(values.mean())
    centered = values - mean
    std = float(values.std(ddof=1))
    if std <= 0.0:
        raise ValueError("return_series_has_zero_variance")
    m2 = float(np.mean(centered**2))
    m3 = float(np.mean(centered**3))
    m4 = float(np.mean(centered**4))
    skew = m3 / (m2 ** 1.5)
    kurt = m4 / (m2 * m2)
    if values.size >= 3:
        lag1 = float(np.corrcoef(values[:-1], values[1:])[0, 1])
        if not np.isfinite(lag1):
            lag1 = 0.0
    else:
        lag1 = 0.0

    heavy = bool(kurt >= kurtosis_warning_threshold)
    if values.size < minimum_observations:
        status = "INFERENCE_MODEL_UNDER_SAMPLED"
    elif heavy:
        status = "HEAVY_TAIL_REVIEW_REQUIRED"
    else:
        status = "BASIC_MOMENT_DIAGNOSTICS_PASS"
    return DistributionDiagnostics(
        observations=int(values.size),
        mean=mean,
        standard_deviation=std,
        skewness=float(skew),
        kurtosis=float(kurt),
        lag1_autocorrelation=lag1,
        finite=True,
        heavy_tail_warning=heavy,
        inference_model_status=status,
    )
