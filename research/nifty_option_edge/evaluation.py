from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .contracts import CLAIM_BOUNDARY_UNDERLYING


def evaluate_direction_magnitude_forecasts(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    horizon_minutes: int,
    min_probability_direction: float = 0.55,
    min_abs_expected_move_points: float = 10.0,
) -> dict[str, object]:
    """Evaluate causal NIFTY forecasts against forward-move labels.

    Required prediction columns are ``decision_timestamp``, ``probability_up`` and
    ``expected_signed_points``. Evaluation is timestamp-joined and restricted to
    measured labels for the requested horizon.
    """

    required_predictions = {
        "decision_timestamp",
        "probability_up",
        "expected_signed_points",
    }
    missing_predictions = required_predictions.difference(predictions.columns)
    if missing_predictions:
        raise ValueError(
            f"prediction columns missing: {sorted(missing_predictions)}"
        )

    prefix = f"fwd_{int(horizon_minutes)}m"
    required_labels = {
        "decision_timestamp",
        f"{prefix}_status",
        f"{prefix}_signed_points",
    }
    missing_labels = required_labels.difference(labels.columns)
    if missing_labels:
        raise ValueError(f"label columns missing: {sorted(missing_labels)}")

    pred = predictions.copy()
    lab = labels.copy()
    pred["decision_timestamp"] = pd.to_datetime(
        pred["decision_timestamp"], utc=True, errors="raise"
    )
    lab["decision_timestamp"] = pd.to_datetime(
        lab["decision_timestamp"], utc=True, errors="raise"
    )
    if pred["decision_timestamp"].duplicated().any():
        raise ValueError("prediction decision_timestamp must be unique")
    if lab["decision_timestamp"].duplicated().any():
        raise ValueError("label decision_timestamp must be unique")

    merged = pred.merge(
        lab[
            [
                "decision_timestamp",
                f"{prefix}_status",
                f"{prefix}_signed_points",
            ]
        ],
        on="decision_timestamp",
        how="inner",
        validate="one_to_one",
    )
    merged = merged.loc[merged[f"{prefix}_status"] == "MEASURED"].copy()
    if merged.empty:
        raise ValueError("no measured timestamp overlap")

    probability_up = pd.to_numeric(merged["probability_up"], errors="raise")
    expected = pd.to_numeric(merged["expected_signed_points"], errors="raise")
    actual = pd.to_numeric(merged[f"{prefix}_signed_points"], errors="raise")
    numeric = np.column_stack([probability_up, expected, actual])
    if not np.isfinite(numeric).all():
        raise ValueError("forecast evaluation values must be finite")
    if ((probability_up < 0.0) | (probability_up > 1.0)).any():
        raise ValueError("probability_up must be in [0, 1]")

    actual_up = (actual > 0).astype(float)
    predicted_up = probability_up >= 0.5
    predicted_sign = np.where(predicted_up, 1.0, -1.0)
    actual_sign = np.where(actual > 0, 1.0, np.where(actual < 0, -1.0, 0.0))
    directional_correct = predicted_sign == actual_sign

    probability_direction = np.where(predicted_up, probability_up, 1.0 - probability_up)
    selective = (
        (probability_direction >= float(min_probability_direction))
        & (np.abs(expected) >= float(min_abs_expected_move_points))
    )
    aligned_realized = actual.to_numpy(dtype=float) * predicted_sign

    error = expected.to_numpy(dtype=float) - actual.to_numpy(dtype=float)
    metrics: dict[str, object] = {
        "claim_boundary": CLAIM_BOUNDARY_UNDERLYING,
        "horizon_minutes": int(horizon_minutes),
        "rows": int(len(merged)),
        "direction_accuracy": float(np.mean(directional_correct)),
        "brier_score_up": float(np.mean((probability_up.to_numpy(dtype=float) - actual_up.to_numpy(dtype=float)) ** 2)),
        "magnitude_mae_points": float(np.mean(np.abs(error))),
        "magnitude_rmse_points": float(math.sqrt(np.mean(error**2))),
        "mean_actual_signed_points": float(np.mean(actual)),
        "mean_abs_actual_points": float(np.mean(np.abs(actual))),
        "selective_rows": int(np.sum(selective)),
        "selective_rate": float(np.mean(selective)),
        "selection_min_probability_direction": float(min_probability_direction),
        "selection_min_abs_expected_move_points": float(min_abs_expected_move_points),
    }

    if np.any(selective):
        selective_correct = directional_correct[selective]
        selective_aligned = aligned_realized[selective]
        metrics.update(
            {
                "selective_direction_accuracy": float(np.mean(selective_correct)),
                "selective_mean_aligned_realized_points": float(np.mean(selective_aligned)),
                "selective_median_aligned_realized_points": float(np.median(selective_aligned)),
                "selective_positive_aligned_rate": float(np.mean(selective_aligned > 0)),
            }
        )
    else:
        metrics.update(
            {
                "selective_direction_accuracy": None,
                "selective_mean_aligned_realized_points": None,
                "selective_median_aligned_realized_points": None,
                "selective_positive_aligned_rate": None,
            }
        )

    return metrics
