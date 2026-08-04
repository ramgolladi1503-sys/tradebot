from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION, CandidateMLConfig, PredictionStatus
from .dataset import (
    chronological_split,
    feature_columns,
    purged_walk_forward_splits,
    semantic_dataset_hash,
    validate_candidate_dataset,
)
from .model import CandidateMLBundle, _fit_unit


@dataclass(frozen=True)
class CandidateMLCertificationConfig:
    n_splits: int = 5
    min_train_sessions: int = 5
    min_selected_per_fold: int = 10
    min_positive_fold_fraction: float = 0.60
    min_mean_lift_r: float = 0.0
    max_ece: float = 0.15
    max_top_five_positive_contribution: float = 0.60
    max_best_session_positive_contribution: float = 0.40
    min_permutation_gap_r: float = 0.01
    min_delayed_mean_lift_r: float = -0.05
    max_ablation_features: int = 25
    random_state: int = 68742

    def __post_init__(self) -> None:
        if self.n_splits < 3:
            raise ValueError("certification_requires_at_least_three_folds")
        if self.min_selected_per_fold < 1:
            raise ValueError("min_selected_per_fold_invalid")
        if not 0 < self.min_positive_fold_fraction <= 1:
            raise ValueError("min_positive_fold_fraction_invalid")
        if not 0 < self.max_ece < 1:
            raise ValueError("max_ece_invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expected_calibration_error(
    labels: Sequence[int],
    probabilities: Sequence[float],
    *,
    bins: int = 10,
) -> float | None:
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if len(y) == 0 or len(y) != len(p):
        return None
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for index in range(bins):
        if index == bins - 1:
            mask = (p >= edges[index]) & (p <= edges[index + 1])
        else:
            mask = (p >= edges[index]) & (p < edges[index + 1])
        count = int(np.sum(mask))
        if count == 0:
            continue
        confidence = float(np.mean(p[mask]))
        accuracy = float(np.mean(y[mask]))
        ece += count / len(y) * abs(accuracy - confidence)
    return float(ece)


def _nested_model(
    train_frame: pd.DataFrame,
    model_config: CandidateMLConfig,
    *,
    features: Sequence[str] | None = None,
) -> CandidateMLBundle:
    inner_train, inner_validation = chronological_split(train_frame, model_config)
    selected_features = list(features or feature_columns(inner_train))
    if not selected_features:
        raise ValueError("certification_feature_set_empty")
    unit = _fit_unit(inner_train, inner_validation, selected_features, model_config)
    return CandidateMLBundle(
        config=model_config,
        global_model=unit,
        trained_at_utc="CERTIFICATION_NESTED_FOLD",
        dataset_hash=semantic_dataset_hash(train_frame),
    )


def _ordered_sessions(frame: pd.DataFrame) -> list[str]:
    return list(dict.fromkeys(frame["session_date"].astype(str).tolist()))


def _resolve_supported_min_train_sessions(
    research_df: pd.DataFrame,
    model_config: CandidateMLConfig,
    certification_config: CandidateMLCertificationConfig,
) -> tuple[int, dict[str, Any]]:
    """Find the first chronological prefix that can satisfy the unchanged model gates.

    The certification configuration expresses a minimum number of sessions, while
    the model contract also requires minimum train and validation row counts. Sparse
    candidate ledgers can therefore satisfy the session count but still be unable to
    fit a nested model. This resolver advances the fold boundary until the existing
    row-support gates pass; it never reduces those gates.
    """

    sessions = _ordered_sessions(research_df)
    requested = int(certification_config.min_train_sessions)
    latest_start = len(sessions) - int(certification_config.n_splits)
    if latest_start < requested:
        raise ValueError("insufficient_sessions_for_supported_walk_forward")

    attempts: list[dict[str, Any]] = []
    for session_count in range(requested, latest_start + 1):
        prefix_sessions = set(sessions[:session_count])
        prefix = research_df[
            research_df["session_date"].astype(str).isin(prefix_sessions)
        ].copy()
        try:
            inner_train, inner_validation = chronological_split(prefix, model_config)
        except ValueError as exc:
            attempts.append(
                {
                    "sessions": int(session_count),
                    "rows": int(len(prefix)),
                    "reason": str(exc),
                }
            )
            continue
        evidence = {
            "requested_min_train_sessions": requested,
            "effective_min_train_sessions": int(session_count),
            "prefix_rows": int(len(prefix)),
            "nested_train_rows": int(len(inner_train)),
            "nested_validation_rows": int(len(inner_validation)),
            "remaining_test_sessions": int(len(sessions) - session_count),
            "model_min_train_rows": int(model_config.min_train_rows),
            "model_min_validation_rows": int(model_config.min_validation_rows),
            "support_gates_lowered": False,
            "attempted_prefixes": attempts,
        }
        return int(session_count), evidence

    raise ValueError("no_chronological_prefix_satisfies_model_support")


