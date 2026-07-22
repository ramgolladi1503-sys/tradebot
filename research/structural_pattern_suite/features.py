from __future__ import annotations

from collections.abc import Sequence

from .contracts import Bar, PreviousSession


def sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def bps_return(start: float, end: float) -> float:
    if start <= 0:
        raise ValueError("start price must be positive")
    return ((end / start) - 1.0) * 10_000


def previous_range(previous: PreviousSession) -> float:
    rng = previous.range
    if rng <= 0:
        raise ValueError("previous session range must be positive")
    return rng


def gap_normalized(session_open: float, previous: PreviousSession) -> float:
    return abs(session_open - previous.close) / previous_range(previous)


def opening_return_bps(session_open: float, decision_close: float) -> float:
    return bps_return(session_open, decision_close)


def directed_leader_spread_bps(direction: int, candidate_return_bps: float, peer_return_bps: float) -> float:
    return direction * (candidate_return_bps - peer_return_bps)


def close_location(bars_from_open_to_decision: Sequence[Bar], decision_close: float) -> float:
    if not bars_from_open_to_decision:
        raise ValueError("bars_from_open_to_decision is required")
    high = max(bar.high for bar in bars_from_open_to_decision)
    low = min(bar.low for bar in bars_from_open_to_decision)
    width = high - low
    if width <= 0:
        raise ValueError("open-to-decision range must be positive")
    return (decision_close - low) / width


def directional_displacement_normalized(session_open: float, decision_close: float, previous: PreviousSession) -> float:
    return abs(decision_close - session_open) / previous_range(previous)

