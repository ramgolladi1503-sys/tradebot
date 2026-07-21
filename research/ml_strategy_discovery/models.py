from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import precision_score, roc_auc_score
from sklearn.tree import DecisionTreeClassifier, _tree

from .contracts import (
    FEATURE_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    DiscoveryConfig,
    FeatureImputation,
    RuleCondition,
    StrategyCandidate,
)
from .dataset import model_feature_names, semantic_dataset_hash
from .evaluation import candidate_mask


@dataclass
class DiscoveryArtifacts:
    feature_names: tuple[str, ...]
    imputer: SimpleImputer
    shallow_tree: DecisionTreeClassifier
    xgboost_model: Any | None
    validation_metrics: dict[str, float | int | None]
    candidates: tuple[StrategyCandidate, ...]
    feature_importance: tuple[dict[str, float | str], ...]


def _binary_target(frame: pd.DataFrame) -> np.ndarray:
    return (frame["barrier_outcome"] == "TARGET_FIRST").astype(int).to_numpy()


def _candidate_id(side: str, conditions: list[RuleCondition]) -> str:
    raw = side.upper() + "|" + "|".join(
        f"{condition.feature}{condition.operator}{condition.threshold:.10g}"
        for condition in conditions
    )
    return "tree_rule_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def extract_tree_candidates(
    tree: DecisionTreeClassifier,
    *,
    feature_names: tuple[str, ...],
    imputation_statistics: np.ndarray,
    development: pd.DataFrame,
    development_matrix: np.ndarray,
    config: DiscoveryConfig,
    minimum_leaf_rows: int = 30,
    minimum_leaf_probability: float = 0.55,
    maximum_candidates: int = 10,
) -> tuple[StrategyCandidate, ...]:
    structure = tree.tree_
    candidates: list[StrategyCandidate] = []
    development_leaf_ids = tree.apply(development_matrix)
    source_dataset_hash = semantic_dataset_hash(development)
    imputation_by_feature = {
        name: float(imputation_statistics[index])
        for index, name in enumerate(feature_names)
    }

    def visit(node_id: int, conditions: list[RuleCondition]) -> None:
        feature_index = structure.feature[node_id]
        if feature_index == _tree.TREE_UNDEFINED:
            if not conditions:
                return
            samples = int(structure.n_node_samples[node_id])
            values = structure.value[node_id][0]
            total = float(values.sum())
            probability = (
                float(values[1] / total)
                if total > 0 and len(values) > 1
                else 0.0
            )
            if samples < minimum_leaf_rows or probability < minimum_leaf_probability:
                return
            condition_features = tuple(dict.fromkeys(item.feature for item in conditions))
            candidate = StrategyCandidate(
                candidate_id=_candidate_id(config.label_side, conditions),
                conditions=tuple(conditions),
                target_atr=config.target_atr,
                stop_atr=config.stop_atr,
                maximum_holding_bars=config.barrier_horizon_bars,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                label_schema_version=LABEL_SCHEMA_VERSION,
                discovery_start=str(development["decision_timestamp"].min()),
                discovery_end=str(development["decision_timestamp"].max()),
                discovery_rows=samples,
                discovery_sessions=int(
                    development.loc[
                        development_leaf_ids == node_id, "session_date"
                    ].nunique()
                ),
                leaf_probability=probability,
                leaf_node_id=int(node_id),
                label_side=config.label_side.upper(),
                source_dataset_hash=source_dataset_hash,
                imputation_values=tuple(
                    FeatureImputation(
                        feature=feature,
                        value=imputation_by_feature[feature],
                    )
                    for feature in condition_features
                ),
            )
            candidates.append(candidate)
            return

        feature = feature_names[feature_index]
        threshold = float(structure.threshold[node_id])
        visit(
            structure.children_left[node_id],
            conditions + [RuleCondition(feature, "<=", threshold)],
        )
        visit(
            structure.children_right[node_id],
            conditions + [RuleCondition(feature, ">", threshold)],
        )

    visit(0, [])
    candidates.sort(
        key=lambda candidate: (
            candidate.leaf_probability,
            candidate.discovery_rows,
        ),
        reverse=True,
    )
    return tuple(candidates[:maximum_candidates])


def _assert_candidate_leaf_reproduction(
    *,
    development: pd.DataFrame,
    development_matrix: np.ndarray,
    tree: DecisionTreeClassifier,
    candidates: tuple[StrategyCandidate, ...],
) -> None:
    leaf_ids = tree.apply(development_matrix)
    for candidate in candidates:
        expected = pd.Series(
            leaf_ids == candidate.leaf_node_id,
            index=development.index,
        )
        observed = candidate_mask(development, candidate)
        if not expected.equals(observed):
            disagreement = int((expected != observed).sum())
            raise AssertionError(
                "extracted candidate does not reproduce its source tree leaf: "
                f"candidate={candidate.candidate_id} disagreements={disagreement}"
            )


