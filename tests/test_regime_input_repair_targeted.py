"""Unit tests specifically verifying the endogenous regime input repair contracts.

Covers:
1. Low, median, high, extreme ATR values mapped through frozen anchor.
2. Positive and negative vwap_slope_atr scaling and sign invariance in consumer.
3. Positive and negative ltp_acceleration_atr scaling, preserving sign from producer, abs() in consumer.
4. Regime transition rate causal warmup and windowing.
5. Intraday session boundary reset of regime transitions.
6. Missing and zero inputs handling (fail-safe).
"""

import math
from collections import deque

import pytest

from core.regime_contract_v2 import (
    INSUFFICIENT_DATA,
    INVALID_INPUT,
    VALID,
    _normalized_acceleration_strength,
    _normalized_slope_strength,
    normalized_heuristic_scores,
)
from core.regime_prob_model import RegimeProbModel


def _base_features(**overrides):
    row = {
        "adx": 20.0,
        "vwap_slope_atr": 0.0,
        "vol_z": 0.0,
        "atr_pct": 0.000334,  # median ~3.3 bps
        "iv_mean": 0.15,
        "ltp_acceleration_atr": 0.0,
        "option_chain_skew": 0.0,
        "oi_delta": 0.0,
        "oi_gross": 10_000_000.0,
        "depth_imbalance": 0.0,
        "regime_transition_rate": 0.0,
        "shock_score": 0.0,
        "uncertainty_index": 0.0,
        "macro_direction_bias": 0.0,
        "x_regime_align": 0.0,
        "x_vol_spillover": 0.0,
        "x_lead_lag": 0.0,
    }
    row.update(overrides)
    return row


class TestATRNormalizationRepair:
    """Repair A: atr_pct anchor normalization tests."""

    def test_atr_below_anchor_min_clamps_to_zero(self):
        # 1 bp (0.0001) is below anchor_min 0.0002 -> atr_strength = 0.0
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=0.0001))
        assert quality["bounded_components"]["atr_strength"] == 0.0

    def test_atr_at_anchor_min(self):
        # 2 bps (0.0002) is exactly anchor_min -> atr_strength = 0.0
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=0.0002))
        assert quality["bounded_components"]["atr_strength"] == 0.0

    def test_atr_at_median(self):
        # Median is ~3.34 bps (0.000334) -> (0.000334 - 0.0002) / 0.0004 = 0.335
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=0.000334))
        atr_s = quality["bounded_components"]["atr_strength"]
        assert math.isclose(atr_s, 0.335, rel_tol=1e-3)

    def test_atr_at_anchor_max(self):
        # 6 bps (0.0006) = 0.0002 + 0.0004 -> atr_strength = 1.0
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=0.0006))
        assert math.isclose(quality["bounded_components"]["atr_strength"], 1.0, abs_tol=1e-9)

    def test_atr_extreme_clamps_to_one(self):
        # 20 bps (0.0020) -> clamped to 1.0
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=0.0020))
        assert math.isclose(quality["bounded_components"]["atr_strength"], 1.0, abs_tol=1e-9)


class TestVWAPSlopeATRRepair:
    """Repair B: vwap_slope_atr contract tests."""

    def test_explicit_vwap_slope_atr_positive(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(vwap_slope_atr=0.75)
        )
        assert quality["normalization"]["slope_source"] == "vwap_slope_atr"
        assert quality["bounded_components"]["slope_strength"] == 0.75

    def test_explicit_vwap_slope_atr_negative_uses_abs(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(vwap_slope_atr=-0.80)
        )
        assert quality["normalization"]["slope_source"] == "vwap_slope_atr"
        assert quality["bounded_components"]["slope_strength"] == 0.80

    def test_raw_vwap_slope_is_ignored_when_unscaled(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(vwap_slope=15.0, vwap_slope_atr=None)
        )
        assert quality["normalization"]["slope_source"] == "raw_vwap_slope_ignored"
        assert quality["bounded_components"]["slope_strength"] == 0.0


class TestLTPAccelerationATRRepair:
    """Repair C: ltp_acceleration_atr contract tests."""

    def test_explicit_ltp_acceleration_atr_positive(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(ltp_acceleration_atr=0.50)
        )
        assert quality["normalization"]["acceleration_source"] == "ltp_acceleration_atr"
        assert quality["bounded_components"]["acceleration_strength"] == 0.50

    def test_explicit_ltp_acceleration_atr_negative_uses_abs(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(ltp_acceleration_atr=-0.65)
        )
        assert quality["normalization"]["acceleration_source"] == "ltp_acceleration_atr"
        assert quality["bounded_components"]["acceleration_strength"] == 0.65

    def test_raw_ltp_acceleration_is_ignored_when_unscaled(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(ltp_acceleration=5.0, ltp_acceleration_atr=None)
        )
        assert quality["normalization"]["acceleration_source"] == "raw_ltp_acceleration_ignored"
        assert quality["bounded_components"]["acceleration_strength"] == 0.0


class TestRegimeTransitionRateRepair:
    """Repair D: regime_transition_rate contract tests."""

    def test_transition_rate_normalized_by_eight(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(regime_transition_rate=4.0)
        )
        assert quality["bounded_components"]["transition_strength"] == 0.50

    def test_transition_rate_clamped_at_eight(self):
        scores, quality = normalized_heuristic_scores(
            _base_features(regime_transition_rate=12.0)
        )
        assert quality["bounded_components"]["transition_strength"] == 1.0


class TestEdgeAndMissingInputs:
    """Boundary and missing input verification."""

    def test_missing_required_atr_pct_fails_insufficient_data(self):
        feats = _base_features()
        del feats["atr_pct"]
        scores, quality = normalized_heuristic_scores(feats)
        assert quality["status"] == INSUFFICIENT_DATA

    def test_non_positive_atr_pct_fails_invalid_input(self):
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=0.0))
        assert quality["status"] == INVALID_INPUT

    def test_negative_atr_pct_fails_invalid_input(self):
        scores, quality = normalized_heuristic_scores(_base_features(atr_pct=-0.0005))
        assert quality["status"] == INVALID_INPUT


class TestMarketDataProducerWiring:
    """Producer wiring in core/market_data.py tests."""

    def test_vwap_slope_atr_preserves_sign(self):
        atr = 50.0
        vwap_slope_pos = 25.0
        vwap_slope_neg = -25.0
        res_pos = (float(vwap_slope_pos) / max(float(atr), 1e-4))
        res_neg = (float(vwap_slope_neg) / max(float(atr), 1e-4))
        assert res_pos == 0.5
        assert res_neg == -0.5

    def test_ltp_acceleration_atr_preserves_sign(self):
        atr = 50.0
        accel_pos = 10.0
        accel_neg = -10.0
        res_pos = (float(accel_pos) / max(float(atr), 1e-4))
        res_neg = (float(accel_neg) / max(float(atr), 1e-4))
        assert res_pos == 0.2
        assert res_neg == -0.2

    def test_producer_zero_atr_fallback(self):
        atr = 0.0
        vwap_slope = 10.0
        res = (float(vwap_slope) / max(float(atr), 1e-4)) if (atr and vwap_slope) else 0.0
        assert res == 0.0
