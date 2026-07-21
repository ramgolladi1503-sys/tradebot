from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from .contracts import BarrierSpec, _aware


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class BarrierOutcome(str, Enum):
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"
    NEITHER = "NEITHER"
    NO_LEGAL_ENTRY = "NO_LEGAL_ENTRY"


@dataclass(frozen=True)
class Bar:
    start: datetime
    open: float
    high: float
    low: float
    close: float

    def validate(self) -> None:
        _aware(self.start, "bar.start")
        prices = (self.open, self.high, self.low, self.close)
        if any(
            not math.isfinite(float(value)) or value <= 0 for value in prices
        ):
            raise ValueError("bar prices must be positive and finite")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("bar high is inconsistent")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("bar low is inconsistent")


@dataclass(frozen=True)
class TripleBarrierLabel:
    outcome: BarrierOutcome
    decision_at: datetime
    entry_at: datetime | None
    entry_price: float | None
    target_price: float | None
    stop_price: float | None
    terminal_at: datetime | None
    bars_observed: int
    ambiguous_same_bar: bool
    mfe: float | None
    mae: float | None


def _ordered_bars(bars: Iterable[Bar]) -> list[Bar]:
    ordered = sorted(bars, key=lambda bar: bar.start)
    previous: datetime | None = None
    for bar in ordered:
        bar.validate()
        if previous is not None and bar.start == previous:
            raise ValueError(f"duplicate bar start: {bar.start.isoformat()}")
        previous = bar.start
    return ordered


def label_triple_barrier(
    *,
    decision_at: datetime,
    bars: Iterable[Bar],
    side: Side,
    barrier: BarrierSpec,
) -> TripleBarrierLabel:
    """Label a next-bar-open trade using future bars only.

    The first legal entry bar has ``bar.start > decision_at``. When target and
    stop are both touched in one bar, the result is conservatively STOP_FIRST;
    ``ambiguous_same_bar`` remains true so it cannot be misrepresented.
    """

    _aware(decision_at, "decision_at")
    barrier.validate()
    ordered = _ordered_bars(bars)
    legal = [bar for bar in ordered if bar.start > decision_at]
    if not legal:
        return TripleBarrierLabel(
            outcome=BarrierOutcome.NO_LEGAL_ENTRY,
            decision_at=decision_at,
            entry_at=None,
            entry_price=None,
            target_price=None,
            stop_price=None,
            terminal_at=None,
            bars_observed=0,
            ambiguous_same_bar=False,
            mfe=None,
            mae=None,
        )

    entry = legal[0]
    observed = legal[: barrier.max_holding_bars]
    entry_price = float(entry.open)
    if side is Side.LONG:
        target_price = entry_price + barrier.target_distance
        stop_price = entry_price - barrier.stop_distance
    else:
        target_price = entry_price - barrier.target_distance
        stop_price = entry_price + barrier.stop_distance

    max_favorable = 0.0
    max_adverse = 0.0
    for index, bar in enumerate(observed, start=1):
        if side is Side.LONG:
            target_hit = bar.high >= target_price
            stop_hit = bar.low <= stop_price
            max_favorable = max(max_favorable, bar.high - entry_price)
            max_adverse = min(max_adverse, bar.low - entry_price)
        else:
            target_hit = bar.low <= target_price
            stop_hit = bar.high >= stop_price
            max_favorable = max(max_favorable, entry_price - bar.low)
            max_adverse = min(max_adverse, entry_price - bar.high)

        if target_hit and stop_hit:
            return TripleBarrierLabel(
                outcome=BarrierOutcome.STOP_FIRST,
                decision_at=decision_at,
                entry_at=entry.start,
                entry_price=entry_price,
                target_price=target_price,
                stop_price=stop_price,
                terminal_at=bar.start,
                bars_observed=index,
                ambiguous_same_bar=True,
                mfe=max_favorable,
                mae=max_adverse,
            )
        if stop_hit:
            outcome = BarrierOutcome.STOP_FIRST
        elif target_hit:
            outcome = BarrierOutcome.TARGET_FIRST
        else:
            continue
        return TripleBarrierLabel(
            outcome=outcome,
            decision_at=decision_at,
            entry_at=entry.start,
            entry_price=entry_price,
            target_price=target_price,
            stop_price=stop_price,
            terminal_at=bar.start,
            bars_observed=index,
            ambiguous_same_bar=False,
            mfe=max_favorable,
            mae=max_adverse,
        )

    terminal = observed[-1]
    return TripleBarrierLabel(
        outcome=BarrierOutcome.NEITHER,
        decision_at=decision_at,
        entry_at=entry.start,
        entry_price=entry_price,
        target_price=target_price,
        stop_price=stop_price,
        terminal_at=terminal.start,
        bars_observed=len(observed),
        ambiguous_same_bar=False,
        mfe=max_favorable,
        mae=max_adverse,
    )
