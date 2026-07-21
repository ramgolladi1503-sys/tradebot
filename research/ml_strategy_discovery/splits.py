from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


def _sessions(values: Iterable[str]) -> tuple[str, ...]:
    ordered = tuple(values)
    if not ordered:
        raise ValueError("session universe cannot be empty")
    if len(set(ordered)) != len(ordered):
        raise ValueError("session universe contains duplicates")
    if tuple(sorted(ordered)) != ordered:
        raise ValueError("session universe must be strictly chronological")
    return ordered


@dataclass(frozen=True)
class DatasetPartitionPlan:
    development: tuple[str, ...]
    validation: tuple[str, ...]
    holdout: tuple[str, ...]

    def validate(self) -> None:
        if not self.development or not self.validation or not self.holdout:
            raise ValueError(
                "development, validation, and holdout must all be non-empty"
            )
        sets = [
            set(self.development),
            set(self.validation),
            set(self.holdout),
        ]
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ValueError("dataset partitions overlap")
        combined = self.development + self.validation + self.holdout
        if tuple(sorted(combined)) != combined:
            raise ValueError("dataset partitions are not chronological")


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_sessions: tuple[str, ...]
    purge_sessions: tuple[str, ...]
    test_sessions: tuple[str, ...]

    def validate(self) -> None:
        if not self.train_sessions or not self.test_sessions:
            raise ValueError(
                "walk-forward train and test windows must be non-empty"
            )
        if set(self.train_sessions) & set(self.test_sessions):
            raise ValueError("walk-forward train and test overlap")
        combined = (
            self.train_sessions + self.purge_sessions + self.test_sessions
        )
        if tuple(sorted(combined)) != combined:
            raise ValueError("walk-forward fold is not chronological")


def make_chronological_partitions(
    sessions: Sequence[str],
    *,
    development_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> DatasetPartitionPlan:
    ordered = _sessions(sessions)
    if not 0 < development_fraction < 1:
        raise ValueError("development_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if development_fraction + validation_fraction >= 1:
        raise ValueError("fractions must leave a non-empty holdout")
    if len(ordered) < 5:
        raise ValueError("at least five sessions are required")

    development_end = max(1, int(len(ordered) * development_fraction))
    validation_end = max(
        development_end + 1,
        int(
            len(ordered)
            * (development_fraction + validation_fraction)
        ),
    )
    validation_end = min(validation_end, len(ordered) - 1)
    plan = DatasetPartitionPlan(
        development=ordered[:development_end],
        validation=ordered[development_end:validation_end],
        holdout=ordered[validation_end:],
    )
    plan.validate()
    return plan


def make_anchored_walk_forward(
    sessions: Sequence[str],
    *,
    minimum_train_sessions: int,
    test_sessions: int,
    step_sessions: int | None = None,
    purge_sessions: int = 0,
) -> tuple[WalkForwardFold, ...]:
    ordered = _sessions(sessions)
    if minimum_train_sessions < 1 or test_sessions < 1:
        raise ValueError(
            "minimum_train_sessions and test_sessions must be positive"
        )
    if purge_sessions < 0:
        raise ValueError("purge_sessions cannot be negative")
    step = test_sessions if step_sessions is None else step_sessions
    if step < 1:
        raise ValueError("step_sessions must be positive")

    folds: list[WalkForwardFold] = []
    test_start = minimum_train_sessions + purge_sessions
    fold_id = 1
    while test_start + test_sessions <= len(ordered):
        train_end = test_start - purge_sessions
        fold = WalkForwardFold(
            fold_id=fold_id,
            train_sessions=ordered[:train_end],
            purge_sessions=ordered[train_end:test_start],
            test_sessions=ordered[
                test_start : test_start + test_sessions
            ],
        )
        fold.validate()
        folds.append(fold)
        fold_id += 1
        test_start += step
    if not folds:
        raise ValueError(
            "session universe is too small for the requested walk-forward plan"
        )
    return tuple(folds)
