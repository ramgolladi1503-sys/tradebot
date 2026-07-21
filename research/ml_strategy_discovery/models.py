from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DiscoveryModelConfig:
    max_depth: int = 4
    min_samples_leaf: int = 20
    random_state: int = 1729
    xgb_estimators: int = 250
    xgb_learning_rate: float = 0.03

    def validate(self) -> None:
        if not 1 <= self.max_depth <= 5:
            raise ValueError(
                "discovery trees must remain interpretable: "
                "max_depth must be 1-5"
            )
        if self.min_samples_leaf < 2:
            raise ValueError("min_samples_leaf must be at least 2")
        if self.xgb_estimators < 10:
            raise ValueError("xgb_estimators must be at least 10")
        if not 0 < self.xgb_learning_rate <= 0.3:
            raise ValueError("xgb_learning_rate must be in (0, 0.3]")


def _validate_training_data(
    X: Sequence[Sequence[float]],
    y: Sequence[int],
) -> None:
    if not X or len(X) != len(y):
        raise ValueError("X and y must be non-empty and have equal length")
    widths = {len(row) for row in X}
    if len(widths) != 1 or 0 in widths:
        raise ValueError("X must be a rectangular non-empty matrix")
    if set(y) - {0, 1}:
        raise ValueError("y must contain binary labels only")
    if len(set(y)) < 2:
        raise ValueError("both binary classes are required")


def fit_shallow_tree(
    X: Sequence[Sequence[float]],
    y: Sequence[int],
    *,
    config: DiscoveryModelConfig | None = None,
):
    """Fit an auditable depth-limited discovery tree.

    Caller owns chronological splitting. This function intentionally does not
    shuffle, cross-validate, inspect holdout data, persist, or activate a model.
    """

    _validate_training_data(X, y)
    cfg = config or DiscoveryModelConfig()
    cfg.validate()
    from sklearn.tree import DecisionTreeClassifier

    model = DecisionTreeClassifier(
        max_depth=cfg.max_depth,
        min_samples_leaf=cfg.min_samples_leaf,
        class_weight="balanced",
        random_state=cfg.random_state,
    )
    return model.fit(X, y)


def fit_xgboost_classifier(
    X: Sequence[Sequence[float]],
    y: Sequence[int],
    *,
    config: DiscoveryModelConfig | None = None,
):
    """Fit a deterministic CPU XGBoost discovery model without live wiring."""

    _validate_training_data(X, y)
    cfg = config or DiscoveryModelConfig()
    cfg.validate()
    from xgboost import XGBClassifier

    model = XGBClassifier(
        n_estimators=cfg.xgb_estimators,
        max_depth=cfg.max_depth,
        learning_rate=cfg.xgb_learning_rate,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=cfg.random_state,
        n_jobs=1,
        tree_method="hist",
    )
    return model.fit(X, y)
