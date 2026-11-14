"""Effective-sample accounting for overlapping forward-return horizons."""
from __future__ import annotations

from typing import Iterable

import pandas as pd


def evaluate_nonoverlap(
    frame: pd.DataFrame,
    signal_column: str,
    horizons: Iterable[int] = (15, 30),
) -> dict[str, object]:
    """Evaluate a signal using same-session, non-overlapping clock windows.

    Raw event counts can badly overstate evidence when several signals occur
    inside the same 15- or 30-minute outcome window. For each requested horizon,
    this function greedily keeps the first valid event in a session and then
    suppresses later events until the prior clock-time outcome window elapsed.

    This is deliberately conservative. It is not a substitute for session/block
    bootstrap inference, but it prevents a dense trend episode from being
    counted as many independent observations during development screening.
    """
    if signal_column not in frame.columns:
        raise KeyError(signal_column)
    required = {"timestamp", "session_date"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    df = frame.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
    df["session_date"] = df["session_date"].astype(str)
    df = df.sort_values(["session_date", "timestamp"]).reset_index(drop=True)
    if df.duplicated(["session_date", "timestamp"]).any():
        raise ValueError("duplicate timestamp within session")

    signal = pd.to_numeric(df[signal_column], errors="coerce").fillna(0).astype(int)
    result: dict[str, object] = {"signal": signal_column, "horizons": {}}

    for horizon in tuple(sorted({int(h) for h in horizons})):
        if horizon < 1:
            raise ValueError("horizons must be positive integer minutes")
        return_column = f"fwd_ret_{horizon}_bps"
        if return_column not in df.columns:
            raise KeyError(return_column)

        valid_mask = signal.ne(0) & df[return_column].notna()
        events = df.loc[
            valid_mask,
            ["timestamp", "session_date", return_column],
        ].copy()
        events["_signal"] = signal.loc[valid_mask].to_numpy()

        selected_indices: list[int] = []
        minimum_gap = pd.Timedelta(minutes=horizon)
        for _, session_events in events.groupby("session_date", sort=False):
            last_kept_time: pd.Timestamp | None = None
            for idx, row in session_events.iterrows():
                timestamp = pd.Timestamp(row["timestamp"])
                if last_kept_time is None or timestamp - last_kept_time >= minimum_gap:
                    selected_indices.append(idx)
                    last_kept_time = timestamp

        selected = events.loc[selected_indices].copy() if selected_indices else events.iloc[0:0].copy()
        directional_return = selected["_signal"] * selected[return_column]

        session_share = _largest_share(selected["session_date"])
        month_share = _largest_share(selected["timestamp"].dt.to_period("M").astype(str))
        result["horizons"][str(horizon)] = {
            "raw_valid_n": int(len(events)),
            "nonoverlap_n": int(len(selected)),
            "sessions": int(selected["session_date"].nunique()),
            "mean_directional_bps": _finite_or_none(directional_return.mean()),
            "median_directional_bps": _finite_or_none(directional_return.median()),
            "hit_rate": _finite_or_none((directional_return > 0).mean()),
            "max_session_event_share": session_share,
            "max_month_event_share": month_share,
        }

    return result


def _largest_share(values: pd.Series) -> float | None:
    if values.empty:
        return None
    counts = values.value_counts(dropna=False)
    if counts.empty:
        return None
    return float(counts.max() / counts.sum())


def _finite_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


__all__ = ["evaluate_nonoverlap"]
