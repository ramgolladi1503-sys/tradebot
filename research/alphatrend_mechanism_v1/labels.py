"""Exact-time forward labels for one-minute intraday research."""
from __future__ import annotations

from typing import Iterable

import pandas as pd


def add_forward_labels(
    frame: pd.DataFrame,
    horizons: Iterable[int] = (5, 10, 15, 20, 30),
) -> pd.DataFrame:
    """Add exact-clock same-session forward outcomes.

    Each horizon is interpreted as minutes, not merely rows. A label is valid
    only if every expected one-minute timestamp through the horizon exists in
    the same trading session. Provider omissions therefore produce NaN instead
    of silently stretching a 15-minute label into 16+ minutes.
    """
    required = {"timestamp", "session_date", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    horizons_tuple = tuple(sorted({int(h) for h in horizons}))
    if not horizons_tuple or horizons_tuple[0] < 1:
        raise ValueError("horizons must contain positive integer minutes")

    df = frame.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    df["session_date"] = df["session_date"].astype(str)
    for column in ("high", "low", "close"):
        df[column] = pd.to_numeric(df[column], errors="raise")
    df["_source_order"] = range(len(df))
    df = df.sort_values(["session_date", "timestamp", "_source_order"]).reset_index(drop=True)
    if df.duplicated(["session_date", "timestamp"]).any():
        raise ValueError("duplicate timestamp within session")

    parts: list[pd.DataFrame] = []
    for _, group in df.groupby("session_date", sort=False):
        g = group.copy()
        time_index = pd.DatetimeIndex(g["timestamp"])
        close_by_time = pd.Series(g["close"].to_numpy(), index=time_index)
        high_by_time = pd.Series(g["high"].to_numpy(), index=time_index)
        low_by_time = pd.Series(g["low"].to_numpy(), index=time_index)

        for horizon in horizons_tuple:
            target_times = time_index + pd.Timedelta(minutes=horizon)
            future_close = pd.Series(
                close_by_time.reindex(target_times).to_numpy(),
                index=g.index,
            )

            expected_highs: list[pd.Series] = []
            expected_lows: list[pd.Series] = []
            for minute in range(1, horizon + 1):
                minute_times = time_index + pd.Timedelta(minutes=minute)
                expected_highs.append(
                    pd.Series(high_by_time.reindex(minute_times).to_numpy(), index=g.index)
                )
                expected_lows.append(
                    pd.Series(low_by_time.reindex(minute_times).to_numpy(), index=g.index)
                )

            high_matrix = pd.concat(expected_highs, axis=1)
            low_matrix = pd.concat(expected_lows, axis=1)
            complete_path = high_matrix.notna().all(axis=1) & low_matrix.notna().all(axis=1)

            # A valid endpoint is not enough: every intervening minute must be
            # present, otherwise the entire horizon is excluded.
            future_close = future_close.where(complete_path)
            future_high = high_matrix.max(axis=1, skipna=False).where(complete_path)
            future_low = low_matrix.min(axis=1, skipna=False).where(complete_path)
            g[f"fwd_ret_{horizon}_bps"] = (future_close / g["close"] - 1.0) * 10000.0
            g[f"fwd_high_{horizon}_bps"] = (future_high / g["close"] - 1.0) * 10000.0
            g[f"fwd_low_{horizon}_bps"] = (future_low / g["close"] - 1.0) * 10000.0

        parts.append(g)

    out = pd.concat(parts, axis=0).sort_values("_source_order")
    return out.drop(columns=["_source_order"]).reset_index(drop=True)


__all__ = ["add_forward_labels"]
