from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION, PredictionStatus
from .dataset import safe_float, text


def population_stability_index(
    reference: Sequence[float],
    current: Sequence[float],
    *,
    bins: int = 10,
) -> float | None:
    ref = np.asarray([value for value in reference if safe_float(value) is not None], dtype=float)
    cur = np.asarray([value for value in current if safe_float(value) is not None], dtype=float)
    if len(ref) < 20 or len(cur) < 20:
        return None
    quantiles = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(quantiles) < 3:
        return 0.0
    quantiles[0], quantiles[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(ref, bins=quantiles)
    cur_counts, _ = np.histogram(cur, bins=quantiles)
    ref_pct = np.clip(ref_counts / max(1, ref_counts.sum()), 1e-6, None)
    cur_pct = np.clip(cur_counts / max(1, cur_counts.sum()), 1e-6, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    features: Sequence[str] | None = None,
) -> dict[str, Any]:
    selected = list(features or sorted(set(reference.columns).intersection(current.columns)))
    feature_psi: dict[str, float | None] = {}
    for name in selected:
        if not pd.api.types.is_numeric_dtype(reference[name]) or not pd.api.types.is_numeric_dtype(current[name]):
            continue
        feature_psi[name] = population_stability_index(reference[name].dropna(), current[name].dropna())
    valid = [value for value in feature_psi.values() if value is not None]
    max_psi = max(valid) if valid else None
    status = "STABLE"
    if max_psi is not None and max_psi >= 0.25:
        status = "QUARANTINE_REQUIRED"
    elif max_psi is not None and max_psi >= 0.10:
        status = "DEGRADED"
    return {"schema_version": SCHEMA_VERSION, "status": status, "max_psi": max_psi, "feature_psi": feature_psi, **SAFETY_CONTRACT}


def counterfactual_shadow_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    buckets = {
        "ACTUAL_ACCEPT_ML_ACCEPT": [],
        "ACTUAL_ACCEPT_ML_REJECT": [],
        "ACTUAL_REJECT_ML_ACCEPT": [],
        "ACTUAL_REJECT_ML_REJECT": [],
        "UNRESOLVED": [],
    }
    for row in rows:
        actual = text(row.get("actual_decision")).upper()
        ml_status = text(row.get("ml_status")).upper()
        outcome_r = safe_float(row.get("future_net_r"))
        resolved_statuses = {PredictionStatus.VALID.value, PredictionStatus.BELOW_VALUE_THRESHOLD.value}
        if actual not in {"ACCEPT", "REJECT"} or ml_status not in resolved_statuses or outcome_r is None:
            buckets["UNRESOLVED"].append(row)
            continue
        ml_accept = ml_status == PredictionStatus.VALID.value
        buckets[f"ACTUAL_{actual}_ML_{'ACCEPT' if ml_accept else 'REJECT'}"].append(row)

    summary: dict[str, Any] = {}
    for key, bucket in buckets.items():
        numeric = [safe_float(item.get("future_net_r")) for item in bucket]
        values = [value for value in numeric if value is not None]
        summary[key] = {
            "rows": len(bucket),
            "mean_future_net_r": float(np.mean(values)) if values else None,
            "total_future_net_r": float(np.sum(values)) if values else None,
        }
    return {"schema_version": SCHEMA_VERSION, "summary": summary, **SAFETY_CONTRACT}
