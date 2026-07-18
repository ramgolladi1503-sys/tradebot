from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategies.movement import opening_range_breakout


@dataclass(frozen=True)
class OracleSetup:
    direction: str
    proposal_ready_at_iso: str
    breakout_timestamp: str
    retest_timestamp: str
    continuation_timestamp: str
    invalidation_reason: str | None


def _is_breakout(bar: dict[str, Any], *, direction: str, orb_high: float, orb_low: float) -> bool:
    close = float(bar["close"])
    return close > orb_high if direction == "BUY_CALL" else close < orb_low


def _is_retest(bar: dict[str, Any], *, direction: str, orb_high: float, orb_low: float) -> bool:
    low = float(bar["low"])
    high = float(bar["high"])
    close = float(bar["close"])
    if direction == "BUY_CALL":
        return low <= orb_high and close >= orb_high and low > orb_low
    return high >= orb_low and close <= orb_low and high < orb_high


def _is_continuation(bar: dict[str, Any], *, direction: str, retest_bar: dict[str, Any]) -> bool:
    close = float(bar["close"])
    return close > float(retest_bar["high"]) if direction == "BUY_CALL" else close < float(retest_bar["low"])


def _is_invalidation(bar: dict[str, Any], *, direction: str, orb_high: float, orb_low: float) -> bool:
    close = float(bar["close"])
    return close < orb_high if direction == "BUY_CALL" else close > orb_low


def evaluate_oracle_direction(
    bars: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    direction: str,
) -> OracleSetup | None:
    if len(bars) < opening_range_breakout.OPENING_RANGE_BARS:
        return None
    opening_range = bars[: opening_range_breakout.OPENING_RANGE_BARS]
    orb_high = max(float(row["high"]) for row in opening_range)
    orb_low = min(float(row["low"]) for row in opening_range)
    breakout_bar: dict[str, Any] | None = None
    retest_bar: dict[str, Any] | None = None
    breakout_index: int | None = None
    retest_index: int | None = None
    invalidation_reason: str | None = None
    for index, bar in enumerate(bars[opening_range_breakout.OPENING_RANGE_BARS :], start=opening_range_breakout.OPENING_RANGE_BARS):
        while True:
            if breakout_index is not None and retest_index is None and index - breakout_index > opening_range_breakout.MAX_BREAKOUT_TO_RETEST_AGE:
                invalidation_reason = "breakout_to_retest_age_expired"
                breakout_bar = None
                breakout_index = None
                continue
            if breakout_index is not None and retest_index is not None and index - retest_index > opening_range_breakout.MAX_RETEST_TO_CONTINUATION_AGE:
                invalidation_reason = "retest_to_continuation_age_expired"
                breakout_bar = None
                retest_bar = None
                breakout_index = None
                retest_index = None
                continue
            break
        if breakout_index is None:
            if _is_breakout(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
                breakout_index = index
                breakout_bar = bar
            continue
        if retest_index is None:
            if _is_invalidation(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
                invalidation_reason = "price_returns_inside_opening_range"
                breakout_bar = None
                breakout_index = None
                continue
            if _is_retest(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
                retest_index = index
                retest_bar = bar
            continue
        if _is_invalidation(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
            invalidation_reason = "price_returns_inside_opening_range"
            breakout_bar = None
            retest_bar = None
            breakout_index = None
            retest_index = None
            continue
        if retest_bar is not None and _is_continuation(bar, direction=direction, retest_bar=retest_bar):
            return OracleSetup(
                direction=direction,
                proposal_ready_at_iso=str(bar["bar_end_timestamp"]),
                breakout_timestamp=str(breakout_bar["bar_end_timestamp"]),
                retest_timestamp=str(retest_bar["bar_end_timestamp"]),
                continuation_timestamp=str(bar["bar_end_timestamp"]),
                invalidation_reason=invalidation_reason,
            )
    return None
