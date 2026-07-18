from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from collections.abc import Mapping

from strategies.movement import opening_range_breakout


@dataclass(frozen=True)
class OracleSetup:
    symbol: str
    session_date: str
    direction: str
    boundary_type: str
    normalized_boundary_value: float
    proposal_ready_at_iso: str
    breakout_timestamp: str
    retest_timestamp: str
    continuation_timestamp: str
    setup_id: str
    invalidation_reason: str | None

    def temporal_identity(self) -> dict[str, Any]:
        return {
            "strategy_id": opening_range_breakout.STRATEGY_ID,
            "symbol": self.symbol,
            "session_date": self.session_date,
            "direction": self.direction,
            "boundary_type": self.boundary_type,
            "normalized_boundary_value": self.normalized_boundary_value,
            "breakout_timestamp": self.breakout_timestamp,
            "retest_timestamp": self.retest_timestamp,
            "continuation_timestamp": self.continuation_timestamp,
            "proposal_ready_at_iso": self.proposal_ready_at_iso,
            "setup_id": self.setup_id,
        }

    def matches_setup_identity(self, identity: Mapping[str, Any]) -> bool:
        for field, expected in self.temporal_identity().items():
            if identity.get(field) != expected:
                return False
        return True


def _boundary_type_for_direction(direction: str) -> str:
    return "ORB_HIGH" if direction == "BUY_CALL" else "ORB_LOW"


def _normalized_boundary_value_for_direction(*, direction: str, orb_high: float, orb_low: float) -> float:
    return orb_high if direction == "BUY_CALL" else orb_low


def _build_setup_id(
    *,
    symbol: str,
    session_date: str,
    direction: str,
    boundary_type: str,
    normalized_boundary_value: float,
    breakout_timestamp: str,
) -> str:
    payload = {
        "strategy_id": opening_range_breakout.STRATEGY_ID,
        "symbol": symbol,
        "session_date": session_date,
        "direction": direction,
        "boundary_type": boundary_type,
        "normalized_boundary_value": normalized_boundary_value,
        "breakout_timestamp": breakout_timestamp,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


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
    boundary_type = _boundary_type_for_direction(direction)
    normalized_boundary_value = _normalized_boundary_value_for_direction(
        direction=direction,
        orb_high=orb_high,
        orb_low=orb_low,
    )
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
            symbol = str(bar["symbol"])
            session_date = str(bar["session_date"])
            breakout_timestamp = str(breakout_bar["bar_end_timestamp"])
            return OracleSetup(
                symbol=symbol,
                session_date=session_date,
                direction=direction,
                boundary_type=boundary_type,
                normalized_boundary_value=normalized_boundary_value,
                proposal_ready_at_iso=str(bar["bar_end_timestamp"]),
                breakout_timestamp=breakout_timestamp,
                retest_timestamp=str(retest_bar["bar_end_timestamp"]),
                continuation_timestamp=str(bar["bar_end_timestamp"]),
                setup_id=_build_setup_id(
                    symbol=symbol,
                    session_date=session_date,
                    direction=direction,
                    boundary_type=boundary_type,
                    normalized_boundary_value=normalized_boundary_value,
                    breakout_timestamp=breakout_timestamp,
                ),
                invalidation_reason=invalidation_reason,
            )
    return None