def train_discovery_models(
    split_dataset: pd.DataFrame,
    *,
    config: DiscoveryConfig | None = None,
    max_tree_depth: int = 4,
    minimum_leaf_rows: int = 30,
) -> DiscoveryArtifacts:
    """Fit on DEVELOPMENT and score VALIDATION without fitting on holdout rows."""

    config = config or DiscoveryConfig()
    if "split" not in split_dataset.columns:
        raise ValueError("chronological split column is required")
    development = split_dataset.loc[
        split_dataset["split"] == "DEVELOPMENT"
    ].copy()
    validation = split_dataset.loc[
        split_dataset["split"] == "VALIDATION"
    ].copy()
    if development.empty or validation.empty:
        raise ValueError("development and validation partitions are required")

    feature_names = tuple(
        name
        for name in model_feature_names(split_dataset)
        if development[name].notna().any()
        and development[name].nunique(dropna=True) > 1
    )
    if not feature_names:
        raise ValueError("no numeric discovery features available")

    imputer = SimpleImputer(strategy="median")
    x_development = imputer.fit_transform(development.loc[:, feature_names])
    x_validation = imputer.transform(validation.loc[:, feature_names])
    y_development = _binary_target(development)
    y_validation = _binary_target(validation)
    if len(np.unique(y_development)) < 2:
        raise ValueError("development target must contain both classes")

    shallow_tree = DecisionTreeClassifier(
        max_depth=max_tree_depth,
        min_samples_leaf=minimum_leaf_rows,
        class_weight="balanced",
        random_state=config.random_seed,
    )
    shallow_tree.fit(x_development, y_development)
    tree_probability = shallow_tree.predict_proba(x_validation)[:, 1]

    xgboost_model = None
    xgb_probability: np.ndarray | None = None
    try:
        import xgboost as xgb

        xgboost_model = xgb.XGBClassifier(
            n_estimators=60,
            max_depth=3,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=config.random_seed,
            eval_metric="logloss",
            n_jobs=1,
            tree_method="hist",
        )
        xgboost_model.fit(x_development, y_development)
        xgb_probability = xgboost_model.predict_proba(x_validation)[:, 1]
    except ImportError:
        xgboost_model = None

    metrics: dict[str, float | int | None] = {
        "development_rows": int(len(development)),
        "validation_rows": int(len(validation)),
        "holdout_rows_excluded_from_fit_and_score": int(
            (split_dataset["split"] == "HOLDOUT_LOCKED").sum()
        ),
        "tree_validation_auc": (
            float(roc_auc_score(y_validation, tree_probability))
            if len(np.unique(y_validation)) == 2
            else None
        ),
        "tree_validation_precision_at_0_55": float(
            precision_score(
                y_validation,
                tree_probability >= 0.55,
                zero_division=0,
            )
        ),
        "xgb_validation_auc": (
            float(roc_auc_score(y_validation, xgb_probability))
            if xgb_probability is not None and len(np.unique(y_validation)) == 2
            else None
        ),
        "xgb_validation_precision_at_0_55": (
            float(
                precision_score(
                    y_validation,
                    xgb_probability >= 0.55,
                    zero_division=0,
                )
            )
            if xgb_probability is not None
            else None
        ),
    }

    candidates = extract_tree_candidates(
        shallow_tree,
        feature_names=feature_names,
        imputation_statistics=imputer.statistics_,
        development=development,
        development_matrix=x_development,
        config=config,
        minimum_leaf_rows=minimum_leaf_rows,
    )
    _assert_candidate_leaf_reproduction(
        development=development,
        development_matrix=x_development,
        tree=shallow_tree,
        candidates=candidates,
    )

    tree_importance = shallow_tree.feature_importances_
    xgb_importance = (
        xgboost_model.feature_importances_
        if xgboost_model is not None
        else np.zeros(len(feature_names), dtype=float)
    )
    importance = tuple(
        sorted(
            (
                {
                    "feature": name,
                    "tree_importance": float(tree_importance[index]),
                    "xgb_importance": float(xgb_importance[index]),
                }
                for index, name in enumerate(feature_names)
            ),
            key=lambda row: (
                row["xgb_importance"],
                row["tree_importance"],
            ),
            reverse=True,
        )
    )

    return DiscoveryArtifacts(
        feature_names=feature_names,
        imputer=imputer,
        shallow_tree=shallow_tree,
        xgboost_model=xgboost_model,
        validation_metrics=metrics,
        candidates=candidates,
        feature_importance=importance,
    )
