# Threshold Estimator Contract

## Specification
* **Identifier**: `REGIME_CONDITIONED_OPENING_STATE_MOMENTUM_V1`
* **Canonical Percentile**: `80`
* **Interpolation Mode**: `linear` (using `numpy.percentile` standard linear method).
* **Minimum Prior History**: `60` sessions.

## Constraints
* No holdout sessions may enter the estimation.
* No future sessions may enter the estimation (strictly chronological/causal).
* Insufficient history returns `INSUFFICIENT_PRIOR_HISTORY`.
