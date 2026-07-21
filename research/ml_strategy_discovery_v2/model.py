from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

from .contracts import canonical_hash, require_causal_features


class RuleReproductionError(ValueError):
    """Raised when a readable rule does not reproduce its source leaf."""


@dataclass(frozen=True)
class FittedImputer:
    values: dict[str, float]

    def transform(self, frame: pd.DataFrame, features: Iterable[str]) -> pd.DataFrame:
        names = require_causal_features(features)
        missing = [name for name in names if name not in frame.columns]
        if missing:
            raise ValueError(f"candidate features missing from frame: {missing}")
        output = frame.loc[:, names].copy()
        for name in names:
            value = self.values.get(name)
            if value is None or not np.isfinite(float(value)):
                raise ValueError(f"imputation value is missing or non-finite: {name}")
            output[name] = pd.to_numeric(output[name], errors="raise").fillna(
                float(value)
            )
        values = output.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("imputed feature matrix contains non-finite values")
        return output


def fit_imputer(frame: pd.DataFrame, features: Iterable[str]) -> FittedImputer:
    names = require_causal_features(features)
    values: dict[str, float] = {}
    for name in names:
        if name not in frame.columns:
            raise ValueError(f"feature is missing: {name}")
        numeric = pd.to_numeric(frame[name], errors="raise")
        median = numeric.median(skipna=True)
        if pd.isna(median) or not np.isfinite(float(median)):
            raise ValueError(f"feature has no finite development median: {name}")
        values[name] = float(median)
    return FittedImputer(values=values)


def semantic_frame_hash(frame: pd.DataFrame, columns: Iterable[str]) -> str:
    names = list(columns)
    canonical = frame.loc[:, names].copy()
    if "decision_timestamp" in canonical.columns:
        canonical = canonical.sort_values("decision_timestamp", kind="mergesort")
    elif "session_date" in canonical.columns:
        canonical = canonical.sort_values("session_date", kind="mergesort")
    for name in canonical.columns:
        if pd.api.types.is_datetime64_any_dtype(canonical[name]):
            canonical[name] = canonical[name].astype(str)
    records = canonical.where(pd.notna(canonical), None).to_dict(orient="records")
    return canonical_hash(records)


def rule_mask(
    frame: pd.DataFrame,
    candidate: dict[str, Any],
    *,
    return_imputation_dependency: bool = False,
) -> pd.Series | tuple[pd.Series, pd.Series]:
    conditions = candidate.get("conditions")
    imputation = candidate.get("imputation_values")
    if not isinstance(conditions, list) or not conditions:
        raise RuleReproductionError("candidate conditions are required")
    if not isinstance(imputation, dict):
        raise RuleReproductionError("candidate imputation values are required")
    mask = pd.Series(True, index=frame.index, dtype=bool)
    depended = pd.Series(False, index=frame.index, dtype=bool)
    for condition in conditions:
        feature = str(condition.get("feature") or "")
        operator = str(condition.get("operator") or "")
        threshold = condition.get("threshold")
        if feature not in frame.columns:
            raise RuleReproductionError(f"candidate feature missing: {feature}")
        if operator not in {"<=", ">"}:
            raise RuleReproductionError(f"unsupported operator: {operator}")
        if not isinstance(threshold, (int, float)) or not np.isfinite(float(threshold)):
            raise RuleReproductionError("condition threshold must be finite")
        if feature not in imputation:
            raise RuleReproductionError(
                f"imputation map does not cover feature: {feature}"
            )
        raw = pd.to_numeric(frame[feature], errors="raise")
        depended |= raw.isna()
        values = raw.fillna(float(imputation[feature]))
        if operator == "<=":
            mask &= values <= float(threshold)
        else:
            mask &= values > float(threshold)
    if return_imputation_dependency:
        return mask, depended & mask
    return mask


