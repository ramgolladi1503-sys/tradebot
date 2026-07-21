from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .gates import performance_metrics
from .model import rule_mask


def _metrics_for_returns(
    frame: pd.DataFrame, mask: pd.Series, returns: pd.Series
) -> dict[str, Any]:
    control = frame.copy()
    control["label_return_r"] = pd.to_numeric(returns, errors="raise").reindex(
        frame.index
    )
    return performance_metrics(control, mask & control["label_return_r"].notna())


def _session_permutation(frame: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    output = pd.Series(index=frame.index, dtype=float)
    buckets: dict[int, list[tuple[np.ndarray, np.ndarray]]] = {}
    for _, group in frame.groupby("session_date", sort=True):
        buckets.setdefault(len(group), []).append(
            (group.index.to_numpy(), group["label_return_r"].astype(float).to_numpy())
        )
    for items in buckets.values():
        order = rng.permutation(len(items))
        for destination, source in enumerate(order):
            output.loc[items[destination][0]] = items[int(source)][1]
    if output.isna().any():
        raise AssertionError("session permutation did not assign every label")
    return output


def _shift_mask(frame: pd.DataFrame, mask: pd.Series, bars: int) -> pd.Series:
    shifted = (
        mask.astype(int)
        .groupby(frame["session_date"], sort=False)
        .shift(bars, fill_value=0)
        .astype(bool)
    )
    shifted.index = frame.index
    return shifted


def _shift_mask_across_sessions(
    frame: pd.DataFrame, mask: pd.Series, sessions: int
) -> pd.Series:
    ordered_sessions = sorted(frame["session_date"].astype(str).unique())
    source_by_destination = {
        ordered_sessions[index]: ordered_sessions[index - sessions]
        for index in range(sessions, len(ordered_sessions))
    }
    bar_index = frame.groupby("session_date", sort=False).cumcount()
    lookup = {
        (str(session), int(position)): bool(value)
        for session, position, value in zip(frame["session_date"], bar_index, mask)
    }
    values = []
    for session, position in zip(frame["session_date"].astype(str), bar_index):
        source_session = source_by_destination.get(session)
        values.append(
            False
            if source_session is None
            else lookup.get((source_session, int(position)), False)
        )
    return pd.Series(values, index=frame.index, dtype=bool)


def _delayed_feature_frame(
    frame: pd.DataFrame, features: list[str], bars: int
) -> pd.DataFrame:
    delayed = frame.copy()
    for feature in features:
        delayed[feature] = frame.groupby("session_date", sort=False)[feature].shift(
            bars
        )
    return delayed


def _perturbed_candidate(candidate: dict[str, Any], factor: float) -> dict[str, Any]:
    updated = dict(candidate)
    updated["conditions"] = [
        {**condition, "threshold": float(condition["threshold"]) * factor}
        for condition in candidate["conditions"]
    ]
    return updated


def run_negative_controls(
    frame: pd.DataFrame,
    candidate: dict[str, Any],
    *,
    seed: int = 42,
    cost_stress_r: float = 0.10,
) -> dict[str, Any]:
    """Run deterministic, development-only controls and return a gating verdict."""
    required = {"session_date", "label_return_r"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"control frame missing columns: {sorted(missing)}")
    original_mask = rule_mask(frame, candidate)
    original = performance_metrics(frame, original_mask)
    rng = np.random.default_rng(seed)
    controls: dict[str, dict[str, Any]] = {}

    row_permutation = pd.Series(
        rng.permutation(frame["label_return_r"].astype(float).to_numpy()),
        index=frame.index,
    )
    controls["row_label_permutation"] = _metrics_for_returns(
        frame, original_mask, row_permutation
    )

    session_permutation = _session_permutation(frame, rng)
    controls["whole_session_label_permutation"] = _metrics_for_returns(
        frame, original_mask, session_permutation
    )

    controls["timestamp_shift_one_session"] = performance_metrics(
        frame, _shift_mask_across_sessions(frame, original_mask, 1)
    )
    controls["placebo_decision_time_30_bars"] = performance_metrics(
        frame, _shift_mask(frame, original_mask, 30)
    )
    controls["one_bar_signal_latency"] = performance_metrics(
        frame, _shift_mask(frame, original_mask, 1)
    )
    controls["two_bar_signal_latency"] = performance_metrics(
        frame, _shift_mask(frame, original_mask, 2)
    )

    candidate_features = sorted(
        {condition["feature"] for condition in candidate["conditions"]}
    )
    for delay in (1, 2):
        delayed = _delayed_feature_frame(frame, candidate_features, delay)
        delayed_mask = rule_mask(delayed, candidate)
        controls[f"delayed_features_{delay}_bar"] = performance_metrics(
            frame, delayed_mask
        )

    reversed_returns = -frame["label_return_r"].astype(float)
    controls["reversed_direction_proxy"] = _metrics_for_returns(
        frame, original_mask, reversed_returns
    )

    ablations: list[tuple[str, dict[str, Any]]] = []
    for index in range(len(candidate["conditions"])):
        ablated = dict(candidate)
        ablated["conditions"] = [
            condition
            for condition_index, condition in enumerate(candidate["conditions"])
            if condition_index != index
        ]
        if not ablated["conditions"]:
            metrics = performance_metrics(frame, pd.Series(True, index=frame.index))
        else:
            metrics = performance_metrics(frame, rule_mask(frame, ablated))
        name = f"condition_ablation_{index}"
        controls[name] = metrics
        ablations.append((name, metrics))
    if ablations:
        strongest_name, strongest_metrics = min(
            ablations,
            key=lambda item: (item[1]["expectancy_r"], -item[1]["rows"]),
        )
        controls["strongest_condition_removal"] = {
            **strongest_metrics,
            "source_control": strongest_name,
        }

    threshold_controls: list[str] = []
    for percentage in (0.05, 0.10, 0.20):
        for direction in (-1, 1):
            factor = 1.0 + direction * percentage
            name = f"threshold_{direction:+d}_{int(percentage * 100)}pct"
            controls[name] = performance_metrics(
                frame, rule_mask(frame, _perturbed_candidate(candidate, factor))
            )
            threshold_controls.append(name)

    years = sorted(frame["session_date"].astype(str).str[:4].unique())
    for year in years:
        subset = frame[frame["session_date"].astype(str).str[:4] != year]
        controls[f"leave_year_out_{year}"] = performance_metrics(
            subset, rule_mask(subset, candidate)
        )

    regime_columns = [
        name
        for name in ("trend_regime", "volatility_regime", "gap_regime", "time_regime")
        if name in frame.columns
    ]
    if not regime_columns:
        raise ValueError("real deterministic regime columns are required for LORO")
    regime_key = frame[regime_columns].astype(str).agg("|".join, axis=1)
    for regime in sorted(regime_key.unique()):
        subset = frame[regime_key != regime]
        controls[f"leave_regime_out_{regime}"] = performance_metrics(
            subset, rule_mask(subset, candidate)
        )

    stressed = frame["label_return_r"].astype(float) - float(cost_stress_r)
    controls["abstract_cost_stress"] = _metrics_for_returns(
        frame, original_mask, stressed
    )

    rejection_reasons: list[str] = []
    for name in (
        "row_label_permutation",
        "whole_session_label_permutation",
        "timestamp_shift_one_session",
        "placebo_decision_time_30_bars",
    ):
        if controls[name]["expectancy_r"] >= original["expectancy_r"]:
            rejection_reasons.append(f"CONTROL_MATCHED_OR_EXCEEDED:{name}")
    for name in ("one_bar_signal_latency", "two_bar_signal_latency"):
        if controls[name]["expectancy_r"] <= 0:
            rejection_reasons.append(f"LATENCY_NON_POSITIVE:{name}")
    for name in ("delayed_features_1_bar", "delayed_features_2_bar"):
        if controls[name]["expectancy_r"] > original["expectancy_r"] * 1.10:
            rejection_reasons.append(f"DELAYED_FEATURE_IMPROVED:{name}")
    comparable_support = max(1, int(original["rows"] * 0.80))
    for name, metrics in ablations:
        if (
            metrics["rows"] >= comparable_support
            and metrics["expectancy_r"] > original["expectancy_r"] * 1.20
        ):
            rejection_reasons.append(f"ABLATION_IMPROVED_RULE:{name}")
    stable_thresholds = sum(
        1
        for name in threshold_controls
        if controls[name]["rows"] >= max(1, int(original["rows"] * 0.50))
        and controls[name]["expectancy_r"] > 0
    )
    if stable_thresholds < len(threshold_controls) / 2:
        rejection_reasons.append("THRESHOLD_NEIGHBORHOOD_UNSTABLE")
    loyo = [
        metrics
        for name, metrics in controls.items()
        if name.startswith("leave_year_out_")
    ]
    if loyo and sum(item["expectancy_r"] > 0 for item in loyo) / len(loyo) < 0.60:
        rejection_reasons.append("LEAVE_YEAR_OUT_UNSTABLE")
    loro = [
        metrics
        for name, metrics in controls.items()
        if name.startswith("leave_regime_out_")
    ]
    if loro and sum(item["expectancy_r"] > 0 for item in loro) / len(loro) < 0.60:
        rejection_reasons.append("LEAVE_REGIME_OUT_UNSTABLE")
    if controls["abstract_cost_stress"]["expectancy_r"] <= 0:
        rejection_reasons.append("COST_STRESS_NON_POSITIVE")

    return {
        "seed": int(seed),
        "original": original,
        "controls": controls,
        "threshold_variants_positive_with_support": stable_thresholds,
        "threshold_variant_count": len(threshold_controls),
        "passes": not rejection_reasons,
        "rejection_reasons": sorted(set(rejection_reasons)),
    }
