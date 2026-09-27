"""Independent scalar reference calculations for synthetic research fixtures.

This module intentionally contains no imports from TradeBot strategies or
indicator implementations. It is not a general strategy interpreter and does
not establish that a natural-language source rule maps to these equations.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class EmaReferenceResult:
    fast: tuple[float | None, ...]
    slow: tuple[float | None, ...]
    cross_up_indices: tuple[int, ...]


def _sma_seeded_ema(values: Sequence[float], period: int) -> tuple[float | None, ...]:
    """EMA with SMA seed, alpha=2/(period+1), and explicit warm-up N-1."""
    if period < 1:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    previous = sum(values[:period]) / period
    result[period - 1] = previous
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        previous = alpha * values[index] + (1.0 - alpha) * previous
        result[index] = previous
    return tuple(result)


def ema_cross_up_reference(
    closes: Sequence[float], *, fast_period: int, slow_period: int
) -> EmaReferenceResult:
    """Calculate a strict fast-over-slow upward cross using scalar equations.

    A cross is available only when both current and previous EMA observations
    are warm. Equality on the previous bar is allowed; equality on the current
    bar is not a cross. Prices must be finite and fast_period < slow_period.
    """
    if fast_period < 1 or slow_period < 1 or fast_period >= slow_period:
        raise ValueError("require 1 <= fast_period < slow_period")
    values = tuple(float(value) for value in closes)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("close values must be finite")
    fast = _sma_seeded_ema(values, fast_period)
    slow = _sma_seeded_ema(values, slow_period)
    events = []
    for index in range(1, len(values)):
        f0, s0 = fast[index - 1], slow[index - 1]
        f1, s1 = fast[index], slow[index]
        if None in (f0, s0, f1, s1):
            continue
        if f0 <= s0 and f1 > s1:
            events.append(index)
    return EmaReferenceResult(fast=fast, slow=slow, cross_up_indices=tuple(events))
