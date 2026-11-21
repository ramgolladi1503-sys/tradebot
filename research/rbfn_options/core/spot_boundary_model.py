"""Causal Stage 1 Spot Boundary Model.

Forecasts pre-open spot levels strictly using historical data:
- Upper Reversal level
- Lower Reversal level
- Trend Decider level

Strictly adheres to:
1. No lookahead bias (features strictly from sessions < t)
2. Invariant ordering: Lower Reversal < Trend Decider < Upper Reversal
3. Purely causal calculations and validation
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence
import numpy as np
import pandas as pd

from research.rbfn_options.core.rbfn_engine import GaussianRBFNetwork


@dataclass(frozen=True)
class CandleMicrostructure:
    """Microstructure metrics for an intraday bar."""
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def validate(self) -> None:
        """Validate candle geometry and invariant boundaries."""
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("Price fields (open, high, low, close) must be positive")
        if self.low > self.high:
            raise ValueError(f"low ({self.low}) cannot exceed high ({self.high})")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"open ({self.open}) must be within [low, high]: [{self.low}, {self.high}]")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"close ({self.close}) must be within [low, high]: [{self.low}, {self.high}]")
        if self.volume < 0:
            raise ValueError(f"volume cannot be negative, got {self.volume}")

    @property
    def range(self) -> float:
        """High minus low spread."""
        return float(self.high - self.low)

    @property
    def lower_shadow_ratio(self) -> float:
        """Lower shadow (wick) as fraction of total candle range.
        
        Returns 0.0 if total candle range is 0.
        """
        r = self.range
        if r <= 0.0:
            return 0.0
        lower_body_edge = min(self.open, self.close)
        lower_shadow = lower_body_edge - self.low
        return float(max(0.0, lower_shadow) / r)

    @property
    def upper_shadow_ratio(self) -> float:
        """Upper shadow (wick) as fraction of total candle range.
        
        Returns 0.0 if total candle range is 0.
        """
        r = self.range
        if r <= 0.0:
            return 0.0
        upper_body_edge = max(self.open, self.close)
        upper_shadow = self.high - upper_body_edge
        return float(max(0.0, upper_shadow) / r)


@dataclass(frozen=True)
class StructuralReversalResult:
    """Result of structural reversal validation on a boundary touch candle."""
    is_valid_reversal: bool
    reversal_type: str  # 'BULLISH', 'BEARISH', or 'NONE'
    wick_ratio: float
    volume_confirmed: bool
    rejection_boundary: str  # 'LOWER', 'UPPER', or 'NONE'
    reason: str


def validate_structural_reversal(
    candle: CandleMicrostructure,
    boundary_touch_type: str,
    recent_volume_series: Optional[Sequence[float]] = None,
    min_wick_ratio: float = 0.35,
    min_volume_ratio: float = 0.8,
) -> StructuralReversalResult:
    """Validate whether a candle touching a boundary represents a structural price rejection.

    Rejection Logic:
    1. Lower boundary touch (potential Bullish reversal):
       - Requires strong lower shadow/wick rejection: lower_shadow_ratio >= min_wick_ratio.
       - Close should ideally not close below open significantly (close >= open or close near high).
    2. Upper boundary touch (potential Bearish reversal):
       - Requires strong upper shadow/wick rejection: upper_shadow_ratio >= min_wick_ratio.
       - Close should ideally not close above open significantly (close <= open or close near low).
    3. Volume confirmation:
       - If `recent_volume_series` is provided and non-empty, checks if candle.volume >= min_volume_ratio * median(recent_volume_series).
       - If recent_volume_series is None or empty, volume_confirmed defaults to True.

    Parameters
    ----------
    candle : CandleMicrostructure
        The candle to evaluate.
    boundary_touch_type : str
        'LOWER' (support touch, expecting bullish bounce) or 'UPPER' (resistance touch, expecting bearish drop).
    recent_volume_series : Sequence[float], optional
        Recent bar volumes (e.g. past 10-20 bars prior to this candle) for volume median baseline.
    min_wick_ratio : float
        Minimum wick rejection ratio (default 0.35, i.e. 35% of total bar range).
    min_volume_ratio : float
        Candle volume must be at least this fraction of recent volume median (default 0.8).

    Returns
    -------
    StructuralReversalResult
    """
    candle.validate()
    touch = boundary_touch_type.upper()
    if touch not in ('LOWER', 'UPPER'):
        raise ValueError(f"boundary_touch_type must be 'LOWER' or 'UPPER', got {boundary_touch_type}")
    if min_wick_ratio < 0.0 or min_wick_ratio > 1.0:
        raise ValueError(f"min_wick_ratio must be in [0.0, 1.0], got {min_wick_ratio}")
    if min_volume_ratio < 0.0:
        raise ValueError(f"min_volume_ratio must be non-negative, got {min_volume_ratio}")

    # Volume confirmation check
    volume_confirmed = True
    if recent_volume_series is not None and len(recent_volume_series) > 0:
        clean_vols = [float(v) for v in recent_volume_series if v >= 0]
        if clean_vols:
            med_vol = float(np.median(clean_vols))
            if med_vol > 0.0:
                volume_confirmed = bool(candle.volume >= min_volume_ratio * med_vol)

    # Candle range check
    if candle.range <= 0.0:
        return StructuralReversalResult(
            is_valid_reversal=False,
            reversal_type="NONE",
            wick_ratio=0.0,
            volume_confirmed=volume_confirmed,
            rejection_boundary=touch,
            reason="Zero candle range, cannot confirm structural rejection",
        )

    if touch == 'LOWER':
        wick_ratio = candle.lower_shadow_ratio
        if wick_ratio < min_wick_ratio:
            return StructuralReversalResult(
                is_valid_reversal=False,
                reversal_type="NONE",
                wick_ratio=wick_ratio,
                volume_confirmed=volume_confirmed,
                rejection_boundary="LOWER",
                reason=f"Lower wick ratio {wick_ratio:.3f} below threshold {min_wick_ratio:.3f}",
            )
        if not volume_confirmed:
            return StructuralReversalResult(
                is_valid_reversal=False,
                reversal_type="NONE",
                wick_ratio=wick_ratio,
                volume_confirmed=False,
                rejection_boundary="LOWER",
                reason="Volume confirmation failed against recent volume baseline",
            )
        return StructuralReversalResult(
            is_valid_reversal=True,
            reversal_type="BULLISH",
            wick_ratio=wick_ratio,
            volume_confirmed=True,
            rejection_boundary="LOWER",
            reason="Confirmed bullish structural rejection at lower boundary",
        )

    else:  # touch == 'UPPER'
        wick_ratio = candle.upper_shadow_ratio
        if wick_ratio < min_wick_ratio:
            return StructuralReversalResult(
                is_valid_reversal=False,
                reversal_type="NONE",
                wick_ratio=wick_ratio,
                volume_confirmed=volume_confirmed,
                rejection_boundary="UPPER",
                reason=f"Upper wick ratio {wick_ratio:.3f} below threshold {min_wick_ratio:.3f}",
            )
        if not volume_confirmed:
            return StructuralReversalResult(
                is_valid_reversal=False,
                reversal_type="NONE",
                wick_ratio=wick_ratio,
                volume_confirmed=False,
                rejection_boundary="UPPER",
                reason="Volume confirmation failed against recent volume baseline",
            )
        return StructuralReversalResult(
            is_valid_reversal=True,
            reversal_type="BEARISH",
            wick_ratio=wick_ratio,
            volume_confirmed=True,
            rejection_boundary="UPPER",
            reason="Confirmed bearish structural rejection at upper boundary",
        )


@dataclass(frozen=True)
class SpotBoundaryForecast:
    """Forecasted spot key levels for a trading session."""
    date: str
    prev_close: float
    prev_range: float
    upper_reversal: float
    trend_decider: float
    lower_reversal: float

    def validate(self) -> None:
        """Enforce strict invariant ordering and positive price levels."""
        if self.prev_close <= 0 or self.prev_range <= 0:
            raise ValueError("prev_close and prev_range must be positive")
        if self.lower_reversal <= 0:
            raise ValueError("lower_reversal must be positive")
        if not (self.lower_reversal < self.trend_decider < self.upper_reversal):
            raise ValueError(
                f"Boundary ordering violation: lower ({self.lower_reversal}) < "
                f"decider ({self.trend_decider}) < upper ({self.upper_reversal}) is required."
            )

    def is_in_dead_zone(
        self,
        spot_price: float,
        dead_zone_points: Optional[float] = None,
        dead_zone_pct: Optional[float] = None,
    ) -> bool:
        """Check if spot price is in dead zone around the Trend Decider level.
        
        If neither dead_zone_points nor dead_zone_pct is specified, defaults to 0.15% (dead_zone_pct=0.0015).
        """
        if spot_price <= 0:
            raise ValueError(f"spot_price must be positive, got {spot_price}")
        if dead_zone_points is not None and dead_zone_points < 0:
            raise ValueError(f"dead_zone_points must be non-negative, got {dead_zone_points}")
        if dead_zone_pct is not None and dead_zone_pct < 0:
            raise ValueError(f"dead_zone_pct must be non-negative, got {dead_zone_pct}")

        half_width = 0.0
        if dead_zone_points is not None:
            half_width += float(dead_zone_points)
        if dead_zone_pct is not None:
            half_width += float(self.trend_decider * dead_zone_pct)
        if dead_zone_points is None and dead_zone_pct is None:
            half_width = float(self.trend_decider * 0.0015)

        return bool(abs(spot_price - self.trend_decider) <= half_width)

    def evaluate_touch(
        self,
        high: float,
        low: float,
        tolerance_points: float = 0.0,
    ) -> dict[str, bool]:
        """Evaluate whether a bar's price range touches or penetrates upper or lower reversal levels.

        Parameters
        ----------
        high : float
            High of the bar.
        low : float
            Low of the bar.
        tolerance_points : float
            Tolerance around reversal boundary in index points (default 0.0).

        Returns
        -------
        dict with boolean keys:
            'upper_touch': True if high >= upper_reversal - tolerance_points
            'lower_touch': True if low <= lower_reversal + tolerance_points
        """
        if low <= 0 or high <= 0:
            raise ValueError("high and low must be positive")
        if low > high:
            raise ValueError(f"low ({low}) cannot be greater than high ({high})")
        if tolerance_points < 0:
            raise ValueError("tolerance_points must be non-negative")

        upper_hit = bool(high >= (self.upper_reversal - tolerance_points))
        lower_hit = bool(low <= (self.lower_reversal + tolerance_points))
        return {
            "upper_touch": upper_hit,
            "lower_touch": lower_hit,
        }


class CausalSpotBoundaryModel:
    """Causal Stage 1 Spot Boundary Model using GaussianRBFNetwork.

    Features engineered per session t strictly from sessions t-1, t-2, ... t-6:
    x_0: 100 * Range_{t-1} / Close_{t-1}
    x_1: (Close_{t-1} - Open_{t-1}) / Range_{t-1}
    x_2: (Close_{t-1} - Low_{t-1}) / Range_{t-1}
    x_3: 100 * (5-day mean range) / Close_{t-1}
    x_4: 100 * (Close_{t-1} / Close_{t-6} - 1)
    x_5: 100 * (Open_{t-1} / Close_{t-2} - 1)

    Targets:
    y_0: (High_t - Close_{t-1}) / Range_{t-1}  --> Upper excursion ratio
    y_1: (Close_{t-1} - Low_t) / Range_{t-1}   --> Lower excursion ratio
    y_2: (Close_t - Close_{t-1}) / Range_{t-1} --> Close change ratio
    """

    def __init__(
        self,
        n_centers: int = 28,
        width: float = 3.4,
        ridge: float = 4.0,
    ) -> None:
        self.rbfn = GaussianRBFNetwork(n_centers=n_centers, width=width, ridge=ridge)
        self.is_fitted: bool = False

    @staticmethod
    def extract_features_and_targets(daily_df: pd.DataFrame) -> list[dict]:
        """Extract strictly causal features and session excursion targets from daily bars.

        Parameters
        ----------
        daily_df : pd.DataFrame
            Must contain ['date', 'o', 'h', 'l', 'c'] sorted chronologically.

        Returns
        -------
        list of dict containing date, x, y, prev_close, prev_range, high, low, close.
        """
        required = {'date', 'o', 'h', 'l', 'c'}
        if not required.issubset(daily_df.columns):
            raise ValueError(f"daily_df missing required columns: {required - set(daily_df.columns)}")

        df = daily_df.sort_values('date').reset_index(drop=True)
        samples = []

        # Requires at least 6 prior sessions (index 6 has 0..5 prior)
        for i in range(6, len(df)):
            p = df.iloc[i - 1]
            p2 = df.iloc[i - 2]
            p6 = df.iloc[i - 6]
            cur = df.iloc[i]

            prev_range = float(p.h - p.l)
            if prev_range <= 0:
                continue

            last5 = df.iloc[i - 5 : i]
            mean_5d_range = float((last5.h - last5.l).mean())

            x = [
                100.0 * prev_range / float(p.c),
                float(p.c - p.o) / prev_range,
                float(p.c - p.l) / prev_range,
                100.0 * mean_5d_range / float(p.c),
                100.0 * (float(p.c) / float(p6.c) - 1.0),
                100.0 * (float(p.o) / float(p2.c) - 1.0),
            ]

            # Future target for session i (to train historical RBFN)
            y = [
                float(cur.h - p.c) / prev_range,
                float(p.c - cur.l) / prev_range,
                float(cur.c - p.c) / prev_range,
            ]

            samples.append({
                'date': str(cur.date),
                'x': np.asarray(x, dtype=float),
                'y': np.asarray(y, dtype=float),
                'prev_close': float(p.c),
                'prev_range': prev_range,
                'high': float(cur.h),
                'low': float(cur.l),
                'close': float(cur.c),
            })
        return samples

    def fit(self, training_samples: list[dict]) -> CausalSpotBoundaryModel:
        """Fit the RBFN on historical training samples."""
        if not training_samples:
            raise ValueError("training_samples cannot be empty")

        x = np.array([s['x'] for s in training_samples], dtype=float)
        y = np.array([s['y'] for s in training_samples], dtype=float)

        self.rbfn.fit(x, y)
        self.is_fitted = True
        return self

    def forecast_session(
        self,
        target_date: str,
        prior_sessions_df: pd.DataFrame,
    ) -> SpotBoundaryForecast:
        """Generate spot boundary levels for target_date using strictly prior sessions.

        Parameters
        ----------
        target_date : str
            Date for which to generate the forecast (e.g. '2026-05-15').
        prior_sessions_df : pd.DataFrame
            Must contain daily bars strictly BEFORE target_date with columns ['date', 'o', 'h', 'l', 'c'].
            Must contain at least 6 sessions.

        Returns
        -------
        SpotBoundaryForecast
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before forecasting.")

        df = prior_sessions_df.sort_values('date').reset_index(drop=True)
        # Verify strict causal condition: all dates < target_date
        if (df['date'] >= target_date).any():
            raise ValueError(f"prior_sessions_df contains dates >= target_date {target_date}")

        if len(df) < 6:
            raise ValueError("At least 6 prior sessions required to compute features.")

        p = df.iloc[-1]
        p2 = df.iloc[-2]
        p6 = df.iloc[-6]
        prev_close = float(p.c)
        prev_range = float(p.h - p.l)

        if prev_range <= 0:
            raise ValueError(f"Previous session range must be positive, got {prev_range}")

        last5 = df.iloc[-5:]
        mean_5d_range = float((last5.h - last5.l).mean())

        x = np.array([
            100.0 * prev_range / prev_close,
            float(p.c - p.o) / prev_range,
            float(p.c - p.l) / prev_range,
            100.0 * mean_5d_range / prev_close,
            100.0 * (prev_close / float(p6.c) - 1.0),
            100.0 * (float(p.o) / float(p2.c) - 1.0),
        ], dtype=float)

        pred_y = self.rbfn.predict(x)
        up_ratio, down_ratio, close_ratio = pred_y[0], pred_y[1], pred_y[2]

        upper_raw = prev_close + prev_range * up_ratio
        lower_raw = prev_close - prev_range * down_ratio
        decider_raw = prev_close + prev_range * close_ratio

        # Order enforcement guard
        # In rare boundary numerical inversions, enforce minimum positive separation
        lower = lower_raw
        upper = upper_raw
        decider = decider_raw

        if lower >= upper:
            # Squeeze / swap fallback preserving symmetry
            mid = prev_close
            span = max(abs(prev_range * 0.5), 10.0)
            lower = mid - span
            upper = mid + span
            decider = mid
        elif not (lower < decider < upper):
            # Clamp decider strictly between lower and upper
            margin = 0.1 * (upper - lower)
            decider = np.clip(decider, lower + margin, upper - margin)

        forecast = SpotBoundaryForecast(
            date=target_date,
            prev_close=prev_close,
            prev_range=prev_range,
            upper_reversal=float(upper),
            trend_decider=float(decider),
            lower_reversal=float(lower),
        )
        forecast.validate()
        return forecast
