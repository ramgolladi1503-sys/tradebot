"""Exact five-minute bar ownership shared by all lead-lag research lanes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ExactBarWindow:
    cutoff: pd.Timestamp
    required_timestamps: tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]
    rows: pd.DataFrame

    @property
    def close_t_minus_10(self) -> float:
        return float(self.rows.iloc[0]["close"])

    @property
    def close_t_minus_5(self) -> float:
        return float(self.rows.iloc[1]["close"])

    @property
    def close_t(self) -> float:
        return float(self.rows.iloc[2]["close"])

    @property
    def return_5m_bps(self) -> float:
        return (self.close_t / self.close_t_minus_5 - 1.0) * 10_000.0

    @property
    def return_10m_bps(self) -> float:
        return (self.close_t / self.close_t_minus_10 - 1.0) * 10_000.0


def required_return_timestamps(cutoff: object) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    ts = pd.Timestamp(cutoff)
    if ts.tzinfo is None:
        raise ValueError("cutoff timestamp must be timezone-aware")
    ts = ts.tz_convert("UTC")
    return (ts - pd.Timedelta(minutes=10), ts - pd.Timedelta(minutes=5), ts)


def exact_bar_window(day: pd.DataFrame, cutoff: object) -> tuple[ExactBarWindow | None, tuple[str, ...]]:
    required = required_return_timestamps(cutoff)
    if day.empty:
        return None, tuple(ts.isoformat() for ts in required)
    frame = day.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("duplicate timestamps in symbol/day frame")
    indexed = frame.set_index("timestamp", drop=False)
    missing = tuple(ts.isoformat() for ts in required if ts not in indexed.index)
    if missing:
        return None, missing
    rows = indexed.loc[list(required)].reset_index(drop=True)
    return ExactBarWindow(required[-1], required, rows), ()


def symbols_with_exact_window(
    day_by_symbol: dict[str, pd.DataFrame],
    symbols: Iterable[str],
    cutoff: object,
) -> tuple[dict[str, ExactBarWindow], dict[str, tuple[str, ...]]]:
    available: dict[str, ExactBarWindow] = {}
    missing: dict[str, tuple[str, ...]] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol).upper()
        window, absent = exact_bar_window(day_by_symbol.get(symbol, pd.DataFrame()), cutoff)
        if window is None:
            missing[symbol] = absent
        else:
            available[symbol] = window
    return available, missing
