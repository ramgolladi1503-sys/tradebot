from __future__ import annotations

import numpy as np
import pandas as pd


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def percentile(values: np.ndarray) -> float:
        if len(values) == 0 or np.isnan(values[-1]):
            return np.nan
        valid = values[~np.isnan(values)]
        if len(valid) < max(5, window // 4):
            return np.nan
        return float(np.mean(valid <= values[-1]))

    return series.rolling(window, min_periods=max(5, window // 4)).apply(
        percentile, raw=True
    )


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    denominator = float(np.square(x_centered).sum())

    def slope(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(np.dot(values - values.mean(), x_centered) / denominator)

    return series.rolling(window, min_periods=window).apply(slope, raw=True)


def compute_causal_features(
    bars: pd.DataFrame,
    *,
    opening_range_bars: int = 15,
) -> pd.DataFrame:
    """Compute completed-bar features using no observations after each row.

    The caller must provide a timestamp-indexed, duplicate-free frame sorted in
    ascending order. Current completed-bar values are allowed; future bars are not.
    """

    frame = bars.copy()
    required = {"open", "high", "low", "close", "volume", "session_date"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing feature columns: {sorted(missing)}")

    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    open_ = frame["open"].astype(float)
    volume = frame["volume"].astype(float)
    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_14 = true_range.rolling(14, min_periods=14).mean()

    out = pd.DataFrame(index=frame.index)
    out["ret_1"] = close.pct_change(1)
    out["ret_3"] = close.pct_change(3)
    out["ret_5"] = close.pct_change(5)
    out["ret_15"] = close.pct_change(15)
    out["true_range"] = true_range
    out["atr_14"] = atr_14
    out["atr_pct_63"] = _rolling_percentile(atr_14, 63)
    out["range_norm_atr"] = (high - low) / atr_14.replace(0, np.nan)

    net_change_10 = (close - close.shift(10)).abs()
    path_10 = close.diff().abs().rolling(10, min_periods=10).sum()
    out["directional_efficiency_10"] = net_change_10 / path_10.replace(0, np.nan)
    out["trend_slope_10_atr"] = _rolling_slope(close, 10) / atr_14.replace(0, np.nan)

    rolling_high_5 = high.rolling(5, min_periods=5).max()
    rolling_low_5 = low.rolling(5, min_periods=5).min()
    rolling_high_20 = high.rolling(20, min_periods=20).max()
    rolling_low_20 = low.rolling(20, min_periods=20).min()
    out["range_expansion_5_atr"] = (
        rolling_high_5 - rolling_low_5
    ) / atr_14.replace(0, np.nan)
    out["compression_ratio_5_20"] = (
        (rolling_high_5 - rolling_low_5)
        / (rolling_high_20 - rolling_low_20).replace(0, np.nan)
    )

    previous_volume_mean_20 = volume.shift(1).rolling(20, min_periods=10).mean()
    previous_volume_mean_5 = volume.shift(1).rolling(5, min_periods=3).mean()
    out["relative_volume_20"] = volume / previous_volume_mean_20.replace(0, np.nan)
    out["volume_acceleration_5"] = volume / previous_volume_mean_5.replace(0, np.nan)
    out["volume_pct_63"] = _rolling_percentile(volume, 63)

    candle_range = (high - low).replace(0, np.nan)
    body_high = pd.concat([open_, close], axis=1).max(axis=1)
    body_low = pd.concat([open_, close], axis=1).min(axis=1)
    out["upper_wick_ratio"] = (high - body_high) / candle_range
    out["lower_wick_ratio"] = (body_low - low) / candle_range
    out["close_location_value"] = ((close - low) - (high - close)) / candle_range

    grouped = frame.groupby("session_date", sort=False)
    cumulative_value = (close * volume).groupby(frame["session_date"]).cumsum()
    cumulative_volume = volume.groupby(frame["session_date"]).cumsum()
    session_vwap = cumulative_value / cumulative_volume.replace(0, np.nan)
    out["distance_from_vwap_atr"] = (close - session_vwap) / atr_14.replace(0, np.nan)

    session_bar_index = grouped.cumcount()
    out["session_bar_index"] = session_bar_index.astype(float)

    session_first_timestamp = grouped["timestamp"].transform("min")
    out["minutes_since_open"] = (
        (frame["timestamp"] - session_first_timestamp).dt.total_seconds() / 60.0
    )
    out["session_bucket"] = pd.cut(
        out["minutes_since_open"],
        bins=[-np.inf, 60, 240, np.inf],
        labels=[0, 1, 2],
    ).astype(float)

    # The completed opening range is masked until its final constituent bar has closed.
    opening_high_all = grouped["high"].transform(
        lambda values: values.iloc[:opening_range_bars].max()
    )
    opening_low_all = grouped["low"].transform(
        lambda values: values.iloc[:opening_range_bars].min()
    )
    opening_complete = session_bar_index >= opening_range_bars - 1
    opening_high = opening_high_all.where(opening_complete)
    opening_low = opening_low_all.where(opening_complete)
    out["opening_range_width_atr"] = (
        opening_high - opening_low
    ) / atr_14.replace(0, np.nan)
    out["distance_from_opening_high_atr"] = (
        close - opening_high
    ) / atr_14.replace(0, np.nan)
    out["distance_from_opening_low_atr"] = (
        close - opening_low
    ) / atr_14.replace(0, np.nan)

    daily = (
        frame.groupby("session_date", sort=True)
        .agg(day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last"))
        .shift(1)
    )
    previous_day_high = frame["session_date"].map(daily["day_high"])
    previous_day_low = frame["session_date"].map(daily["day_low"])
    previous_day_close = frame["session_date"].map(daily["day_close"])
    previous_day_range = (previous_day_high - previous_day_low).replace(0, np.nan)
    out["previous_day_range_position"] = (
        close - previous_day_low
    ) / previous_day_range
    out["distance_from_previous_high_atr"] = (
        close - previous_day_high
    ) / atr_14.replace(0, np.nan)
    out["distance_from_previous_low_atr"] = (
        close - previous_day_low
    ) / atr_14.replace(0, np.nan)

    session_open = grouped["open"].transform("first")
    out["gap_pct"] = session_open / previous_day_close - 1.0
    out["day_of_week"] = frame["timestamp"].dt.dayofweek.astype(float)

    if "days_to_expiry" in frame.columns:
        out["days_to_expiry"] = pd.to_numeric(
            frame["days_to_expiry"], errors="coerce"
        )
        out["expiry_day_flag"] = (out["days_to_expiry"] == 0).astype(float)
    else:
        out["days_to_expiry"] = np.nan
        out["expiry_day_flag"] = np.nan

    previous_20_high = high.shift(1).rolling(20, min_periods=20).max()
    previous_20_low = low.shift(1).rolling(20, min_periods=20).min()
    breakout_up = close > previous_20_high
    breakout_down = close < previous_20_low
    out["breakout_up"] = breakout_up.astype(float)
    out["breakout_down"] = breakout_down.astype(float)
    out["breakout_distance_atr"] = np.where(
        breakout_up,
        (close - previous_20_high) / atr_14.replace(0, np.nan),
        np.where(
            breakout_down,
            (previous_20_low - close) / atr_14.replace(0, np.nan),
            0.0,
        ),
    )

    breakout_up_seen = breakout_up.shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
    breakout_down_seen = breakout_down.shift(1).rolling(5, min_periods=1).max().fillna(0).astype(bool)
    retest_up = breakout_up_seen & (low <= previous_20_high) & (close >= previous_20_high)
    retest_down = breakout_down_seen & (high >= previous_20_low) & (close <= previous_20_low)
    out["retest_after_breakout"] = (retest_up | retest_down).astype(float)
    out["failed_breakout"] = (
        (breakout_up_seen & (close < previous_20_high))
        | (breakout_down_seen & (close > previous_20_low))
    ).astype(float)

    return out.replace([np.inf, -np.inf], np.nan)
