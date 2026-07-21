from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import numpy as np
import pandas as pd

from .contracts import RuleCondition, StrategyCandidate


def candidate_mask(dataset: pd.DataFrame, candidate: StrategyCandidate) -> pd.Series:
    mask = pd.Series(True, index=dataset.index)
    imputation = candidate.imputation_map()
    for condition in candidate.conditions:
        if condition.feature not in dataset.columns:
            raise ValueError(
                f"candidate feature missing from dataset: {condition.feature}"
            )
        values = pd.to_numeric(dataset[condition.feature], errors="coerce")
        if condition.feature in imputation:
            values = values.fillna(imputation[condition.feature])
        current = (
            values <= condition.threshold
            if condition.operator == "<="
            else values > condition.threshold
        )
        mask &= current.fillna(False)
    return mask


def _metrics(returns: pd.Series, sessions: pd.Series) -> dict[str, float | int | None]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {
            "trades": 0,
            "sessions": 0,
            "label_win_rate": None,
            "label_expectancy_r": None,
            "label_profit_factor": None,
            "label_max_drawdown_r": None,
            "label_total_return_r": None,
        }
    wins = clean[clean > 0]
    losses = clean[clean < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    equity = clean.cumsum()
    drawdown = equity - equity.cummax()
    return {
        "trades": int(len(clean)),
        "sessions": int(sessions.loc[clean.index].nunique()),
        "label_win_rate": float((clean > 0).mean()),
        "label_expectancy_r": float(clean.mean()),
        "label_profit_factor": (
            gross_profit / gross_loss if gross_loss > 0 else None
        ),
        "label_max_drawdown_r": float(drawdown.min()),
        "label_total_return_r": float(clean.sum()),
    }


def evaluate_candidate(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
    *,
    allowed_splits: Iterable[str] = ("VALIDATION",),
    cost_r: float = 0.0,
) -> dict[str, float | int | None]:
    if cost_r < 0:
        raise ValueError("cost_r cannot be negative")
    scope = dataset.loc[dataset["split"].isin(tuple(allowed_splits))].copy()
    if scope.empty:
        raise ValueError("evaluation scope is empty")
    selected = candidate_mask(scope, candidate)
    returns = scope.loc[selected, "label_return_r"] - cost_r
    metrics = _metrics(returns, scope["session_date"])
    metrics["claim_boundary"] = "UNDERLYING_RESEARCH_LABELS_NOT_OPTION_PNL"
    metrics["label_cost_r"] = float(cost_r)
    return metrics


def evaluate_locked_holdout_once(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
    *,
    acknowledgement: str,
    cost_r: float = 0.0,
) -> dict[str, float | int | None]:
    required = "EVALUATE_FROZEN_CANDIDATE_ONCE"
    if acknowledgement != required:
        raise PermissionError(
            "locked holdout requires explicit acknowledgement; the caller must "
            "also preserve an external consumption record"
        )
    return evaluate_candidate(
        dataset,
        candidate,
        allowed_splits=("HOLDOUT_LOCKED",),
        cost_r=cost_r,
    )


def walk_forward_evaluate(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
    *,
    allowed_splits: Iterable[str] = ("VALIDATION",),
    folds: int = 5,
    cost_r: float = 0.0,
) -> list[dict[str, float | int | None]]:
    """Segment a frozen rule across contiguous validation-session folds.

    This is not a certifying re-fit walk-forward analysis. The candidate remains
    frozen and each fold is only a temporal stability slice.
    """

    scope = dataset.loc[dataset["split"].isin(tuple(allowed_splits))].copy()
    scope = scope.sort_values("decision_timestamp", kind="mergesort")
    if folds < 2 or len(scope) < folds * 5:
        raise ValueError("insufficient rows for requested validation folds")
    ordered_sessions = (
        scope.groupby("session_date", sort=False)["decision_timestamp"]
        .min()
        .sort_values(kind="mergesort")
        .index.to_numpy()
    )
    if len(ordered_sessions) < folds:
        raise ValueError("insufficient complete sessions for requested folds")
    session_folds = np.array_split(ordered_sessions, folds)
    results: list[dict[str, float | int | None]] = []
    for fold_number, fold_sessions in enumerate(session_folds, start=1):
        fold = scope.loc[scope["session_date"].isin(fold_sessions)].copy()
        selected = candidate_mask(fold, candidate)
        metrics = _metrics(
            fold.loc[selected, "label_return_r"] - cost_r,
            fold["session_date"],
        )
        metrics.update(
            {
                "fold": fold_number,
                "start": str(fold["decision_timestamp"].min()),
                "end": str(fold["decision_timestamp"].max()),
                "claim_boundary": "FROZEN_RULE_VALIDATION_SLICE_NOT_CERTIFYING_WFA",
                "label_cost_r": float(cost_r),
            }
        )
        results.append(metrics)
    return results


def run_negative_controls(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
    *,
    allowed_splits: Iterable[str] = ("VALIDATION",),
    random_seed: int = 42,
    timestamp_shift_rows: int = 7,
) -> dict[str, dict[str, float | int | None]]:
    scope = dataset.loc[dataset["split"].isin(tuple(allowed_splits))].copy()
    if scope.empty:
        raise ValueError("negative-control scope is empty")
    selected = candidate_mask(scope, candidate)
    rng = np.random.default_rng(random_seed)

    original = _metrics(scope.loc[selected, "label_return_r"], scope["session_date"])

    permuted = scope["label_return_r"].to_numpy(copy=True)
    rng.shuffle(permuted)
    permuted_series = pd.Series(permuted, index=scope.index)
    label_permutation = _metrics(
        permuted_series.loc[selected], scope["session_date"]
    )

    shifted_selected = selected.shift(timestamp_shift_rows, fill_value=False)
    timestamp_shift = _metrics(
        scope.loc[shifted_selected, "label_return_r"], scope["session_date"]
    )

    ablations: list[dict[str, float | int | None]] = []
    for index in range(len(candidate.conditions)):
        remaining = tuple(
            condition
            for condition_index, condition in enumerate(candidate.conditions)
            if condition_index != index
        )
        if not remaining:
            continue
        ablated = replace(candidate, conditions=remaining)
        metrics = _metrics(
            scope.loc[candidate_mask(scope, ablated), "label_return_r"],
            scope["session_date"],
        )
        metrics["removed_condition_index"] = index
        ablations.append(metrics)

    return {
        "original": original,
        "label_permutation": label_permutation,
        "timestamp_shift": timestamp_shift,
        "condition_ablations": {
            str(index): result for index, result in enumerate(ablations)
        },
    }


def parameter_stability(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
    *,
    allowed_splits: Iterable[str] = ("VALIDATION",),
    perturbations: tuple[float, ...] = (-0.10, -0.05, 0.05, 0.10),
    cost_r: float = 0.0,
) -> list[dict[str, float | int | None]]:
    results: list[dict[str, float | int | None]] = []
    for perturbation in perturbations:
        conditions = tuple(
            RuleCondition(
                feature=condition.feature,
                operator=condition.operator,
                threshold=condition.threshold * (1.0 + perturbation),
            )
            for condition in candidate.conditions
        )
        perturbed = replace(candidate, conditions=conditions)
        metrics = evaluate_candidate(
            dataset,
            perturbed,
            allowed_splits=allowed_splits,
            cost_r=cost_r,
        )
        metrics["threshold_perturbation"] = perturbation
        results.append(metrics)
    return results


def cost_stress(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
    *,
    allowed_splits: Iterable[str] = ("VALIDATION",),
    costs_r: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10),
) -> list[dict[str, float | int | None]]:
    results: list[dict[str, float | int | None]] = []
    for cost in costs_r:
        metrics = evaluate_candidate(
            dataset,
            candidate,
            allowed_splits=allowed_splits,
            cost_r=cost,
        )
        results.append(metrics)
    return results
