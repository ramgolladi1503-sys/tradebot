from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarketStateConfig:
    timestamp_col: str = "timestamp"
    session_col: str = "session_date"
    close_col: str = "close"
    high_col: str = "high"
    low_col: str = "low"
    open_col: str = "open"
    volume_col: str = "volume"
    option_close_col: str = "option_close"
    option_volume_col: str = "option_volume"
    vwap_col: str = "vwap"
    short_window: int = 5
    medium_window: int = 15
    long_window: int = 30
    min_periods: int = 5


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator / denominator


def _rolling_slope(values: pd.Series, window: int, min_periods: int) -> pd.Series:
    def slope(chunk: np.ndarray) -> float:
        y = np.asarray(chunk, dtype=float)
        if np.isnan(y).any() or len(y) < 2:
            return np.nan
        x = np.arange(len(y), dtype=float)
        return float(np.polyfit(x, y, 1)[0])

    return values.rolling(window, min_periods=min_periods).apply(slope, raw=True)


def _path_efficiency(close: pd.Series, window: int, min_periods: int) -> pd.Series:
    displacement = close.diff(window).abs()
    path = close.diff().abs().rolling(window, min_periods=min_periods).sum()
    return _safe_div(displacement, path).clip(0.0, 1.0)


def _rolling_zscore(values: pd.Series, window: int, min_periods: int) -> pd.Series:
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std(ddof=0)
    return _safe_div(values - mean, std)


def _require_columns(frame: pd.DataFrame, required: set[str]) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required market-state columns: {missing}")


def state_contract(config: MarketStateConfig | None = None) -> dict[str, Any]:
    cfg = config or MarketStateConfig()
    return {
        "version": "causal_market_state_v1",
        "config": asdict(cfg),
        "timestamp_semantics": "all states at row t use row t and earlier completed bars only",
        "families": {
            "trend": [
                "trend_return_short",
                "trend_return_medium",
                "trend_slope_medium",
                "trend_path_efficiency",
                "trend_directional_ratio",
                "trend_vwap_residence",
            ],
            "compression_expansion": [
                "range_short_long_ratio",
                "realized_vol_short_long_ratio",
                "bar_overlap_ratio",
                "range_zscore",
            ],
            "balance_imbalance": [
                "vwap_distance_atr",
                "vwap_cross_frequency",
                "close_location_value",
                "directional_efficiency_signed",
            ],
            "acceptance_rejection": [
                "above_vwap_dwell",
                "below_vwap_dwell",
                "upper_rejection_wick",
                "lower_rejection_wick",
            ],
            "participation": [
                "volume_zscore",
                "range_per_volume",
                "directional_participation",
            ],
            "option_responsiveness": [
                "option_return_short",
                "option_elasticity_short",
                "option_response_consistency",
                "option_volume_zscore",
            ],
            "absorption_exhaustion_proxies": [
                "failed_progress_up",
                "failed_progress_down",
                "impulse_exhaustion_up",
                "impulse_exhaustion_down",
            ],
            "quality": [
                "underlying_observable",
                "option_observable",
                "state_reliability",
            ],
        },
    }


