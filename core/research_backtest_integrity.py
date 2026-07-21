from __future__ import annotations

import pandas as pd


def causal_completed_htf_sma(
    close: pd.Series,
    *,
    period_minutes: int,
    window: int = 15,
) -> pd.Series:
    """Map an SMA of completed higher-timeframe closes to intraday rows.

    A row inside the currently-forming HTF bucket may only use HTF buckets that
    completed before that bucket began. Grouping by the floored bucket and
    shifting the bucket-level SMA by one enforces that contract for bar-open or
    bar-close labelled lower-timeframe rows without reading a future close from
    the same bucket.
    """
    if not isinstance(close.index, pd.DatetimeIndex):
        raise TypeError("close must use a DatetimeIndex")
    if period_minutes <= 0:
        raise ValueError("period_minutes must be positive")
    if window <= 0:
        raise ValueError("window must be positive")

    frequency = f"{int(period_minutes)}min"
    bucket_keys = close.index.floor(frequency)
    htf_close = close.groupby(bucket_keys).last()
    completed_htf_sma = htf_close.rolling(window, min_periods=window).mean().shift(1)
    return pd.Series(bucket_keys, index=close.index).map(completed_htf_sma).astype(float)


def is_immediate_next_bar(*, signal_bar_index: int, current_bar_index: int) -> bool:
    """Return whether current_bar_index is the only legal next-bar entry."""
    return int(current_bar_index) == int(signal_bar_index) + 1
