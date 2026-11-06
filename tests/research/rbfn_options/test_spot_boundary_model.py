"""Tests for CausalSpotBoundaryModel.

Verifies:
- Strict causal feature engineering (no future sessions)
- Monotonic boundary ordering: lower_reversal < trend_decider < upper_reversal
- Validation guards on invalid daily bars
- Rejection of target date lookahead
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.rbfn_options.core.spot_boundary_model import (
    CandleMicrostructure,
    CausalSpotBoundaryModel,
    SpotBoundaryForecast,
    StructuralReversalResult,
    validate_structural_reversal,
)


def make_dummy_daily_data(n_days: int = 50) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="B").strftime("%Y-%m-%d")
    base_price = 22000.0
    records = []
    current_close = base_price

    for d in dates:
        ret = np.random.normal(0.0005, 0.008)
        c = current_close * (1 + ret)
        o = current_close * (1 + np.random.normal(0.0, 0.002))
        h = max(o, c) + abs(np.random.normal(50, 20))
        l = min(o, c) - abs(np.random.normal(50, 20))
        records.append({'date': d, 'o': o, 'h': h, 'l': l, 'c': c})
        current_close = c

    return pd.DataFrame(records)


def test_spot_boundary_forecast_validation():
    # Valid forecast
    valid = SpotBoundaryForecast(
        date="2026-05-01",
        prev_close=22000.0,
        prev_range=200.0,
        upper_reversal=22150.0,
        trend_decider=22020.0,
        lower_reversal=21850.0,
    )
    valid.validate()

    # Invalid ordering: upper <= lower
    invalid = SpotBoundaryForecast(
        date="2026-05-01",
        prev_close=22000.0,
        prev_range=200.0,
        upper_reversal=21800.0,
        trend_decider=22000.0,
        lower_reversal=22100.0,
    )
    with pytest.raises(ValueError, match="Boundary ordering violation"):
        invalid.validate()


def test_causal_spot_boundary_pipeline():
    df = make_dummy_daily_data(40)
    samples = CausalSpotBoundaryModel.extract_features_and_targets(df)
    assert len(samples) == 40 - 6

    # Verify features strictly use past
    for s in samples:
        assert len(s['x']) == 6
        assert len(s['y']) == 3
        assert s['prev_range'] > 0

    model = CausalSpotBoundaryModel(n_centers=10, width=3.4, ridge=2.0)
    model.fit(samples[:25])
    assert model.is_fitted

    # Forecast for session 26
    target_date = df.iloc[31]['date']
    prior_df = df.iloc[:31]  # strictly before target_date

    forecast = model.forecast_session(target_date, prior_df)
    assert forecast.date == target_date
    assert forecast.lower_reversal < forecast.trend_decider < forecast.upper_reversal


def test_lookahead_detection_raises():
    df = make_dummy_daily_data(20)
    samples = CausalSpotBoundaryModel.extract_features_and_targets(df)
    model = CausalSpotBoundaryModel(n_centers=8)
    model.fit(samples)

    # Attempt to forecast with data containing the target date
    target_date = df.iloc[15]['date']
    contaminated_df = df.iloc[:16]  # includes target_date!

    with pytest.raises(ValueError, match="prior_sessions_df contains dates >= target_date"):
        model.forecast_session(target_date, contaminated_df)


def test_spot_boundary_dead_zone_and_touch():
    forecast = SpotBoundaryForecast(
        date="2026-05-01",
        prev_close=22000.0,
        prev_range=200.0,
        upper_reversal=22150.0,
        trend_decider=22000.0,
        lower_reversal=21850.0,
    )

    # Dead zone: defaults to 0.15% around trend decider (22000 * 0.0015 = 33 points)
    # Range is [21967.0, 22033.0]
    assert forecast.is_in_dead_zone(22000.0) is True
    assert forecast.is_in_dead_zone(22030.0) is True
    assert forecast.is_in_dead_zone(21970.0) is True
    assert forecast.is_in_dead_zone(22050.0) is False
    assert forecast.is_in_dead_zone(21950.0) is False

    # Dead zone explicit points (e.g. 20.0 points -> [21980, 22020])
    assert forecast.is_in_dead_zone(22015.0, dead_zone_points=20.0) is True
    assert forecast.is_in_dead_zone(22025.0, dead_zone_points=20.0) is False

    # Dead zone explicit pct (e.g. 0.001 -> 22.0 points)
    assert forecast.is_in_dead_zone(22020.0, dead_zone_pct=0.001) is True
    assert forecast.is_in_dead_zone(22030.0, dead_zone_pct=0.001) is False

    # Evaluate touch without tolerance
    # upper_reversal = 22150, lower_reversal = 21850
    t1 = forecast.evaluate_touch(high=22155.0, low=22100.0)
    assert t1["upper_touch"] is True
    assert t1["lower_touch"] is False

    t2 = forecast.evaluate_touch(high=21900.0, low=21845.0)
    assert t2["upper_touch"] is False
    assert t2["lower_touch"] is True

    # Inside boundaries
    t3 = forecast.evaluate_touch(high=22100.0, low=21900.0)
    assert t3["upper_touch"] is False
    assert t3["lower_touch"] is False

    # With tolerance_points = 5.0 (upper triggers at >= 22145)
    t4 = forecast.evaluate_touch(high=22146.0, low=22120.0, tolerance_points=5.0)
    assert t4["upper_touch"] is True

    # Guard tests
    with pytest.raises(ValueError, match="low.*cannot be greater than high"):
        forecast.evaluate_touch(high=22000.0, low=22100.0)

    with pytest.raises(ValueError, match="spot_price must be positive"):
        forecast.is_in_dead_zone(-10.0)


def test_candle_microstructure_geometry_and_shadows():
    # Regular bullish hammer (strong lower wick)
    # open 22020, close 22040, high 22045, low 21990
    # range = 55.0
    # lower_shadow = 22020 - 21990 = 30.0 -> ratio = 30 / 55 = 0.54545...
    # upper_shadow = 22045 - 22040 = 5.0 -> ratio = 5 / 55 = 0.09090...
    candle = CandleMicrostructure(open=22020.0, high=22045.0, low=21990.0, close=22040.0, volume=1500.0)
    candle.validate()

    assert candle.range == 55.0
    assert abs(candle.lower_shadow_ratio - (30.0 / 55.0)) < 1e-4
    assert abs(candle.upper_shadow_ratio - (5.0 / 55.0)) < 1e-4

    # Shooting star (strong upper wick)
    # open 22040, close 22020, high 22090, low 22015
    # range = 75.0
    # upper_shadow = 22090 - 22040 = 50.0 -> ratio = 50 / 75 = 0.6666...
    # lower_shadow = 22020 - 22015 = 5.0 -> ratio = 5 / 75 = 0.0666...
    star = CandleMicrostructure(open=22040.0, high=22090.0, low=22015.0, close=22020.0, volume=2000.0)
    star.validate()

    assert star.range == 75.0
    assert abs(star.upper_shadow_ratio - (50.0 / 75.0)) < 1e-4
    assert abs(star.lower_shadow_ratio - (5.0 / 75.0)) < 1e-4

    # Zero range candle (doji / no movement)
    zero_range = CandleMicrostructure(open=22000.0, high=22000.0, low=22000.0, close=22000.0, volume=100.0)
    zero_range.validate()
    assert zero_range.range == 0.0
    assert zero_range.lower_shadow_ratio == 0.0
    assert zero_range.upper_shadow_ratio == 0.0

    # Validation errors
    with pytest.raises(ValueError, match="Price fields.*must be positive"):
        CandleMicrostructure(open=-10.0, high=22000.0, low=21900.0, close=21950.0).validate()

    with pytest.raises(ValueError, match="low.*cannot exceed high"):
        CandleMicrostructure(open=22000.0, high=21900.0, low=22100.0, close=21950.0).validate()

    with pytest.raises(ValueError, match="open.*must be within"):
        CandleMicrostructure(open=22200.0, high=22100.0, low=21900.0, close=21950.0).validate()

    with pytest.raises(ValueError, match="close.*must be within"):
        CandleMicrostructure(open=22000.0, high=22100.0, low=21900.0, close=21800.0).validate()

    with pytest.raises(ValueError, match="volume cannot be negative"):
        CandleMicrostructure(open=22000.0, high=22100.0, low=21900.0, close=21950.0, volume=-5.0).validate()


def test_validate_structural_reversal_lower_boundary():
    # Lower boundary touch with strong lower wick (hammer): bullish reversal
    candle_valid = CandleMicrostructure(open=22020.0, high=22045.0, low=21990.0, close=22040.0, volume=1500.0)
    recent_vols = [1000.0, 1200.0, 1100.0, 1300.0, 1050.0]  # median = 1100.0
    # 1500.0 >= 0.8 * 1100.0 = 880.0 -> Confirmed

    res = validate_structural_reversal(
        candle=candle_valid,
        boundary_touch_type="LOWER",
        recent_volume_series=recent_vols,
        min_wick_ratio=0.35,
    )
    assert res.is_valid_reversal is True
    assert res.reversal_type == "BULLISH"
    assert res.rejection_boundary == "LOWER"
    assert res.volume_confirmed is True
    assert res.wick_ratio > 0.35

    # Insufficient lower wick (marubozu / strong down bar without lower rejection)
    candle_weak_wick = CandleMicrostructure(open=22040.0, high=22045.0, low=21990.0, close=21995.0, volume=1500.0)
    # lower_shadow = 21995 - 21990 = 5.0 / 55.0 = 0.0909 < 0.35
    res_weak = validate_structural_reversal(
        candle=candle_weak_wick,
        boundary_touch_type="LOWER",
        recent_volume_series=recent_vols,
        min_wick_ratio=0.35,
    )
    assert res_weak.is_valid_reversal is False
    assert res_weak.reversal_type == "NONE"
    assert "below threshold" in res_weak.reason

    # Insufficient volume confirmation
    res_low_vol = validate_structural_reversal(
        candle=candle_valid,
        boundary_touch_type="LOWER",
        recent_volume_series=[5000.0, 6000.0, 5500.0],  # median = 5500.0, 0.8 * 5500 = 4400 > 1500
        min_wick_ratio=0.35,
        min_volume_ratio=0.8,
    )
    assert res_low_vol.is_valid_reversal is False
    assert res_low_vol.volume_confirmed is False
    assert "Volume confirmation failed" in res_low_vol.reason


def test_validate_structural_reversal_upper_boundary():
    # Upper boundary touch with strong upper wick (shooting star): bearish reversal
    candle_star = CandleMicrostructure(open=22040.0, high=22090.0, low=22015.0, close=22020.0, volume=1800.0)
    recent_vols = [1200.0, 1400.0, 1300.0]

    res = validate_structural_reversal(
        candle=candle_star,
        boundary_touch_type="UPPER",
        recent_volume_series=recent_vols,
        min_wick_ratio=0.35,
    )
    assert res.is_valid_reversal is True
    assert res.reversal_type == "BEARISH"
    assert res.rejection_boundary == "UPPER"
    assert res.volume_confirmed is True

    # Zero range candle rejected
    candle_zero = CandleMicrostructure(open=22050.0, high=22050.0, low=22050.0, close=22050.0, volume=500.0)
    res_zero = validate_structural_reversal(candle=candle_zero, boundary_touch_type="UPPER")
    assert res_zero.is_valid_reversal is False
    assert res_zero.reversal_type == "NONE"
    assert "Zero candle range" in res_zero.reason

    # Invalid boundary type
    with pytest.raises(ValueError, match="boundary_touch_type must be 'LOWER' or 'UPPER'"):
        validate_structural_reversal(candle=candle_star, boundary_touch_type="MIDDLE")


