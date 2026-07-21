from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RuleCondition:
    feature: str
    operator: str
    threshold: float

    def render(self) -> str:
        return f"{self.feature} {self.operator} {self.threshold:.10g}"


@dataclass(frozen=True)
class ExtractedRule:
    conditions: tuple[RuleCondition, ...]
    positive_probability: float
    support: int
    leaf_id: int

    def render(self) -> str:
        expression = (
            " AND ".join(condition.render() for condition in self.conditions)
            or "TRUE"
        )
        return (
            f"IF {expression} THEN "
            f"positive_probability={self.positive_probability:.4f} "
            f"support={self.support}"
        )


def extract_positive_leaf_rules(
    estimator,
    feature_names: Sequence[str],
    *,
    positive_class: int = 1,
    minimum_probability: float = 0.50,
    minimum_support: int = 1,
) -> tuple[ExtractedRule, ...]:
    """Extract readable positive-leaf rules from a fitted sklearn tree."""

    if not 0 <= minimum_probability <= 1:
        raise ValueError("minimum_probability must be in [0, 1]")
    if minimum_support < 1:
        raise ValueError("minimum_support must be positive")
    tree = getattr(estimator, "tree_", None)
    classes = list(getattr(estimator, "classes_", []))
    if tree is None or not classes:
        raise ValueError(
            "estimator must be a fitted sklearn decision tree classifier"
        )
    if positive_class not in classes:
        raise ValueError(f"positive class {positive_class!r} is absent")
    positive_index = classes.index(positive_class)
    if tree.n_features != len(feature_names):
        raise ValueError("feature_names does not match fitted estimator")

    rules: list[ExtractedRule] = []

    def visit(
        node_id: int,
        conditions: tuple[RuleCondition, ...],
    ) -> None:
        left = int(tree.children_left[node_id])
        right = int(tree.children_right[node_id])
        is_leaf = left == right
        if is_leaf:
            raw = tree.value[node_id]
            counts = raw[0] if getattr(raw, "ndim", 1) > 1 else raw
            total = float(sum(counts))
            probability = (
                0.0 if total <= 0 else float(counts[positive_index]) / total
            )
            support = int(tree.n_node_samples[node_id])
            if (
                probability >= minimum_probability
                and support >= minimum_support
            ):
                rules.append(
                    ExtractedRule(
                        conditions=conditions,
                        positive_probability=probability,
                        support=support,
                        leaf_id=node_id,
                    )
                )
            return

        feature_index = int(tree.feature[node_id])
        threshold = float(tree.threshold[node_id])
        if (
            feature_index < 0
            or feature_index >= len(feature_names)
            or not math.isfinite(threshold)
        ):
            raise ValueError("tree contains an invalid split")
        feature = feature_names[feature_index]
        visit(
            left,
            conditions + (RuleCondition(feature, "<=", threshold),),
        )
        visit(
            right,
            conditions + (RuleCondition(feature, ">", threshold),),
        )

    visit(0, ())
    return tuple(
        sorted(
            rules,
            key=lambda rule: (
                -rule.positive_probability,
                -rule.support,
                rule.leaf_id,
            ),
        )
    )