def _extract_conditions(
    tree: Any,
    feature_names: tuple[str, ...],
    node_id: int,
    conditions: list[dict[str, Any]],
    output: list[tuple[int, list[dict[str, Any]]]],
) -> None:
    left = int(tree.children_left[node_id])
    right = int(tree.children_right[node_id])
    if left == right:
        output.append((node_id, list(conditions)))
        return
    feature = feature_names[int(tree.feature[node_id])]
    threshold = float(tree.threshold[node_id])
    _extract_conditions(
        tree,
        feature_names,
        left,
        conditions + [{"feature": feature, "operator": "<=", "threshold": threshold}],
        output,
    )
    _extract_conditions(
        tree,
        feature_names,
        right,
        conditions + [{"feature": feature, "operator": ">", "threshold": threshold}],
        output,
    )


def generate_candidates(
    frame: pd.DataFrame,
    *,
    features: Iterable[str],
    target_column: str = "label_return_r",
    max_depth: int = 3,
    min_samples_leaf: int = 50,
    seed: int = 42,
) -> list[dict[str, Any]]:
    feature_names = require_causal_features(features)
    if target_column not in frame.columns:
        raise ValueError(f"target column is missing: {target_column}")
    target = pd.to_numeric(frame[target_column], errors="raise")
    if target.isna().any():
        raise ValueError("candidate training target contains missing values")
    imputer = fit_imputer(frame, feature_names)
    matrix = imputer.transform(frame, feature_names)
    labels = (target > 0).astype(int)
    if labels.nunique() < 2:
        return []
    tree_model = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=seed,
        class_weight="balanced",
    )
    tree_model.fit(matrix, labels)
    source_leaves = tree_model.apply(matrix)
    extracted: list[tuple[int, list[dict[str, Any]]]] = []
    _extract_conditions(tree_model.tree_, feature_names, 0, [], extracted)
    dataset_hash = semantic_frame_hash(
        frame,
        ["session_date", target_column, *feature_names],
    )
    feature_schema_hash = canonical_hash(feature_names)
    candidates: list[dict[str, Any]] = []
    seen_masks: set[str] = set()
    for leaf_node_id, exact_conditions in extracted:
        leaf_mask = pd.Series(source_leaves == leaf_node_id, index=frame.index)
        if not leaf_mask.any():
            continue
        leaf_labels = labels.loc[leaf_mask]
        positive_probability = float(leaf_labels.mean())
        if positive_probability <= float(labels.mean()):
            continue
        rounded_conditions = [
            {**condition, "threshold": round(float(condition["threshold"]), 12)}
            for condition in exact_conditions
        ]
        candidate = {
            "leaf_node_id": int(leaf_node_id),
            "conditions": rounded_conditions,
            "imputation_values": dict(imputer.values),
            "feature_names": list(feature_names),
            "feature_schema_hash": feature_schema_hash,
            "source_dataset_hash": dataset_hash,
            "leaf_probability": positive_probability,
            "development_rows": int(leaf_mask.sum()),
            "development_sessions": int(frame.loc[leaf_mask, "session_date"].nunique()),
            "seed": int(seed),
            "max_depth": int(max_depth),
            "min_samples_leaf": int(min_samples_leaf),
        }
        independent = rule_mask(frame, candidate)
        if not independent.equals(leaf_mask):
            raise RuleReproductionError(
                f"rounded readable rule does not reproduce source leaf {leaf_node_id}"
            )
        mask_hash = canonical_hash(independent.astype(int).tolist())
        if mask_hash in seen_masks:
            continue
        seen_masks.add(mask_hash)
        candidate["selected_row_mask_hash"] = mask_hash
        candidate["rule_hash"] = canonical_hash(
            {
                "conditions": rounded_conditions,
                "imputation_values": candidate["imputation_values"],
                "feature_schema_hash": feature_schema_hash,
            }
        )
        candidates.append(candidate)
    return sorted(candidates, key=lambda item: item["rule_hash"])
