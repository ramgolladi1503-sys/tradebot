from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .contracts import (
    SAFETY_CONTRACT,
    SCHEMA_VERSION,
    CandidateMLConfig,
    CandidatePrediction,
    PredictionStatus,
)
from .dataset import chronological_split, feature_columns, safe_float, semantic_dataset_hash, text


@dataclass
class _PlattCalibrator:
    model: LogisticRegression | None = None

    def fit(self, probabilities: np.ndarray, labels: np.ndarray) -> None:
        p = np.asarray(probabilities, dtype=float)
        y = np.asarray(labels, dtype=int)
        if len(p) != len(y) or len(p) < 20 or len(np.unique(y)) < 2:
            self.model = None
            return
        p = np.clip(p, 1e-6, 1 - 1e-6)
        logits = np.log(p / (1 - p)).reshape(-1, 1)
        model = LogisticRegression(random_state=68742, max_iter=1000)
        model.fit(logits, y)
        self.model = model

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
        if self.model is None:
            return p
        logits = np.log(p / (1 - p)).reshape(-1, 1)
        return self.model.predict_proba(logits)[:, 1]


@dataclass
class _ModelUnit:
    feature_names: list[str]
    logistic: Pipeline
    tree: HistGradientBoostingClassifier
    calibrator: _PlattCalibrator
    means: dict[str, float]
    stds: dict[str, float]
    threshold_probability: float
    train_rows: int
    positive_rows: int
    metrics: dict[str, float | None]


@dataclass
class CandidateMLBundle:
    config: CandidateMLConfig
    global_model: _ModelUnit | None = None
    strategy_models: dict[str, _ModelUnit] = field(default_factory=dict)
    trained_at_utc: str | None = None
    dataset_hash: str | None = None
    schema_version: str = SCHEMA_VERSION
    safety: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_CONTRACT))

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, out)
        return out

    @classmethod
    def load(cls, path: str | Path) -> "CandidateMLBundle":
        loaded = joblib.load(Path(path))
        if not isinstance(loaded, cls):
            raise TypeError("candidate_ml_bundle_type_mismatch")
        if loaded.schema_version != SCHEMA_VERSION:
            raise ValueError("candidate_ml_schema_version_mismatch")
        if loaded.safety.get("allowed_for_live_execution") is not False:
            raise ValueError("candidate_ml_bundle_unsafe_live_authority")
        return loaded

    def predict(self, row: Mapping[str, Any]) -> CandidatePrediction:
        strategy_id = text(row.get("strategy_id") or row.get("strategy") or "GLOBAL").upper() or "GLOBAL"
        unit = self.strategy_models.get(strategy_id) or self.global_model
        scope = strategy_id if strategy_id in self.strategy_models else "GLOBAL"
        if unit is None:
            return _prediction(PredictionStatus.MODEL_UNAVAILABLE, strategy_id, scope, reason="NO_TRAINED_MODEL")

        missing = tuple(name for name in self.config.required_features if safe_float(row.get(name)) is None)
        if len(missing) / max(1, len(self.config.required_features)) > self.config.max_missing_ratio:
            return _prediction(
                PredictionStatus.FEATURES_INCOMPLETE,
                strategy_id,
                scope,
                threshold=unit.threshold_probability,
                reason="REQUIRED_FEATURES_MISSING",
                missing=missing,
            )

        feature_row = _coerce_prediction_features(row, unit.feature_names)
        ood = _find_ood_features(feature_row.iloc[0], unit.means, unit.stds, self.config.ood_z_threshold)
        if ood:
            return _prediction(
                PredictionStatus.OUT_OF_DISTRIBUTION,
                strategy_id,
                scope,
                threshold=unit.threshold_probability,
                reason="FEATURE_DISTRIBUTION_OUTSIDE_TRAINING_SUPPORT",
                ood=tuple(ood),
            )
        if unit.train_rows < self.config.min_train_rows or unit.positive_rows < self.config.min_positive_rows:
            return _prediction(
                PredictionStatus.INSUFFICIENT_SUPPORT,
                strategy_id,
                scope,
                threshold=unit.threshold_probability,
                reason="MODEL_SUPPORT_BELOW_MINIMUM",
            )

        p_log = float(unit.logistic.predict_proba(feature_row)[:, 1][0])
        p_tree_raw = float(unit.tree.predict_proba(feature_row)[:, 1][0])
        p_tree = float(unit.calibrator.transform(np.array([p_tree_raw]))[0])
        explanation = _explain_logistic(unit, feature_row)
        if abs(p_log - p_tree) > self.config.ensemble_disagreement_threshold:
            return CandidatePrediction(
                status=PredictionStatus.MODEL_DISAGREEMENT,
                probability=None,
                raw_logistic_probability=p_log,
                raw_tree_probability=p_tree,
                expected_value_r=None,
                threshold_probability=unit.threshold_probability,
                strategy_id=strategy_id,
                model_scope=scope,
                reason_codes=("ENSEMBLE_DISAGREEMENT",),
                **explanation,
            )

        probability = float((p_log + p_tree) / 2.0)
        win_r = safe_float(row.get("average_win_r")) or self.config.default_win_r
        loss_r = safe_float(row.get("average_loss_r")) or self.config.default_loss_r
        row_cost = safe_float(row.get("cost_r"))
        cost_r = row_cost if row_cost is not None else self.config.cost_r
        expected_value_r = probability * win_r - (1 - probability) * loss_r - cost_r
        status = PredictionStatus.VALID
        reasons: tuple[str, ...] = ()
        if probability < max(self.config.probability_floor, unit.threshold_probability) or expected_value_r <= 0:
            status = PredictionStatus.BELOW_VALUE_THRESHOLD
            reasons = ("NON_POSITIVE_POST_COST_EXPECTANCY",)
        return CandidatePrediction(
            status=status,
            probability=probability,
            raw_logistic_probability=p_log,
            raw_tree_probability=p_tree,
            expected_value_r=float(expected_value_r),
            threshold_probability=unit.threshold_probability,
            strategy_id=strategy_id,
            model_scope=scope,
            reason_codes=reasons,
            missing_features=missing,
            **explanation,
        )