def build_market_state_frame(
    frame: pd.DataFrame,
    config: MarketStateConfig | None = None,
) -> pd.DataFrame:
    """Return a causal descriptive state frame.

    The input must already be sorted-compatible completed bars. The function sorts by
    session and timestamp, never shifts features backwards, and preserves row identity.
    Missing optional option columns produce explicit observability flags and NaN states.
    """

    cfg = config or MarketStateConfig()
    required = {
        cfg.timestamp_col,
        cfg.close_col,
        cfg.high_col,
        cfg.low_col,
        cfg.open_col,
        cfg.volume_col,
    }
    _require_columns(frame, required)

    out = frame.copy()
    out[cfg.timestamp_col] = pd.to_datetime(out[cfg.timestamp_col], utc=True, errors="raise")
    if cfg.session_col not in out.columns:
        out[cfg.session_col] = out[cfg.timestamp_col].dt.date.astype(str)
    out = out.sort_values([cfg.session_col, cfg.timestamp_col], kind="mergesort").reset_index(drop=True)

    def per_session(group: pd.DataFrame) -> pd.DataFrame:
        g = group.copy()
        close = pd.to_numeric(g[cfg.close_col], errors="coerce")
        high = pd.to_numeric(g[cfg.high_col], errors="coerce")
        low = pd.to_numeric(g[cfg.low_col], errors="coerce")
        open_ = pd.to_numeric(g[cfg.open_col], errors="coerce")
        volume = pd.to_numeric(g[cfg.volume_col], errors="coerce")
        true_range = high - low
        returns = close.pct_change()

        if cfg.vwap_col in g.columns:
            vwap = pd.to_numeric(g[cfg.vwap_col], errors="coerce")
        else:
            typical = (high + low + close) / 3.0
            cumulative_volume = volume.fillna(0).cumsum().replace(0, np.nan)
            vwap = (typical * volume.fillna(0)).cumsum() / cumulative_volume

        atr_long = true_range.rolling(cfg.long_window, min_periods=cfg.min_periods).mean()
        body = close - open_
        upper_wick = high - pd.concat([open_, close], axis=1).max(axis=1)
        lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low

        g["trend_return_short"] = close.pct_change(cfg.short_window)
        g["trend_return_medium"] = close.pct_change(cfg.medium_window)
        g["trend_slope_medium"] = _safe_div(
            _rolling_slope(close, cfg.medium_window, cfg.min_periods), close
        )
        g["trend_path_efficiency"] = _path_efficiency(close, cfg.medium_window, cfg.min_periods)
        g["trend_directional_ratio"] = (
            np.sign(returns).rolling(cfg.medium_window, min_periods=cfg.min_periods).mean()
        )
        g["trend_vwap_residence"] = (
            np.sign(close - vwap).rolling(cfg.medium_window, min_periods=cfg.min_periods).mean()
        )

        short_range = true_range.rolling(cfg.short_window, min_periods=cfg.min_periods).mean()
        long_range = true_range.rolling(cfg.long_window, min_periods=cfg.min_periods).mean()
        short_vol = returns.rolling(cfg.short_window, min_periods=cfg.min_periods).std(ddof=0)
        long_vol = returns.rolling(cfg.long_window, min_periods=cfg.min_periods).std(ddof=0)
        previous_high = high.shift(1)
        previous_low = low.shift(1)
        overlap = (
            pd.concat([high, previous_high], axis=1).min(axis=1)
            - pd.concat([low, previous_low], axis=1).max(axis=1)
        ).clip(lower=0)
        union = (
            pd.concat([high, previous_high], axis=1).max(axis=1)
            - pd.concat([low, previous_low], axis=1).min(axis=1)
        )
        g["range_short_long_ratio"] = _safe_div(short_range, long_range)
        g["realized_vol_short_long_ratio"] = _safe_div(short_vol, long_vol)
        g["bar_overlap_ratio"] = _safe_div(overlap, union).rolling(
            cfg.short_window, min_periods=cfg.min_periods
        ).mean()
        g["range_zscore"] = _rolling_zscore(true_range, cfg.long_window, cfg.min_periods)

        g["vwap_distance_atr"] = _safe_div(close - vwap, atr_long)
        vwap_side = np.sign(close - vwap)
        g["vwap_cross_frequency"] = vwap_side.ne(vwap_side.shift(1)).rolling(
            cfg.medium_window, min_periods=cfg.min_periods
        ).mean()
        g["close_location_value"] = _safe_div(close - low, true_range).clip(0.0, 1.0)
        g["directional_efficiency_signed"] = (
            np.sign(close.diff(cfg.medium_window)) * g["trend_path_efficiency"]
        )

        above = (close > vwap).astype(float)
        below = (close < vwap).astype(float)
        g["above_vwap_dwell"] = above.rolling(cfg.short_window, min_periods=cfg.min_periods).mean()
        g["below_vwap_dwell"] = below.rolling(cfg.short_window, min_periods=cfg.min_periods).mean()
        g["upper_rejection_wick"] = _safe_div(upper_wick, true_range).clip(0.0, 1.0)
        g["lower_rejection_wick"] = _safe_div(lower_wick, true_range).clip(0.0, 1.0)

        g["volume_zscore"] = _rolling_zscore(volume, cfg.long_window, cfg.min_periods)
        g["range_per_volume"] = _safe_div(true_range, volume)
        g["directional_participation"] = np.sign(body) * g["volume_zscore"]

        option_present = cfg.option_close_col in g.columns
        if option_present:
            option_close = pd.to_numeric(g[cfg.option_close_col], errors="coerce")
            option_returns = option_close.pct_change()
            g["option_return_short"] = option_close.pct_change(cfg.short_window)
            g["option_elasticity_short"] = _safe_div(
                g["option_return_short"], g["trend_return_short"]
            )
            same_direction = np.sign(option_returns) == np.sign(returns)
            g["option_response_consistency"] = same_direction.astype(float).rolling(
                cfg.short_window, min_periods=cfg.min_periods
            ).mean()
            if cfg.option_volume_col in g.columns:
                option_volume = pd.to_numeric(g[cfg.option_volume_col], errors="coerce")
                g["option_volume_zscore"] = _rolling_zscore(
                    option_volume, cfg.long_window, cfg.min_periods
                )
            else:
                g["option_volume_zscore"] = np.nan
            g["option_observable"] = option_close.notna().astype(int)
        else:
            for name in (
                "option_return_short",
                "option_elasticity_short",
                "option_response_consistency",
                "option_volume_zscore",
            ):
                g[name] = np.nan
            g["option_observable"] = 0

        price_progress = close.diff(cfg.short_window)
        signed_volume_pressure = np.sign(body).rolling(
            cfg.short_window, min_periods=cfg.min_periods
        ).sum()
        normalized_progress = _safe_div(price_progress, atr_long)
        g["failed_progress_up"] = (
            (signed_volume_pressure > 0) & (normalized_progress <= 0.25)
        ).astype(int)
        g["failed_progress_down"] = (
            (signed_volume_pressure < 0) & (normalized_progress >= -0.25)
        ).astype(int)
        g["impulse_exhaustion_up"] = (
            (g["range_zscore"] > 1.0)
            & (g["upper_rejection_wick"] > 0.4)
            & (g["close_location_value"] < 0.6)
        ).astype(int)
        g["impulse_exhaustion_down"] = (
            (g["range_zscore"] > 1.0)
            & (g["lower_rejection_wick"] > 0.4)
            & (g["close_location_value"] > 0.4)
        ).astype(int)

        g["underlying_observable"] = (
            close.notna() & high.notna() & low.notna() & open_.notna()
        ).astype(int)
        core = [
            "trend_return_short",
            "trend_path_efficiency",
            "range_short_long_ratio",
            "vwap_distance_atr",
            "volume_zscore",
        ]
        g["state_reliability"] = g[core].notna().mean(axis=1) * (
            0.75 + 0.25 * g["option_observable"]
        )
        return g

    return out.groupby(cfg.session_col, group_keys=False, sort=False).apply(per_session).reset_index(drop=True)
