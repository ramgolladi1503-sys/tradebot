from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contracts import canonical_hash
from .model import rule_mask


def _permuted_labels_by_session(
    frame: pd.DataFrame,
    *,
    rng: np.random.Generator,
) -> pd.Series:
    """Permute complete label vectors between same-length sessions."""
    result = pd.Series(index=frame.index, dtype=float)
    grouped: dict[int, list[tuple[str, np.ndarray, np.ndarray]]] = {}
    for session, group in frame.groupby("session_date", sort=True):
        indices = group.index.to_numpy()
        labels = group["label_return_r"].astype(float).to_numpy()
        grouped.setdefault(len(group), []).append((str(session), indices, labels))
    for items in grouped.values():
        order = rng.permutation(len(items))
        for destination_index, source_index in enumerate(order):
            destination_indices = items[destination_index][1]
            source_labels = items[int(source_index)][2]
            result.loc[destination_indices] = source_labels
    if result.isna().any():
        raise AssertionError("session permutation failed to assign all labels")
    return result


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    values = np.asarray(p_values, dtype=float)
    if ((values < 0) | (values > 1)).any():
        raise ValueError("p-values must be in [0, 1]")
    order = np.argsort(values)
    ranked = values[order]
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for reverse_index in range(len(values) - 1, -1, -1):
        rank = reverse_index + 1
        running = min(running, float(ranked[reverse_index] * len(values) / rank))
        adjusted[order[reverse_index]] = running
    return adjusted.clip(0.0, 1.0).tolist()


def max_statistic_test(
    frame: pd.DataFrame,
    candidates: list[dict[str, Any]],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    if iterations < 100:
        raise ValueError("at least 100 permutations are required")
    if not candidates:
        return {
            "iterations": iterations,
            "seed": seed,
            "hypothesis_count": 0,
            "candidates": [],
            "null_distribution_hash": canonical_hash([]),
        }
    masks = [rule_mask(frame, candidate) for candidate in candidates]
    observed = [
        float(frame.loc[mask, "label_return_r"].mean()) if mask.any() else 0.0
        for mask in masks
    ]
    rng = np.random.default_rng(seed)
    null_matrix = np.empty((iterations, len(candidates)), dtype=float)
    for iteration in range(iterations):
        permuted = _permuted_labels_by_session(frame, rng=rng)
        for index, mask in enumerate(masks):
            null_matrix[iteration, index] = (
                float(permuted.loc[mask].mean()) if mask.any() else 0.0
            )
    max_null = null_matrix.max(axis=1)
    raw_p = [
        float((1 + np.count_nonzero(null_matrix[:, index] >= value)) / (iterations + 1))
        for index, value in enumerate(observed)
    ]
    fwer_p = [
        float((1 + np.count_nonzero(max_null >= value)) / (iterations + 1))
        for value in observed
    ]
    q_values = benjamini_hochberg(raw_p)
    records: list[dict[str, Any]] = []
    for candidate, statistic, p_value, family_p, q_value in zip(
        candidates, observed, raw_p, fwer_p, q_values
    ):
        records.append(
            {
                "rule_hash": candidate["rule_hash"],
                "observed_expectancy_r": statistic,
                "raw_p_value": p_value,
                "max_statistic_fwer_p_value": family_p,
                "bh_fdr_q_value": q_value,
                "passes_adjusted_significance": bool(
                    family_p <= 0.05 and q_value <= 0.05 and statistic > 0
                ),
            }
        )
    return {
        "iterations": int(iterations),
        "seed": int(seed),
        "hypothesis_count": len(candidates),
        "candidates": records,
        "null_distribution_hash": canonical_hash(max_null.tolist()),
        "null_max_expectancy_quantiles": {
            "q50": float(np.quantile(max_null, 0.50)),
            "q95": float(np.quantile(max_null, 0.95)),
            "q99": float(np.quantile(max_null, 0.99)),
        },
    }


def _condition_map(candidate: dict[str, Any]) -> dict[tuple[str, str], float]:
    return {
        (str(condition["feature"]), str(condition["operator"])): float(
            condition["threshold"]
        )
        for condition in candidate["conditions"]
    }


def rule_similarity(
    left: dict[str, Any], right: dict[str, Any], *, relative_tolerance: float = 0.10
) -> float:
    left_map = _condition_map(left)
    right_map = _condition_map(right)
    keys = set(left_map) | set(right_map)
    if not keys:
        return 0.0
    scores: list[float] = []
    for key in keys:
        if key not in left_map or key not in right_map:
            scores.append(0.0)
            continue
        denominator = max(abs(left_map[key]), abs(right_map[key]), 1.0)
        distance = abs(left_map[key] - right_map[key]) / denominator
        scores.append(max(0.0, 1.0 - distance / relative_tolerance))
    return float(np.mean(scores))


def jaccard_selected_rows(
    frame: pd.DataFrame, left: dict[str, Any], right: dict[str, Any]
) -> float:
    left_indices = set(frame.index[rule_mask(frame, left)].tolist())
    right_indices = set(frame.index[rule_mask(frame, right)].tolist())
    union = left_indices | right_indices
    if not union:
        return 1.0
    return len(left_indices & right_indices) / len(union)


def recurrence_summary(
    frame: pd.DataFrame,
    candidate: dict[str, Any],
    fold_candidates: list[list[dict[str, Any]]],
    *,
    minimum_similarity: float = 0.80,
) -> dict[str, Any]:
    best_similarities: list[float] = []
    best_jaccards: list[float] = []
    recurring = 0
    for candidates in fold_candidates:
        if not candidates:
            best_similarities.append(0.0)
            best_jaccards.append(0.0)
            continue
        scored = [
            (
                rule_similarity(candidate, other),
                jaccard_selected_rows(frame, candidate, other),
            )
            for other in candidates
        ]
        best = max(scored, key=lambda item: (item[0], item[1]))
        best_similarities.append(float(best[0]))
        best_jaccards.append(float(best[1]))
        if best[0] >= minimum_similarity:
            recurring += 1
    fold_count = len(fold_candidates)
    condition_keys = sorted(f"{key[0]}:{key[1]}" for key in _condition_map(candidate))
    return {
        "fold_count": fold_count,
        "recurring_folds": recurring,
        "recurrence_fraction": float(recurring / fold_count) if fold_count else 0.0,
        "median_rule_similarity": float(np.median(best_similarities))
        if best_similarities
        else 0.0,
        "median_selected_row_jaccard": float(np.median(best_jaccards))
        if best_jaccards
        else 0.0,
        "condition_signature": condition_keys,
        "passes_recurrence": bool(
            fold_count > 0
            and recurring / fold_count >= 0.60
            and np.median(best_similarities) >= minimum_similarity
        ),
    }
