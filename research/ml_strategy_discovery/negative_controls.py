from __future__ import annotations

import hashlib
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")


def _rank(seed_material: str, index: int, value: object) -> str:
    payload = f"{seed_material}\x1f{index}\x1f{value!r}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def deterministic_permutation(
    values: Sequence[T],
    *,
    seed_material: str,
) -> tuple[T, ...]:
    """Version-independent permutation for label-shuffle controls."""

    if not seed_material:
        raise ValueError("seed_material is required")
    ranked = sorted(
        enumerate(values),
        key=lambda item: _rank(seed_material, item[0], item[1]),
    )
    return tuple(item[1] for item in ranked)


def delayed_series(
    values: Sequence[T],
    *,
    lag: int,
    fill: T | None = None,
) -> tuple[T | None, ...]:
    if lag < 1:
        raise ValueError("lag must be at least 1")
    return tuple(
        fill if index < lag else values[index - lag]
        for index in range(len(values))
    )


def parameter_neighborhood(
    value: float,
    *,
    relative_steps: Iterable[float] = (-0.10, -0.05, 0.05, 0.10),
    lower_bound: float | None = None,
    upper_bound: float | None = None,
) -> tuple[float, ...]:
    candidates = {float(value)}
    for step in relative_steps:
        candidates.add(float(value) * (1.0 + float(step)))
    filtered = [
        candidate
        for candidate in candidates
        if (lower_bound is None or candidate >= lower_bound)
        and (upper_bound is None or candidate <= upper_bound)
    ]
    return tuple(sorted(filtered))


def randomized_entry_offsets(
    *,
    count: int,
    maximum_offset_bars: int,
    seed_material: str,
) -> tuple[int, ...]:
    if count < 1 or maximum_offset_bars < 1:
        raise ValueError("count and maximum_offset_bars must be positive")
    if not seed_material:
        raise ValueError("seed_material is required")
    result: list[int] = []
    for index in range(count):
        digest = hashlib.sha256(
            f"{seed_material}:{index}".encode("utf-8")
        ).digest()
        result.append(
            int.from_bytes(digest[:8], "big") % maximum_offset_bars + 1
        )
    return tuple(result)
