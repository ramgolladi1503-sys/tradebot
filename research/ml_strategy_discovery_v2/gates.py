from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contracts import StabilityConfig
from .model import rule_mask


def label_profit_factor(returns: pd.Series) -> float | None:
    numeric = pd.to_numeric(returns, errors="raise").dropna().astype(float)
    gains = float(numeric[numeric > 0].sum())
    losses = float(-numeric[numeric < 0].sum())
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def max_drawdown(returns: pd.Series) -> float:
    numeric = pd.to_numeric(returns, errors="raise").fillna(0.0).astype(float)
    equity = numeric.cumsum()
    drawdown = equity - equity.cummax()
    return float(-drawdown.min()) if len(drawdown) else 0.0


def performance_metrics(frame: pd.DataFrame, mask: pd.Series) -> dict[str, Any]:
    selected = frame.loc[mask].copy()
    returns = pd.to_numeric(
        selected.get("label_return_r", pd.Series(dtype=float)), errors="raise"
    ).dropna()
    positive = returns[returns > 0]
    negative = returns[returns < 0]
    return {
        "rows": int(len(returns)),
        "sessions": int(selected.loc[returns.index, "session_date"].nunique())
        if len(returns)
        else 0,
        "support_rate": float(len(returns) / len(frame)) if len(frame) else 0.0,
        "win_rate": float((returns > 0).mean()) if len(returns) else 0.0,
        "expectancy_r": float(returns.mean()) if len(returns) else 0.0,
        "median_r": float(returns.median()) if len(returns) else 0.0,
        "total_r": float(returns.sum()) if len(returns) else 0.0,
        "gross_positive_r": float(positive.sum()),
        "gross_negative_r": float(negative.sum()),
        "label_pf": label_profit_factor(returns),
        "max_drawdown_r": max_drawdown(returns),
    }


def concentration_metrics(frame: pd.DataFrame, mask: pd.Series) -> dict[str, Any]:
    selected = frame.loc[mask].copy()
    returns = pd.to_numeric(selected["label_return_r"], errors="raise").astype(float)
    positives = returns[returns > 0]
    total_positive = float(positives.sum())

    def contribution(values: pd.Series, n: int) -> float:
        if total_positive <= 0:
            return 1.0
        return float(values.nlargest(n).sum() / total_positive)

    selected["year"] = selected["session_date"].astype(str).str[:4]
    positive_frame = selected[selected["label_return_r"] > 0]
    year = positive_frame.groupby("year")["label_return_r"].sum()
    regime_column = next(
        (
            name
            for name in (
                "regime",
                "deterministic_regime",
                "volatility_regime",
                "trend_regime",
            )
            if name in selected.columns
        ),
        None,
    )
    regime = (
        positive_frame.groupby(regime_column)["label_return_r"].sum()
        if regime_column is not None and not positive_frame.empty
        else pd.Series(dtype=float)
    )
    session = positive_frame.groupby("session_date")["label_return_r"].sum()
    return {
        "top1_trade_positive_contribution": contribution(positives, 1),
        "top5_trade_positive_contribution": contribution(positives, 5),
        "top10_trade_positive_contribution": contribution(positives, 10),
        "largest_session_positive_contribution": float(session.max() / total_positive)
        if total_positive > 0 and not session.empty
        else 1.0,
        "largest_year_positive_contribution": float(year.max() / total_positive)
        if total_positive > 0 and not year.empty
        else 1.0,
        "largest_regime_positive_contribution": float(regime.max() / total_positive)
        if total_positive > 0 and not regime.empty
        else None,
        "regime_column": regime_column,
    }