def _prediction(
    status: PredictionStatus,
    strategy_id: str,
    scope: str,
    *,
    threshold: float | None = None,
    reason: str,
    missing: tuple[str, ...] = (),
    ood: tuple[str, ...] = (),
) -> CandidatePrediction:
    return CandidatePrediction(
        status=status,
        probability=None,
        raw_logistic_probability=None,
        raw_tree_probability=None,
        expected_value_r=None,
        threshold_probability=threshold,
        strategy_id=strategy_id,
        model_scope=scope,
        reason_codes=(reason,),
        missing_features=missing,
        ood_features=ood,
    )


def fit_candidate_ml(df: pd.DataFrame, config: CandidateMLConfig | None = None) -> CandidateMLBundle:
    cfg = config or CandidateMLConfig()
    train, validation = chronological_split(df, cfg)
    features = feature_columns(train)
    if not features:
        raise ValueError("candidate_feature_set_empty")
    bundle = CandidateMLBundle(config=cfg)
    bundle.global_model = _fit_unit(train, validation, features, cfg)
    for strategy_id, strategy_df in df.groupby(df["strategy_id"].astype(str).str.upper()):
        if len(strategy_df) < cfg.min_strategy_rows:
            continue
        try:
            strategy_train, strategy_validation = chronological_split(strategy_df.copy(), cfg)
            bundle.strategy_models[strategy_id] = _fit_unit(strategy_train, strategy_validation, features, cfg)
        except ValueError:
            continue
    bundle.trained_at_utc = datetime.now(tz=timezone.utc).isoformat()
    bundle.dataset_hash = semantic_dataset_hash(df)
    return bundle


