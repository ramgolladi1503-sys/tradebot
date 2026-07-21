from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .contracts import canonical_hash


@dataclass(frozen=True)
class Fold:
    fold: int
    train_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]
    embargo_sessions: tuple[str, ...]

    @property
    def validation_start(self) -> str:
        return self.validation_sessions[0]

    @property
    def validation_end(self) -> str:
        return self.validation_sessions[-1]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validation_start"] = self.validation_start
        payload["validation_end"] = self.validation_end
        return payload


def _ordered_sessions(values: Iterable[str]) -> list[str]:
    sessions = sorted({str(value) for value in values})
    if len(sessions) < 6:
        raise ValueError("at least six sessions are required for walk-forward folds")
    return sessions


def generate_anchored_folds(
    sessions: Iterable[str],
    *,
    num_folds: int,
    embargo_sessions: int = 1,
) -> list[Fold]:
    """Create chronological anchored walk-forward folds.

    The first chunk is initial training. Every subsequent chunk is scored once using
    only earlier sessions; sessions immediately before validation are embargoed.
    """
    ordered = _ordered_sessions(sessions)
    if num_folds < 2:
        raise ValueError("num_folds must be at least two")
    if embargo_sessions < 0:
        raise ValueError("embargo_sessions cannot be negative")
    chunks = [
        list(map(str, chunk))
        for chunk in np.array_split(np.array(ordered, dtype=object), num_folds + 1)
    ]
    if any(not chunk for chunks in chunks):
        raise ValueError("too many folds for available sessions")
    folds: list[Fold] = []
    for index in range(1, len(chunks)):
        validation = chunks[index]
        earlier = [session for chunk in chunks[:index] for session in chunk]
        embargo_count = min(embargo_sessions, max(0, len(earlier) - 1))
        embargo = earlier[-embargo_count:] if embargo_count else []
        train = earlier[:-embargo_count] if embargo_count else earlier
        if not train:
            raise ValueError("fold has no training sessions after embargo")
        if set(train) & set(validation) or set(embargo) & set(validation):
            raise AssertionError("fold session isolation failed")
        if max(train) >= min(validation):
            raise AssertionError("walk-forward fold includes future training sessions")
        folds.append(
            Fold(
                fold=index,
                train_sessions=tuple(train),
                validation_sessions=tuple(validation),
                embargo_sessions=tuple(embargo),
            )
        )
    return folds


def generate_nested_folds(
    frame: pd.DataFrame,
    *,
    outer_folds: int = 5,
    inner_folds: int = 4,
    embargo_sessions: int = 1,
) => list[dict[str, Any]]:
    if "session_date" not in frame.columns:
        raise ValueError("session_date is required")
    outer = generate_anchored_folds(
        frame["session_date"].astype(str),
        num_folds=outer_folds,
        embargo_sessions=embargo_sessions,
    )
    output: list[dict[str, Any]] = []
    for outer_fold in outer:
        maximum_inner = min(inner_folds, max(2, len(outer_fold.train_sessions) // 3))
        inner = generate_anchored_folds(
            outer_fold.train_sessions,
            num_folds=maximum_inner,
            embargo_sessions=embargo_sessions,
        )
        output.append(
            {
                "outer": outer_fold.to_dict(),
                "inner": [fold.to_dict() for fold in inner],
            }
        )
    return output


def fold_manifest_hash(folds: list[dict[str, Any]]) -> str:
    return canonical_hash(folds)