def session_bootstrap_expectancy(
    frame: pd.DataFrame,
    mask: pd.Series,
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    selected = frame.loc[mask, ["session_date", "label_return_r"]].copy()
    if selected.empty:
        return {
            "iterations": iterations,
            "lower_95": None,
            "median": None,
            "upper_95": None,
        }
    session_groups = {
        str(session): group["label_return_r"].astype(float).to_numpy()
        for session, group in selected.groupby("session_date", sort=True)
    }
    sessions = np.array(sorted(session_groups), dtype=object)
    rng = np.random.default_rng(seed)
    samples = np.empty(iterations, dtype=float)
    for index in range(iterations):
        drawn = rng.choice(sessions, size=len(sessions), replace=True)
        values = np.concatenate([session_groups[str(session)] for session in drawn])
        samples[index] = float(values.mean())
    return {
        "iterations": int(iterations),
        "seed": int(seed),
        "lower_95": float(np.quantile(samples, 0.025)),
        "median": float(np.quantile(samples, 0.5)),
        "upper_95": float(np.quantile(samples, 0.975)),
    }


def imputation_dependence(
    frame: pd.DataFrame, candidate: dict[str, Any]
) -> dict[str, Any]:
    mask, dependent_selected = rule_mask(
        frame, candidate, return_imputation_dependency=True
    )
    selected_count = int(mask.sum())
    features = sorted({condition["feature"] for condition in candidate["conditions"]})
    per_feature = {
        feature: float(frame.loc[mask, feature].isna().mean())
        if selected_count
        else 0.0
        for feature in features
    }
    any_fraction = (
        float(dependent_selected.sum() / selected_count) if selected_count else 0.0
    )
    return {
        "selected_rows": selected_count,
        "any_feature_fraction": any_fraction,
        "per_feature_fraction": per_feature,
    }


def support_gate(
    metrics: dict[str, Any], config: StabilityConfig
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics["rows"] < config.min_rows:
        reasons.append("MIN_ROWS")
    if metrics["sessions"] < config.min_sessions:
        reasons.append("MIN_SESSIONS")
    if metrics["support_rate"] < 0.005:
        reasons.append("EXTREMELY_RARE")
    if metrics["support_rate"] > 0.95:
        reasons.append("NEAR_UNIVERSAL")
    return not reasons, reasons


def base_rate_gate(
    candidate_metrics: dict[str, Any], base_metrics: dict[str, Any]
) -> tuple[bool, list[str]]:
    if candidate_metrics["expectancy_r"] <= base_metrics["expectancy_r"]:
        return False, ["NO_BASE_RATE_LIFT"]
    return True, []


def fold_gate(
    fold_results: list[dict[str, Any]], config: StabilityConfig
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    if not fold_results:
        return False, ["NO_OUTER_FOLDS"], {}
    trade_bearing = [item for item in fold_results if item["metrics"]["rows"] > 0]
    coverage = len(trade_bearing) / len(fold_results)
    expectations = [item["metrics"]["expectancy_r"] for item in trade_bearing]
    median_expectancy = float(np.median(expectations)) if expectations else 0.0
    positive_totals = [max(0.0, item["metrics"]["total_r"]) for item in trade_bearing]
    total_positive = float(sum(positive_totals))
    largest_contribution = (
        max(positive_totals) / total_positive if total_positive > 0 else 1.0
    )
    if coverage < config.min_trade_bearing_fold_fraction:
        reasons.append("INSUFFICIENT_FOLD_COVERAGE")
    if median_expectancy <= 0:
        reasons.append("NON_POSITIVE_MEDIAN_FOLD_EXPECTANCY")
    if largest_contribution > config.max_fold_positive_contribution:
        reasons.append("FOLD_CONCENTRATION")
    summary = {
        "folds": len(fold_results),
        "trade_bearing_folds": len(trade_bearing),
        "trade_bearing_fraction": float(coverage),
        "median_fold_expectancy_r": median_expectancy,
        "largest_fold_positive_contribution": float(largest_contribution),
    }
    return not reasons, reasons, summary


def concentration_gate(
    values: dict[str, Any], config: StabilityConfig
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if (
        values["top5_trade_positive_contribution"]
        > config.max_top5_positive_contribution
    ):
        reasons.append("TOP5_TRADE_CONCENTRATION")
    if (
        values["largest_year_positive_contribution"]
        > config.max_year_positive_contribution
    ):
        reasons.append("YEAR_CONCENTRATION")
    regime_value = values.get("largest_regime_positive_contribution")
    if (
        regime_value is not None
        and regime_value > config.max_regime_positive_contribution
    ):
        reasons.append("REGIME_CONCENTRATION")
    return not reasons, reasons


def bootstrap_gate(values: dict[str, Any]) -> tuple[bool, list[str]]:
    lower = values.get("lower_95")
    if lower is None or lower < -0.1:
        return False, ["BOOTSTRAP_LOWER_BOUND_MATERIALLY_NEGATIVE"]
    return True, []


def imputation_gate(
    values: dict[str, Any], config: StabilityConfig
) -> tuple[bool, list[str]]:
    if values["any_feature_fraction"] > config.max_imputed_selection_fraction:
        return False, ["IMPUTATION_DEPENDENCE"]
    return True, []
