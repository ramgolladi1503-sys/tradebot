from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .common import INDEX_SYMBOL, MIN_CONSTITUENTS, RANDOM_STATE, digest
from .discovery import FamilyModel, assign_family, fit_family_model, freeze_family_motifs

BATCH_B_FEATURES: dict[str, tuple[str, ...]] = {
    "TAIL_SHAPE_ASYMMETRY": (
        "cross_skew",
        "cross_excess_kurtosis",
        "tail_log_magnitude_ratio",
        "tail_count_imbalance",
        "median_mean_gap_norm",
        "extreme_abs_concentration",
    ),
    "ORDER_STATISTIC_GEOMETRY": (
        "center_iqr_norm",
        "upper_wing_norm",
        "lower_wing_norm",
        "wing_asymmetry",
        "upper_half_span_norm",
        "lower_half_span_norm",
    ),
    "STATE_DURATION_HAZARD": (
        "breadth_sign_run",
        "divergence_sign_run",
        "dispersion_high_run",
        "concentration_high_run",
        "breadth_flip_count6",
        "divergence_flip_count6",
    ),
    "CLOCK_TIME_RESIDUAL": (
        "breadth_clock_resid",
        "dispersion_clock_resid",
        "concentration_clock_resid",
        "divergence_clock_resid",
        "volume_clock_resid",
        "skew_clock_resid",
    ),
    "CROSS_METRIC_PHASE": (
        "breadth_peak_age6",
        "dispersion_peak_age6",
        "concentration_peak_age6",
        "divergence_peak_age6",
        "breadth_dispersion_phase6",
        "divergence_concentration_phase6",
    ),
    "PATH_TOPOLOGY": (
        "breadth_path_efficiency6",
        "dispersion_path_efficiency6",
        "concentration_path_efficiency6",
        "divergence_path_efficiency6",
        "breadth_dispersion_loop_area6",
        "divergence_concentration_loop_area6",
    ),
}

CLOCK_METRICS = {
    "breadth_imbalance": "breadth_clock_resid",
    "dispersion_std": "dispersion_clock_resid",
    "top5_abs_share": "concentration_clock_resid",
    "index_eqw_divergence": "divergence_clock_resid",
    "median_volume_ratio": "volume_clock_resid",
    "cross_skew": "skew_clock_resid",
}


def _distribution_shape(values: np.ndarray) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < MIN_CONSTITUENTS:
        raise ValueError("insufficient cross-sectional values")
    mean = float(np.mean(x))
    median = float(np.median(x))
    std = float(np.std(x, ddof=0))
    scale = max(std, 1e-12)
    centered = x - mean
    m2 = float(np.mean(centered * centered))
    if m2 <= 1e-24:
        skew = 0.0
        kurt = 0.0
    else:
        m3 = float(np.mean(centered ** 3))
        m4 = float(np.mean(centered ** 4))
        skew = m3 / (m2 ** 1.5)
        kurt = m4 / (m2 * m2) - 3.0
    q10, q25, q50, q75, q90 = np.quantile(x, [0.10, 0.25, 0.50, 0.75, 0.90])
    upper = x[x >= q90]
    lower = x[x <= q10]
    upper_mag = float(np.mean(np.abs(upper))) if upper.size else 0.0
    lower_mag = float(np.mean(np.abs(lower))) if lower.size else 0.0
    eps = 1e-12
    tail_log_ratio = float(math.log((upper_mag + eps) / (lower_mag + eps)))
    upper_extreme = float(np.mean(x >= mean + 1.5 * scale))
    lower_extreme = float(np.mean(x <= mean - 1.5 * scale))
    total_abs = float(np.sum(np.abs(x)))
    extreme_abs = float(np.sum(np.abs(upper)) + np.sum(np.abs(lower)))
    upper_wing = float(q90 - q75)
    lower_wing = float(q25 - q10)
    wing_denom = max(upper_wing + lower_wing, eps)
    return {
        "cross_skew": float(skew),
        "cross_excess_kurtosis": float(kurt),
        "tail_log_magnitude_ratio": tail_log_ratio,
        "tail_count_imbalance": upper_extreme - lower_extreme,
        "median_mean_gap_norm": float((mean - median) / scale),
        "extreme_abs_concentration": float(extreme_abs / max(total_abs, eps)),
        "center_iqr_norm": float((q75 - q25) / scale),
        "upper_wing_norm": float(upper_wing / scale),
        "lower_wing_norm": float(lower_wing / scale),
        "wing_asymmetry": float((upper_wing - lower_wing) / wing_denom),
        "upper_half_span_norm": float((q90 - q50) / scale),
        "lower_half_span_norm": float((q50 - q10) / scale),
    }


