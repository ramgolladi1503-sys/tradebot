from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import DiscoveryObservation


@dataclass(frozen=True)
class LabeledObservation:
    observation: DiscoveryObservation
    label: int

    def validate(self) -> None:
        self.observation.validate()
        if self.label not in (0, 1):
            raise ValueError("binary discovery label must be 0 or 1")


def build_feature_matrix(
    rows: Iterable[LabeledObservation],
) -> tuple[tuple[str, ...], list[list[float]], list[int], tuple[str, ...]]:
    """Build a deterministic matrix after enforcing one causal feature schema."""

    materialized = sorted(
        rows,
        key=lambda row: (
            row.observation.decision_at,
            row.observation.observation_id,
        ),
    )
    if not materialized:
        raise ValueError("at least one labeled observation is required")

    seen_ids: set[str] = set()
    feature_names: tuple[str, ...] | None = None
    matrix: list[list[float]] = []
    labels: list[int] = []
    observation_ids: list[str] = []

    for row in materialized:
        row.validate()
        observation = row.observation
        if observation.observation_id in seen_ids:
            raise ValueError(
                f"duplicate observation_id: {observation.observation_id}"
            )
        seen_ids.add(observation.observation_id)
        current_names = tuple(sorted(observation.features))
        if feature_names is None:
            feature_names = current_names
        elif current_names != feature_names:
            raise ValueError(
                f"inconsistent feature schema for {observation.observation_id}: "
                f"expected {feature_names}, got {current_names}"
            )
        matrix.append(
            [float(observation.features[name].value) for name in feature_names]
        )
        labels.append(row.label)
        observation_ids.append(observation.observation_id)

    assert feature_names is not None
    return feature_names, matrix, labels, tuple(observation_ids)