def _score_frame(bundle: CandidateMLBundle, frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, source in frame.iterrows():
        payload = source.to_dict()
        prediction = bundle.predict(payload)
        rows.append(
            {
                "event_id": str(payload.get("event_id") or ""),
                "session_date": str(payload.get("session_date") or ""),
                "target": int(payload.get("target") or 0),
                "future_net_r": float(payload.get("future_net_r") or 0.0),
                "ml_status": prediction.status.value,
                "probability": prediction.probability,
                "expected_value_r": prediction.expected_value_r,
                "selected": prediction.status == PredictionStatus.VALID,
            }
        )
    return pd.DataFrame(rows)


def _concentration(scored: pd.DataFrame) -> dict[str, float | None]:
    selected = scored[scored["selected"]].copy()
    if selected.empty:
        return {
            "top_five_positive_contribution": None,
            "best_session_positive_contribution": None,
            "largest_session_share_of_rows": None,
        }
    positives = selected[selected["future_net_r"] > 0]["future_net_r"].sort_values(ascending=False)
    positive_total = float(positives.sum())
    top_five = float(positives.head(5).sum() / positive_total) if positive_total > 0 else None
    session_positive = (
        selected.assign(positive_r=selected["future_net_r"].clip(lower=0.0))
        .groupby("session_date", dropna=False)["positive_r"]
        .sum()
        .sort_values(ascending=False)
    )
    best_session = float(session_positive.iloc[0] / positive_total) if positive_total > 0 and len(session_positive) else None
    session_rows = selected.groupby("session_date", dropna=False).size()
    largest_row_share = float(session_rows.max() / len(selected)) if len(selected) else None
    return {
        "top_five_positive_contribution": top_five,
        "best_session_positive_contribution": best_session,
        "largest_session_share_of_rows": largest_row_share,
    }


def _fold_metrics(scored: pd.DataFrame) -> dict[str, Any]:
    selected = scored[scored["selected"]].copy()
    probabilities = scored.dropna(subset=["probability"])
    baseline_mean = float(scored["future_net_r"].mean()) if len(scored) else None
    selected_mean = float(selected["future_net_r"].mean()) if len(selected) else None
    lift = selected_mean - baseline_mean if selected_mean is not None and baseline_mean is not None else None
    ece = expected_calibration_error(
        probabilities["target"].astype(int).tolist(),
        probabilities["probability"].astype(float).tolist(),
    )
    brier = (
        float(brier_score_loss(probabilities["target"].astype(int), probabilities["probability"].astype(float)))
        if len(probabilities)
        else None
    )
    auc = None
    if len(probabilities) and probabilities["target"].nunique() == 2:
        auc = float(roc_auc_score(probabilities["target"].astype(int), probabilities["probability"].astype(float)))
    return {
        "rows": int(len(scored)),
        "probability_rows": int(len(probabilities)),
        "selected_rows": int(len(selected)),
        "baseline_mean_future_net_r": baseline_mean,
        "selected_mean_future_net_r": selected_mean,
        "selected_total_future_net_r": float(selected["future_net_r"].sum()) if len(selected) else None,
        "lift_r": lift,
        "positive_selected_expectancy": bool(selected_mean is not None and selected_mean > 0),
        "ece": ece,
        "brier": brier,
        "roc_auc": auc,
        "status_counts": {str(key): int(value) for key, value in scored["ml_status"].value_counts().to_dict().items()},
        "concentration": _concentration(scored),
    }


def _permute_targets(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    out = frame.copy()
    rng = np.random.default_rng(seed)
    out["target"] = rng.permutation(out["target"].astype(int).to_numpy())
    return out


def _delay_features(frame: pd.DataFrame, features: Sequence[str]) -> pd.DataFrame:
    out = frame.copy()
    out[list(features)] = (
        out.groupby("session_date", sort=False, dropna=False)[list(features)]
        .shift(1)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    return out


def _aggregate_fold_metrics(folds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lifts = [float(item["lift_r"]) for item in folds if item.get("lift_r") is not None]
    selected_means = [
        float(item["selected_mean_future_net_r"])
        for item in folds
        if item.get("selected_mean_future_net_r") is not None
    ]
    eces = [float(item["ece"]) for item in folds if item.get("ece") is not None]
    selected_counts = [int(item.get("selected_rows") or 0) for item in folds]
    positive_folds = sum(1 for value in selected_means if value > 0)
    return {
        "folds": int(len(folds)),
        "mean_lift_r": float(np.mean(lifts)) if lifts else None,
        "median_lift_r": float(np.median(lifts)) if lifts else None,
        "worst_lift_r": float(np.min(lifts)) if lifts else None,
        "mean_selected_future_net_r": float(np.mean(selected_means)) if selected_means else None,
        "positive_expectancy_fold_fraction": float(positive_folds / len(folds)) if folds else 0.0,
        "max_ece": float(np.max(eces)) if eces else None,
        "min_selected_rows": int(min(selected_counts)) if selected_counts else 0,
        "total_selected_rows": int(sum(selected_counts)),
    }


def _ablation_report(
    research_df: pd.DataFrame,
    model_config: CandidateMLConfig,
    certification_config: CandidateMLCertificationConfig,
    *,
    supported_train_sessions: int,
) -> dict[str, Any]:
    sessions = _ordered_sessions(research_df)
    train_sessions = set(sessions[:supported_train_sessions])
    test_sessions = set(sessions[supported_train_sessions:])
    train = research_df[
        research_df["session_date"].astype(str).isin(train_sessions)
    ].copy().reset_index(drop=True)
    validation = research_df[
        research_df["session_date"].astype(str).isin(test_sessions)
    ].copy().reset_index(drop=True)
    if validation.empty:
        raise ValueError("ablation_test_block_empty")

    all_features = feature_columns(train)
    base_bundle = _nested_model(train, model_config, features=all_features)
    base_metrics = _fold_metrics(_score_frame(base_bundle, validation))
    results: dict[str, Any] = {}
    for feature in all_features[: certification_config.max_ablation_features]:
        remaining = [name for name in all_features if name != feature]
        if not remaining:
            continue
        try:
            bundle = _nested_model(train, model_config, features=remaining)
            metrics = _fold_metrics(_score_frame(bundle, validation))
            results[feature] = {
                "lift_r": metrics.get("lift_r"),
                "selected_mean_future_net_r": metrics.get("selected_mean_future_net_r"),
                "delta_lift_vs_base": (
                    float(metrics["lift_r"] - base_metrics["lift_r"])
                    if metrics.get("lift_r") is not None and base_metrics.get("lift_r") is not None
                    else None
                ),
            }
        except Exception as exc:
            results[feature] = {"error": f"{type(exc).__name__}:{exc}"}
    return {
        "train_sessions": int(supported_train_sessions),
        "train_rows": int(len(train)),
        "test_sessions": int(len(test_sessions)),
        "test_rows": int(len(validation)),
        "base": base_metrics,
        "feature_ablations": results,
    }


def certify_candidate_ml(
    research_df: pd.DataFrame,
    *,
    model_config: CandidateMLConfig | None = None,
    certification_config: CandidateMLCertificationConfig | None = None,
) -> dict[str, Any]:
    validate_candidate_dataset(research_df)
    model_cfg = model_config or CandidateMLConfig()
    cert_cfg = certification_config or CandidateMLCertificationConfig()
    effective_train_sessions, support_evidence = _resolve_supported_min_train_sessions(
        research_df,
        model_cfg,
        cert_cfg,
    )
    splits = purged_walk_forward_splits(
        research_df,
        n_splits=cert_cfg.n_splits,
        purge_rows=model_cfg.purge_rows,
        min_train_sessions=effective_train_sessions,
    )
    base_folds: list[dict[str, Any]] = []
    permutation_folds: list[dict[str, Any]] = []
    delayed_folds: list[dict[str, Any]] = []
    errors: list[str] = []

    for fold_index, (train_idx, test_idx) in enumerate(splits):
        train_frame = research_df.iloc[train_idx].copy().reset_index(drop=True)
        test_frame = research_df.iloc[test_idx].copy().reset_index(drop=True)
        features = feature_columns(train_frame)
        try:
            base_bundle = _nested_model(train_frame, model_cfg, features=features)
            base_metrics = _fold_metrics(_score_frame(base_bundle, test_frame))
            base_metrics["fold_index"] = fold_index
            base_metrics["train_rows"] = int(len(train_frame))
            base_metrics["train_sessions"] = int(train_frame["session_date"].nunique())
            base_metrics["test_sessions"] = int(test_frame["session_date"].nunique())
            base_folds.append(base_metrics)

            permuted = _permute_targets(train_frame, cert_cfg.random_state + fold_index)
            permutation_bundle = _nested_model(permuted, model_cfg, features=features)
            permutation_metrics = _fold_metrics(_score_frame(permutation_bundle, test_frame))
            permutation_metrics["fold_index"] = fold_index
            permutation_folds.append(permutation_metrics)

            delayed_train = _delay_features(train_frame, features)
            delayed_test = _delay_features(test_frame, features)
            delayed_bundle = _nested_model(delayed_train, model_cfg, features=features)
            delayed_metrics = _fold_metrics(_score_frame(delayed_bundle, delayed_test))
            delayed_metrics["fold_index"] = fold_index
            delayed_folds.append(delayed_metrics)
        except Exception as exc:
            errors.append(f"fold_{fold_index}:{type(exc).__name__}:{exc}")

    base_summary = _aggregate_fold_metrics(base_folds)
    permutation_summary = _aggregate_fold_metrics(permutation_folds)
    delayed_summary = _aggregate_fold_metrics(delayed_folds)
    all_concentration = [item.get("concentration") or {} for item in base_folds]
    top_five_values = [
        float(item["top_five_positive_contribution"])
        for item in all_concentration
        if item.get("top_five_positive_contribution") is not None
    ]
    best_session_values = [
        float(item["best_session_positive_contribution"])
        for item in all_concentration
        if item.get("best_session_positive_contribution") is not None
    ]
    base_lift = base_summary.get("mean_lift_r")
    permutation_lift = permutation_summary.get("mean_lift_r")
    delayed_lift = delayed_summary.get("mean_lift_r")

    gates = {
        "all_folds_completed": len(base_folds) == cert_cfg.n_splits and not errors,
        "selected_support": base_summary.get("min_selected_rows", 0) >= cert_cfg.min_selected_per_fold,
        "positive_fold_fraction": base_summary.get("positive_expectancy_fold_fraction", 0.0) >= cert_cfg.min_positive_fold_fraction,
        "mean_lift": base_lift is not None and float(base_lift) > cert_cfg.min_mean_lift_r,
        "calibration": base_summary.get("max_ece") is not None and float(base_summary["max_ece"]) <= cert_cfg.max_ece,
        "top_five_concentration": bool(top_five_values) and max(top_five_values) <= cert_cfg.max_top_five_positive_contribution,
        "best_session_concentration": bool(best_session_values) and max(best_session_values) <= cert_cfg.max_best_session_positive_contribution,
        "permutation_control": (
            base_lift is not None
            and permutation_lift is not None
            and float(base_lift) - float(permutation_lift) >= cert_cfg.min_permutation_gap_r
        ),
        "delayed_feature_control": delayed_lift is not None and float(delayed_lift) >= cert_cfg.min_delayed_mean_lift_r,
    }
    if errors or not base_folds:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif base_lift is None or float(base_lift) <= cert_cfg.min_mean_lift_r:
        verdict = "NO_OUT_OF_SAMPLE_ML_LIFT"
    elif all(gates.values()):
        verdict = "READY_FOR_LOCKED_HOLDOUT"
    else:
        verdict = "ML_EVIDENCE_QUARANTINED"

    ablations: dict[str, Any]
    try:
        ablations = _ablation_report(
            research_df,
            model_cfg,
            cert_cfg,
            supported_train_sessions=effective_train_sessions,
        )
    except Exception as exc:
        ablations = {"error": f"{type(exc).__name__}:{exc}"}

    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "dataset_semantic_sha256": semantic_dataset_hash(research_df),
        "dataset_rows": int(len(research_df)),
        "dataset_sessions": int(research_df["session_date"].nunique()),
        "model_config": model_cfg.to_dict(),
        "certification_config": cert_cfg.to_dict(),
        "walk_forward_support": support_evidence,
        "gates": gates,
        "base_walk_forward": {"summary": base_summary, "folds": base_folds},
        "label_permutation_control": {"summary": permutation_summary, "folds": permutation_folds},
        "one_row_delayed_feature_control": {"summary": delayed_summary, "folds": delayed_folds},
        "feature_ablation": ablations,
        "errors": errors,
        "holdout_metrics_consumed": False,
        "allowed_for_paper_execution": False,
        **SAFETY_CONTRACT,
    }