def build_distribution_frame(
    frame: pd.DataFrame,
    universe: Sequence[str],
    accepted_sessions: Sequence[str],
) -> pd.DataFrame:
    allowed = set(map(str, accepted_sessions))
    selected = frame.loc[
        frame["symbol"].isin(list(universe))
        & frame["session_date"].astype(str).isin(allowed)
    ].copy()
    selected = selected.sort_values(["symbol", "session_date", "timestamp"], kind="mergesort")
    selected["log_ret1"] = selected.groupby(
        ["symbol", "session_date"], observed=True, sort=False
    )["close"].transform(lambda v: np.log(v).diff())
    rows: list[dict[str, Any]] = []
    for (session_date, timestamp), group in selected.groupby(
        ["session_date", "timestamp"], sort=True
    ):
        values = pd.to_numeric(group["log_ret1"], errors="coerce").to_numpy(float)
        values = values[np.isfinite(values)]
        if values.size < MIN_CONSTITUENTS:
            continue
        rows.append(
            {
                "session_date": str(session_date),
                "timestamp": pd.Timestamp(timestamp),
                "distribution_constituent_count": int(values.size),
                **_distribution_shape(values),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("no distribution-shape rows passed constituent gate")
    return result.sort_values(["session_date", "timestamp"], kind="mergesort").reset_index(drop=True)


def fit_clock_norms(frame: pd.DataFrame) -> dict[str, Any]:
    observation = frame.loc[frame["split"].eq("observation")].copy()
    if observation.empty:
        raise ValueError("clock normalization requires observation rows")
    observation["clock_key"] = observation["timestamp"].dt.strftime("%H:%M")
    norms: dict[str, Any] = {}
    for metric in CLOCK_METRICS:
        values = pd.to_numeric(observation[metric], errors="coerce")
        global_median = float(np.nanmedian(values.to_numpy(float)))
        global_q25 = float(np.nanquantile(values.to_numpy(float), 0.25))
        global_q75 = float(np.nanquantile(values.to_numpy(float), 0.75))
        global_scale = max(global_q75 - global_q25, 1e-12)
        slots: dict[str, dict[str, float]] = {}
        for clock_key, group in observation.groupby("clock_key", sort=True):
            x = pd.to_numeric(group[metric], errors="coerce").dropna().to_numpy(float)
            if x.size < 20:
                slots[str(clock_key)] = {"median": global_median, "scale": global_scale}
                continue
            med = float(np.median(x))
            scale = float(np.quantile(x, 0.75) - np.quantile(x, 0.25))
            slots[str(clock_key)] = {
                "median": med,
                "scale": max(scale, global_scale * 0.10, 1e-12),
            }
        norms[metric] = {
            "global_median": global_median,
            "global_scale": global_scale,
            "slots": slots,
        }
    payload = {
        "fit_scope": "observation_only",
        "metrics": norms,
        "outcomes_seen": False,
    }
    payload["semantic_sha256"] = digest(payload)
    return payload


def apply_clock_norms(frame: pd.DataFrame, norms: Mapping[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    clock = result["timestamp"].dt.strftime("%H:%M")
    for metric, output in CLOCK_METRICS.items():
        config = norms["metrics"][metric]
        medians = clock.map(
            lambda key: float(config["slots"].get(str(key), {}).get("median", config["global_median"]))
        )
        scales = clock.map(
            lambda key: float(config["slots"].get(str(key), {}).get("scale", config["global_scale"]))
        )
        values = pd.to_numeric(result[metric], errors="coerce")
        result[output] = ((values - medians) / scales.replace(0, np.nan)).clip(-10.0, 10.0)
    return result


def _signed_run(values: pd.Series) -> pd.Series:
    signs = np.sign(pd.to_numeric(values, errors="coerce").fillna(0.0).to_numpy(float))
    runs = np.zeros(signs.size, dtype=float)
    prior = 0.0
    run = 0
    for i, sign in enumerate(signs):
        if sign == 0:
            run = 0
        elif sign == prior:
            run += 1
        else:
            run = 1
        runs[i] = float(run)
        prior = sign
    return pd.Series(runs, index=values.index)


def _flip_count(values: pd.Series, window: int = 6) -> pd.Series:
    signs = np.sign(pd.to_numeric(values, errors="coerce").fillna(0.0))
    changed = signs.ne(signs.shift(1)) & signs.ne(0) & signs.shift(1).fillna(0).ne(0)
    return changed.astype(float).rolling(window, min_periods=2).sum()


def _peak_age(values: pd.Series, window: int = 6) -> pd.Series:
    def age(arr: np.ndarray) -> float:
        x = np.asarray(arr, dtype=float)
        if x.size == 0 or not np.isfinite(x).any():
            return np.nan
        idx = int(np.nanargmax(np.abs(x)))
        return float(x.size - 1 - idx)
    return pd.to_numeric(values, errors="coerce").rolling(window, min_periods=3).apply(age, raw=True)


def _path_efficiency(values: pd.Series, window: int = 6) -> pd.Series:
    def eff(arr: np.ndarray) -> float:
        x = np.asarray(arr, dtype=float)
        if x.size < 2 or not np.isfinite(x).all():
            return np.nan
        path = float(np.sum(np.abs(np.diff(x))))
        return float(abs(x[-1] - x[0]) / max(path, 1e-12))
    return pd.to_numeric(values, errors="coerce").rolling(window, min_periods=3).apply(eff, raw=True)


def _loop_area(x: pd.Series, y: pd.Series, window: int = 6) -> pd.Series:
    xv = pd.to_numeric(x, errors="coerce").to_numpy(float)
    yv = pd.to_numeric(y, errors="coerce").to_numpy(float)
    out = np.full(xv.size, np.nan, dtype=float)
    for i in range(xv.size):
        start = max(0, i - window + 1)
        a = xv[start : i + 1]
        b = yv[start : i + 1]
        if a.size < 3 or not np.isfinite(a).all() or not np.isfinite(b).all():
            continue
        area = 0.5 * abs(float(np.dot(a, np.roll(b, -1)) - np.dot(b, np.roll(a, -1))))
        out[i] = area / a.size
    return pd.Series(out, index=x.index)


def add_temporal_batch_b_features(frame: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, group in frame.groupby("session_date", sort=True):
        x = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True).copy()
        x["breadth_sign_run"] = _signed_run(x["breadth_clock_resid"])
        x["divergence_sign_run"] = _signed_run(x["divergence_clock_resid"])
        x["dispersion_high_run"] = _signed_run(x["dispersion_clock_resid"])
        x["concentration_high_run"] = _signed_run(x["concentration_clock_resid"])
        x["breadth_flip_count6"] = _flip_count(x["breadth_clock_resid"])
        x["divergence_flip_count6"] = _flip_count(x["divergence_clock_resid"])
        x["breadth_peak_age6"] = _peak_age(x["breadth_clock_resid"])
        x["dispersion_peak_age6"] = _peak_age(x["dispersion_clock_resid"])
        x["concentration_peak_age6"] = _peak_age(x["concentration_clock_resid"])
        x["divergence_peak_age6"] = _peak_age(x["divergence_clock_resid"])
        x["breadth_dispersion_phase6"] = x["breadth_peak_age6"] - x["dispersion_peak_age6"]
        x["divergence_concentration_phase6"] = x["divergence_peak_age6"] - x["concentration_peak_age6"]
        x["breadth_path_efficiency6"] = _path_efficiency(x["breadth_clock_resid"])
        x["dispersion_path_efficiency6"] = _path_efficiency(x["dispersion_clock_resid"])
        x["concentration_path_efficiency6"] = _path_efficiency(x["concentration_clock_resid"])
        x["divergence_path_efficiency6"] = _path_efficiency(x["divergence_clock_resid"])
        x["breadth_dispersion_loop_area6"] = _loop_area(
            x["breadth_clock_resid"], x["dispersion_clock_resid"]
        )
        x["divergence_concentration_loop_area6"] = _loop_area(
            x["divergence_clock_resid"], x["concentration_clock_resid"]
        )
        parts.append(x)
    return pd.concat(parts, ignore_index=True).sort_values(
        ["session_date", "timestamp"], kind="mergesort"
    ).reset_index(drop=True)


def build_batch_b_frame(
    raw: pd.DataFrame,
    universe: Sequence[str],
    accepted_sessions: Sequence[str],
    base_cross: pd.DataFrame,
    clock_norms: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    distribution = build_distribution_frame(raw, universe, accepted_sessions)
    result = base_cross.merge(
        distribution,
        on=["session_date", "timestamp"],
        how="inner",
        validate="one_to_one",
    )
    if clock_norms is None:
        clock_norms = fit_clock_norms(result)
    result = apply_clock_norms(result, clock_norms)
    result = add_temporal_batch_b_features(result)
    return result, dict(clock_norms)


def freeze_batch_b_discovery(
    frame: pd.DataFrame,
    splits: Mapping[str, Sequence[str]],
) -> tuple[dict[str, FamilyModel], dict[str, pd.DataFrame], dict[str, Any]]:
    models: dict[str, FamilyModel] = {}
    assignments: dict[str, pd.DataFrame] = {}
    families: list[dict[str, Any]] = []
    all_motifs: list[dict[str, Any]] = []
    for family, features in BATCH_B_FEATURES.items():
        model = fit_family_model(frame, family, features)
        if model is None:
            families.append(
                {
                    "family": family,
                    "batch": "B",
                    "principal_verdict": "FAMILY_NOT_MODELABLE_OUTCOME_BLIND",
                    "motif_count": 0,
                }
            )
            continue
        assigned = assign_family(frame, model)
        motifs = freeze_family_motifs(assigned, model, splits)
        models[family] = model
        assignments[family] = assigned
        model_payload = {
            "family": family,
            "features": list(model.features),
            "k": model.k,
            "centers": model.centers.tolist(),
            "median": model.median.tolist(),
            "scale": model.scale.tolist(),
            "confidence_threshold": model.confidence_threshold,
            "observation_silhouette": model.observation_silhouette,
            "model_semantic_sha256": model.model_semantic_sha256,
            "fit_scope": "observation_only",
            "outcomes_seen": False,
        }
        families.append(
            {
                "family": family,
                "batch": "B",
                "principal_verdict": (
                    "OUTCOME_BLIND_RECURRENT_TRANSITIONS_FROZEN"
                    if motifs
                    else "NO_RECURRENT_TRANSITION_PASSED_STABILITY_GATES"
                ),
                "motif_count": len(motifs),
                "model": model_payload,
                "motifs": motifs,
            }
        )
        all_motifs.extend(motifs)
    catalog = {
        "principal_verdict": "AUTONOMOUS_BATCH_B_OUTCOME_BLIND_DISCOVERY_FROZEN",
        "batch": "B",
        "families_attempted": list(BATCH_B_FEATURES),
        "family_count": len(BATCH_B_FEATURES),
        "families": families,
        "total_frozen_motifs": len(all_motifs),
        "policy": {
            "outcomes_seen_when_frozen": False,
            "future_returns_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "family_definitions_orthogonal_to_batch_a": True,
            "failed_batch_a_families_reopened": False,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return models, assignments, catalog