def _fit_unit(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    config: CandidateMLConfig,
) -> _ModelUnit:
    X_train = train[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y_train = train["target"].astype(int).to_numpy()
    X_validation = validation[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y_validation = validation["target"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2:
        raise ValueError("candidate_training_target_single_class")
    if len(np.unique(y_validation)) < 2:
        raise ValueError("candidate_validation_target_single_class")

    logistic = Pipeline([
        ("scale", StandardScaler()),
        ("model", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=config.random_state, C=0.5)),
    ])
    tree = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=max(20, len(train) // 100),
        l2_regularization=1.0,
        random_state=config.random_state,
    )
    logistic.fit(X_train, y_train)
    tree.fit(X_train, y_train)

    cut = max(20, int(len(validation) * config.calibration_fraction))
    cut = min(cut, len(validation) - 1)
    calibration_X, calibration_y = X_validation.iloc[:cut], y_validation[:cut]
    selection_X, selection_y = X_validation.iloc[cut:], y_validation[cut:]
    if len(selection_X) < 10 or len(np.unique(selection_y)) < 2:
        half = len(validation) // 2
        calibration_X, calibration_y = X_validation.iloc[:half], y_validation[:half]
        selection_X, selection_y = X_validation.iloc[half:], y_validation[half:]

    calibrator = _PlattCalibrator()
    calibrator.fit(tree.predict_proba(calibration_X)[:, 1], calibration_y)
    p_log = logistic.predict_proba(selection_X)[:, 1]
    p_tree = calibrator.transform(tree.predict_proba(selection_X)[:, 1])
    p_ensemble = (p_log + p_tree) / 2.0
    threshold = _select_value_threshold(p_ensemble, selection_y, config)
    return _ModelUnit(
        feature_names=features,
        logistic=logistic,
        tree=tree,
        calibrator=calibrator,
        means={name: float(X_train[name].mean()) for name in features},
        stds={name: float(X_train[name].std(ddof=0)) for name in features},
        threshold_probability=threshold,
        train_rows=len(train),
        positive_rows=int(np.sum(y_train)),
        metrics=_classification_metrics(selection_y, p_ensemble),
    )


def _classification_metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float | None]:
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    out: dict[str, float | None] = {
        "rows": float(len(y)),
        "brier": float(brier_score_loss(y, p)) if len(y) else None,
        "log_loss": float(log_loss(y, np.column_stack([1 - p, p]), labels=[0, 1])) if len(y) else None,
        "roc_auc": None,
    }
    if len(np.unique(y)) == 2:
        out["roc_auc"] = float(roc_auc_score(y, p))
    return out


def _select_value_threshold(probabilities: np.ndarray, labels: np.ndarray, config: CandidateMLConfig) -> float:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=int)
    best_threshold = float(config.probability_floor)
    best_value = -float("inf")
    for threshold in np.linspace(max(0.50, config.probability_floor), 0.90, 41):
        selected = p >= threshold
        if int(np.sum(selected)) < 10:
            continue
        returns = np.where(y[selected] == 1, config.default_win_r - config.cost_r, -config.default_loss_r - config.cost_r)
        score = float(np.mean(returns)) - float(np.std(returns, ddof=0)) / math.sqrt(len(returns))
        if score > best_value:
            best_value, best_threshold = score, float(threshold)
    return best_threshold


def _coerce_prediction_features(row: Mapping[str, Any], features: Sequence[str]) -> pd.DataFrame:
    values = {name: (safe_float(row.get(name)) if safe_float(row.get(name)) is not None else 0.0) for name in features}
    return pd.DataFrame([values], columns=list(features))


def _find_ood_features(row: pd.Series, means: Mapping[str, float], stds: Mapping[str, float], threshold: float) -> list[str]:
    out: list[str] = []
    for name, value in row.items():
        std = abs(float(stds.get(name, 0.0)))
        if std <= 1e-12:
            continue
        if abs((float(value) - float(means.get(name, 0.0))) / std) > threshold:
            out.append(name)
    return sorted(out)


def _explain_logistic(unit: _ModelUnit, feature_row: pd.DataFrame) -> dict[str, tuple[tuple[str, float], ...]]:
    try:
        scaler = unit.logistic.named_steps["scale"]
        model = unit.logistic.named_steps["model"]
        contributions = scaler.transform(feature_row)[0] * np.asarray(model.coef_[0], dtype=float)
        pairs = [(name, float(value)) for name, value in zip(unit.feature_names, contributions)]
        positives = tuple(sorted((item for item in pairs if item[1] > 0), key=lambda item: item[1], reverse=True)[:5])
        negatives = tuple(sorted((item for item in pairs if item[1] < 0), key=lambda item: item[1])[:5])
        return {"top_positive_features": positives, "top_negative_features": negatives}
    except Exception:
        return {"top_positive_features": (), "top_negative_features": ()}


def bundle_manifest(bundle: CandidateMLBundle) -> dict[str, Any]:
    def unit_payload(unit: _ModelUnit | None) -> dict[str, Any] | None:
        if unit is None:
            return None
        return {
            "feature_names": list(unit.feature_names),
            "threshold_probability": unit.threshold_probability,
            "train_rows": unit.train_rows,
            "positive_rows": unit.positive_rows,
            "metrics": dict(unit.metrics),
        }

    return {
        "schema_version": bundle.schema_version,
        "trained_at_utc": bundle.trained_at_utc,
        "dataset_hash": bundle.dataset_hash,
        "config": bundle.config.to_dict(),
        "global_model": unit_payload(bundle.global_model),
        "strategy_models": {key: unit_payload(value) for key, value in sorted(bundle.strategy_models.items())},
        **bundle.safety,
    }
