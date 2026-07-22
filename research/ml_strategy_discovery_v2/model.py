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
            numeric = pd.to_numeric(output[name], errors="raise").astype(float)
            output[name] = numeric.replace([np.inf, -np.inf], np.nan).fillna(
                float(value)
            )
        matrix = output.to_numpy(dtype=float)
        if not np.isfinite(matrix).all():
            raise ValueError("imputed feature matrix contains non-finite values")
        return output


def finite_training_features(
    frame: pd.DataFrame, features: Iterable[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Partition requested features using training data only.

    A feature with no finite value in the current training fold cannot receive a
    truthful training median. Such a feature is excluded from that fold's model
    search rather than assigned a fabricated constant.
    """

    names = require_causal_features(features)
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise ValueError(f"feature is missing: {missing}")
    usable: list[str] = []
    excluded: list[str] = []
    for name in names:
        numeric = pd.to_numeric(frame[name], errors="raise").astype(float)
        if np.isfinite(numeric.to_numpy(dtype=float)).any():
            usable.append(name)
        else:
            excluded.append(name)
    return tuple(usable), tuple(excluded)


def fit_imputer(frame: pd.DataFrame, features: Iterable[str]) -> FittedImputer:
    names = require_causal_features(features)
    values: dict[str, float] = {}
    for name in names:
        if name not in frame.columns:
            raise ValueError(f"feature is missing: {name}")
        numeric = pd.to_numeric(frame[name], errors="raise").astype(float)
        finite = numeric[np.isfinite(numeric.to_numpy(dtype=float))]
        median = finite.median(skipna=True)
        if pd.isna(median) or not np.isfinite(float(median)):
            raise ValueError(f"feature has no finite development median: {name}")
        values[name] = float(median)
    return FittedImputer(values=values)


def semantic_frame_hash(frame: pd.DataFrame, columns: Iterable[str]) -> str:
    names = list(columns)
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise ValueError(f"semantic hash columns missing: {missing}")
    canonical = frame.loc[:, names].copy()
    sort_columns = [
        name for name in ("decision_timestamp", "session_date") if name in canonical.columns
    ]
    if sort_columns:
        canonical = canonical.sort_values(sort_columns, kind="mergesort")
    canonical = canonical.reset_index(drop=True)
    canonical = canonical.replace([np.inf, -np.inf], np.nan)
    for name in canonical.columns:
        if pd.api.types.is_datetime64_any_dtype(canonical[name]):
            canonical[name] = canonical[name].astype(str)
    object_frame = canonical.astype(object).where(pd.notna(canonical), None)
    return canonical_hash(object_frame.to_dict(orient="records"))


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
        fill_value = float(imputation[feature])
        if not np.isfinite(fill_value):
            raise RuleReproductionError(f"imputation value is non-finite: {feature}")
        raw = pd.to_numeric(frame[feature], errors="raise").astype(float)
        nonfinite = ~np.isfinite(raw.to_numpy(dtype=float))
        nonfinite_mask = pd.Series(nonfinite, index=frame.index, dtype=bool)
        depended |= nonfinite_mask
        values = raw.mask(nonfinite_mask, fill_value)
        mask &= values <= float(threshold) if operator == "<=" else values > float(threshold)
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
    requested_feature_names = require_causal_features(features)
    required = {"session_date", target_column, *requested_feature_names}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"candidate training frame missing columns: {sorted(missing)}")
    target = pd.to_numeric(frame[target_column], errors="raise")
    if target.isna().any() or not np.isfinite(target.astype(float)).all():
        raise ValueError("candidate training target contains missing/non-finite values")
    feature_names, excluded_features = finite_training_features(
        frame, requested_feature_names
    )
    if not feature_names:
        return []
    imputer = fit_imputer(frame, feature_names)
    matrix = imputer.transform(frame, feature_names)
    labels = (target > 0).astype(int)
    if labels.nunique() < 2:
        return []
    effective_leaf = max(2, min(int(min_samples_leaf), max(2, len(frame) // 2)))
    tree_model = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=effective_leaf,
        random_state=seed,
        class_weight="balanced",
    )
    tree_model.fit(matrix, labels)
    source_leaves = tree_model.apply(matrix)
    extracted: list[tuple[int, list[dict[str, Any]]]] = []
    _extract_conditions(tree_model.tree_, feature_names, 0, [], extracted)
    dataset_hash = semantic_frame_hash(
        frame, ["session_date", target_column, *requested_feature_names]
    )
    feature_schema_hash = canonical_hash(
        {
            "requested_features": requested_feature_names,
            "usable_training_features": feature_names,
            "excluded_nonfinite_features": excluded_features,
        }
    )
    candidates: list[dict[str, Any]] = []
    seen_masks: set[str] = set()
    base_probability = float(labels.mean())
    for leaf_node_id, exact_conditions in extracted:
        leaf_mask = pd.Series(source_leaves == leaf_node_id, index=frame.index, dtype=bool)
        if not leaf_mask.any() or not exact_conditions:
            continue
        positive_probability = float(labels.loc[leaf_mask].mean())
        if positive_probability <= base_probability:
            continue
        candidate = {
            "leaf_node_id": int(leaf_node_id),
            "conditions": exact_conditions,
            "imputation_values": dict(imputer.values),
            "feature_names": list(feature_names),
            "requested_feature_names": list(requested_feature_names),
            "excluded_nonfinite_features": list(excluded_features),
            "feature_schema_hash": feature_schema_hash,
            "source_dataset_hash": dataset_hash,
            "leaf_probability": positive_probability,
            "development_rows": int(leaf_mask.sum()),
            "development_sessions": int(frame.loc[leaf_mask, "session_date"].nunique()),
            "seed": int(seed),
            "max_depth": int(max_depth),
            "min_samples_leaf": int(effective_leaf),
        }
        independent = rule_mask(frame, candidate)
        if not independent.equals(leaf_mask):
            raise RuleReproductionError(
                f"readable rule does not reproduce source leaf {leaf_node_id}"
            )
        mask_hash = canonical_hash(independent.astype(int).tolist())
        if mask_hash in seen_masks:
            continue
        seen_masks.add(mask_hash)
        candidate["selected_row_mask_hash"] = mask_hash
        candidate["rule_hash"] = canonical_hash(
            {
                "conditions": candidate["conditions"],
                "imputation_values": candidate["imputation_values"],
                "feature_schema_hash": feature_schema_hash,
            }
        )
        candidates.append(candidate)
    return sorted(candidates, key=lambda item: item["rule_hash"])
