"""Objective weekly bearish-structure detector for research use only.

This module deliberately does NOT implement discretionary Elliott Wave labels.
It converts the useful part of the hypothesis into a deterministic, auditable
pattern:

1. five confirmed alternating weekly pivots ending H-L-H-L-H,
2. contracting pivot-leg magnitude,
3. rising reaction lows (compression),
4. final high near/above the prior high,
5. optional bearish oscillator divergence,
6. a subsequent weekly close below the last confirmed swing low.

Pivots require right-side confirmation, so the returned signal timestamp is
never earlier than information that was actually observable.

No strategy selection, broker calls, order intent, or live authority exists here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"
STATUS_NO_SIGNAL = "NO_SIGNAL"
STATUS_CONFIRMED = "BEARISH_STRUCTURE_CONFIRMED"
SOURCE = "objective_weekly_structure_v1"


@dataclass(frozen=True)
class Pivot:
    index: int
    kind: str
    price: float
    confirmed_index: int
    oscillator: float | None = None


@dataclass(frozen=True)
class WeeklyStructureAssessment:
    status: str
    source: str
    read_only: bool
    signal_index: int | None
    signal_timestamp: Any | None
    reasons: tuple[str, ...]
    pivots: tuple[Pivot, ...]
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "read_only": self.read_only,
            "signal_index": self.signal_index,
            "signal_timestamp": self.signal_timestamp,
            "reasons": list(self.reasons),
            "pivots": [
                {
                    "index": p.index,
                    "kind": p.kind,
                    "price": p.price,
                    "confirmed_index": p.confirmed_index,
                    "oscillator": p.oscillator,
                }
                for p in self.pivots
            ],
            "metadata": dict(self.metadata),
        }


def assess_bearish_weekly_structure(
    bars: Sequence[Mapping[str, Any]],
    *,
    pivot_window: int = 2,
    max_leg_expansion: float = 1.15,
    final_leg_ratio_max: float = 0.85,
    final_high_tolerance: float = 0.01,
    break_buffer: float = 0.0,
    max_break_wait_bars: int = 8,
    oscillator_key: str = "oscillator",
) -> WeeklyStructureAssessment:
    """Assess an objective bearish topping structure from completed weekly bars.

    The detector is intentionally conservative. A pattern is not confirmed until
    a later completed weekly close breaks below the D-pivot low.
    """

    if pivot_window < 1:
        raise ValueError("pivot_window must be >= 1")
    if len(bars) < (pivot_window * 2 + 7):
        return _assessment(
            STATUS_INSUFFICIENT,
            reasons=("not_enough_weekly_bars",),
            pivots=(),
            metadata={"bar_count": len(bars), "pivot_window": pivot_window},
        )

    normalized = [_normalize_bar(row, i, oscillator_key) for i, row in enumerate(bars)]
    pivots = _confirmed_pivots(normalized, pivot_window)
    if len(pivots) < 5:
        return _assessment(
            STATUS_NO_SIGNAL,
            reasons=("fewer_than_five_confirmed_pivots",),
            pivots=tuple(pivots),
            metadata={"bar_count": len(bars), "pivot_window": pivot_window},
        )

    candidates = []
    for end in range(4, len(pivots)):
        seq = pivots[end - 4 : end + 1]
        if [p.kind for p in seq] != ["H", "L", "H", "L", "H"]:
            continue
        candidates.append(seq)

    if not candidates:
        return _assessment(
            STATUS_NO_SIGNAL,
            reasons=("no_h_l_h_l_h_sequence",),
            pivots=tuple(pivots[-5:]),
            metadata={"bar_count": len(bars), "pivot_window": pivot_window},
        )

    for seq in reversed(candidates):
        a, b, c, d, e = seq
        legs = [
            abs(a.price - b.price),
            abs(c.price - b.price),
            abs(c.price - d.price),
            abs(e.price - d.price),
        ]
        if any(x <= 0 for x in legs):
            continue

        local_contraction = all(
            later <= earlier * max_leg_expansion
            for earlier, later in zip(legs, legs[1:])
        )
        terminal_contraction = legs[-1] <= legs[0] * final_leg_ratio_max
        rising_reaction_lows = d.price > b.price
        final_high_near_prior = e.price >= c.price * (1.0 - final_high_tolerance)

        if not (
            local_contraction
            and terminal_contraction
            and rising_reaction_lows
            and final_high_near_prior
        ):
            continue

        divergence = None
        if c.oscillator is not None and e.oscillator is not None:
            divergence = e.oscillator < c.oscillator

        first_eligible_break = max(e.confirmed_index, e.index + pivot_window)
        last_eligible_break = min(
            len(normalized) - 1,
            first_eligible_break + max_break_wait_bars,
        )
        break_level = d.price * (1.0 - break_buffer)

        for i in range(first_eligible_break, last_eligible_break + 1):
            if normalized[i]["close"] < break_level:
                reasons = [
                    "confirmed_five_pivot_contraction",
                    "rising_reaction_lows",
                    "final_high_near_or_above_prior_high",
                    "weekly_close_below_last_reaction_low",
                ]
                if divergence is True:
                    reasons.append("bearish_oscillator_divergence")
                elif divergence is False:
                    reasons.append("oscillator_divergence_absent")
                else:
                    reasons.append("oscillator_not_supplied")

                return WeeklyStructureAssessment(
                    status=STATUS_CONFIRMED,
                    source=SOURCE,
                    read_only=True,
                    signal_index=i,
                    signal_timestamp=normalized[i]["timestamp"],
                    reasons=tuple(reasons),
                    pivots=tuple(seq),
                    metadata={
                        "pivot_window": pivot_window,
                        "legs": legs,
                        "break_level": break_level,
                        "divergence": divergence,
                        "max_break_wait_bars": max_break_wait_bars,
                        "research_only": True,
                        "order_authority": False,
                        "broker_write_authority": False,
                    },
                )

    return _assessment(
        STATUS_NO_SIGNAL,
        reasons=("no_candidate_passed_contraction_and_break_rules",),
        pivots=tuple(pivots[-5:]),
        metadata={
            "bar_count": len(bars),
            "pivot_window": pivot_window,
            "research_only": True,
            "order_authority": False,
            "broker_write_authority": False,
        },
    )


def _confirmed_pivots(bars: list[dict[str, Any]], window: int) -> list[Pivot]:
    raw: list[Pivot] = []
    for i in range(window, len(bars) - window):
        left = bars[i - window : i]
        right = bars[i + 1 : i + window + 1]
        high = bars[i]["high"]
        low = bars[i]["low"]

        if high > max(x["high"] for x in left) and high >= max(x["high"] for x in right):
            raw.append(
                Pivot(
                    index=i,
                    kind="H",
                    price=high,
                    confirmed_index=i + window,
                    oscillator=bars[i]["oscillator"],
                )
            )
        if low < min(x["low"] for x in left) and low <= min(x["low"] for x in right):
            raw.append(
                Pivot(
                    index=i,
                    kind="L",
                    price=low,
                    confirmed_index=i + window,
                    oscillator=bars[i]["oscillator"],
                )
            )

    raw.sort(key=lambda p: (p.index, 0 if p.kind == "H" else 1))
    out: list[Pivot] = []
    for p in raw:
        if not out or out[-1].kind != p.kind:
            out.append(p)
            continue
        previous = out[-1]
        more_extreme = p.price > previous.price if p.kind == "H" else p.price < previous.price
        if more_extreme:
            out[-1] = p
    return out


def _normalize_bar(row: Mapping[str, Any], index: int, oscillator_key: str) -> dict[str, Any]:
    try:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
    except Exception as exc:
        raise ValueError(f"invalid weekly OHLC at index {index}") from exc

    if not (high >= max(low, close) and low <= close):
        raise ValueError(f"invalid weekly OHLC geometry at index {index}")

    oscillator = row.get(oscillator_key)
    try:
        oscillator = None if oscillator is None else float(oscillator)
    except Exception:
        oscillator = None

    return {
        "high": high,
        "low": low,
        "close": close,
        "timestamp": row.get("timestamp", index),
        "oscillator": oscillator,
    }


def _assessment(
    status: str,
    *,
    reasons: tuple[str, ...],
    pivots: tuple[Pivot, ...],
    metadata: dict[str, Any],
) -> WeeklyStructureAssessment:
    return WeeklyStructureAssessment(
        status=status,
        source=SOURCE,
        read_only=True,
        signal_index=None,
        signal_timestamp=None,
        reasons=reasons,
        pivots=pivots,
        metadata=metadata,
    )


__all__ = [
    "Pivot",
    "WeeklyStructureAssessment",
    "STATUS_CONFIRMED",
    "STATUS_INSUFFICIENT",
    "STATUS_NO_SIGNAL",
    "assess_bearish_weekly_structure",
]
