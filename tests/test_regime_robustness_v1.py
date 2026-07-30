import json
import math

import pytest

from core.regime_contract_v2 import (
    INSUFFICIENT_DATA,
    INVALID_INPUT,
    RegimeStabilizer,
    UNCERTAIN,
    VALID,
    normalize_iv,
    normalize_oi_delta,
    normalized_heuristic_scores,
    probability_diagnostics,
    stable_softmax,
)
from core.regime_entropy_gate import evaluate_regime_entropy_gate
from core.regime_prob_model import REGIMES, RegimeProbModel


def valid_features(**overrides):
    row = {
        "adx": 28.0,
        "vwap_slope": 1.5,
        "vol_z": 1.2,
        "atr_pct": 0.006,
        "iv_mean": 18.0,
        "ltp_acceleration": 2.0,
        "option_chain_skew": 0.01,
        "oi_delta": 250_000.0,
        "oi_gross": 10_000_000.0,
        "depth_imbalance": 0.2,
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


def heuristic_model(tmp_path):
    return RegimeProbModel(str(tmp_path / "missing.json"))


def test_raw_oi_is_bounded_and_cannot_dominate_softmax():
    scores, quality = normalized_heuristic_scores(
        valid_features(oi_delta=10**12, oi_gross=None)
    )
    assert quality["status"] == VALID
    assert -1.0 <= quality["normalization"]["oi_normalized"] <= 1.0
    probs = stable_softmax(scores)
    assert max(probs.values()) < 0.90
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-12)


def test_oi_ratio_uses_gross_when_available():
    value, source = normalize_oi_delta(100.0, 1000.0)
    assert source == "oi_gross_ratio"
    assert value == 0.1


def test_iv_percent_and_decimal_have_same_scale():
    decimal, note_decimal = normalize_iv(0.18)
    percent, note_percent = normalize_iv(18.0)
    assert decimal == percent == 0.18
    assert note_decimal is None
    assert note_percent == "iv_scaled_percent"


def test_missing_required_feature_is_not_fake_range_evidence(tmp_path):
    out = heuristic_model(tmp_path).predict(valid_features(adx=None))
    assert out["regime_status"] == INSUFFICIENT_DATA
    assert out["primary_regime"] == "UNKNOWN"
    assert set(out["regime_probs"].values()) == {0.2}
    assert out["unstable_regime_flag"] is True


def test_zero_atr_is_invalid_not_confident_range(tmp_path):
    out = heuristic_model(tmp_path).predict(valid_features(atr_pct=0.0))
    assert out["regime_status"] == INVALID_INPUT
    assert out["primary_regime"] == "UNKNOWN"
    assert out["unstable_regime_flag"] is True


def test_probability_diagnostics_are_full_precision():
    probs = stable_softmax(
        {
            "TREND": 1.0,
            "RANGE": 0.9,
            "RANGE_VOLATILE": 0.8,
            "EVENT": 0.7,
            "PANIC": 0.6,
        }
    )
    diag = probability_diagnostics(probs)
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-12)
    assert 0.0 <= diag["normalized_entropy"] <= 1.0
    assert diag["top_two_margin"] > 0.0


def test_rounded_probability_vector_is_accepted_and_renormalized():
    rounded = {
        "TREND": 0.333333,
        "RANGE": 0.222222,
        "RANGE_VOLATILE": 0.166667,
        "EVENT": 0.166667,
        "PANIC": 0.111112,
    }
    assert sum(rounded.values()) == 1.000001
    diag = probability_diagnostics(rounded)
    assert diag["input_probability_sum"] == 1.000001
    assert math.isclose(
        sum(diag["probabilities"].values()), 1.0, abs_tol=1e-12
    )


def test_unknown_nonzero_probability_label_is_rejected():
    with pytest.raises(ValueError, match="unknown_probability_labels:NEUTRAL"):
        probability_diagnostics(
            {
                "TREND": 1.0,
                "RANGE": 0.0,
                "RANGE_VOLATILE": 0.0,
                "EVENT": 0.0,
                "PANIC": 0.0,
                "NEUTRAL": 0.1,
            }
        )


def test_low_entropy_is_not_itself_an_error():
    diag = probability_diagnostics(
        {
            "TREND": 1.0,
            "RANGE": 0.0,
            "RANGE_VOLATILE": 0.0,
            "EVENT": 0.0,
            "PANIC": 0.0,
        }
    )
    assert diag["normalized_entropy"] == 0.0
    assert diag["top_label"] == "TREND"


def test_legacy_raw_trend_override_is_preserved():
    result = evaluate_regime_entropy_gate(
        raw_entropy=1.45,
        primary_regime="TREND",
        regime_prob_max=0.65,
        market_data={"volume_delta_override": True},
    )
    assert result["uncertain"] is False
    assert "LEGACY_RAW_TREND_OVERRIDE" in result["threshold_source"]


def test_probability_vector_never_uses_legacy_trend_override():
    result = evaluate_regime_entropy_gate(
        probabilities={regime: 0.2 for regime in REGIMES},
        primary_regime="TREND",
        regime_prob_max=0.65,
        market_data={
            "volume_delta_override": True,
            "depth_imbalance": 0.8,
            "feature_quality_status": VALID,
        },
    )
    assert result["uncertain"] is True
    assert "LEGACY_RAW_TREND_OVERRIDE" not in result["threshold_source"]


def test_clear_trend_is_discriminative_not_high_entropy(tmp_path):
    out = heuristic_model(tmp_path).predict(
        valid_features(
            adx=35.0,
            vol_z=0.5,
            atr_pct=0.008,
            iv_mean=0.18,
            oi_delta=3_000_000.0,
            oi_gross=10_000_000.0,
            depth_imbalance=0.4,
            x_regime_align=0.5,
        )
    )
    assert out["primary_regime"] == "TREND"
    assert out["regime_status"] == VALID
    assert out["regime_prob_max"] >= 0.80
    assert out["regime_entropy_normalized"] < out["regime_entropy_threshold"]


def test_clear_range_is_discriminative_not_high_entropy(tmp_path):
    out = heuristic_model(tmp_path).predict(
        valid_features(
            adx=10.0,
            vol_z=-0.5,
            atr_pct=0.003,
            iv_mean=0.15,
            oi_delta=0.0,
            depth_imbalance=0.0,
        )
    )
    assert out["primary_regime"] == "RANGE"
    assert out["regime_status"] == VALID
    assert out["regime_prob_max"] >= 0.90


def test_clear_range_volatile_is_discriminative(tmp_path):
    out = heuristic_model(tmp_path).predict(
        valid_features(
            adx=14.0,
            vol_z=1.8,
            atr_pct=0.011,
            iv_mean=0.25,
            oi_delta=0.0,
            depth_imbalance=0.0,
        )
    )
    assert out["primary_regime"] == "RANGE_VOLATILE"
    assert out["regime_status"] == VALID
    assert out["regime_prob_max"] >= 0.75


def test_structurally_mixed_inputs_remain_uncertain(tmp_path):
    out = heuristic_model(tmp_path).predict(
        valid_features(
            adx=28.0,
            vol_z=1.4,
            atr_pct=0.003,
            iv_mean=0.20,
            shock_score=0.1,
            uncertainty_index=0.2,
            oi_delta=0.0,
            depth_imbalance=0.0,
        )
    )
    assert out["regime_status"] == UNCERTAIN
    assert out["regime_entropy_normalized"] > out["regime_entropy_threshold"]
    assert out["regime_prob_max"] < 0.40


def test_panic_requires_normalized_acceleration_and_transition_evidence(tmp_path):
    out = heuristic_model(tmp_path).predict(
        valid_features(
            adx=30.0,
            vol_z=2.5,
            atr_pct=0.015,
            iv_mean=0.60,
            shock_score=0.9,
            uncertainty_index=0.8,
            regime_transition_rate=8.0,
            ltp_acceleration_atr=1.0,
            x_lead_lag=1.0,
            macro_direction_bias=-1.0,
        )
    )
    assert out["primary_regime"] == "PANIC"
    assert out["regime_status"] == VALID
    assert out["regime_prob_max"] >= 0.65


def test_heuristic_provenance_explicitly_says_uncalibrated(tmp_path):
    out = heuristic_model(tmp_path).predict(valid_features())
    assert out["model_source"] == "HEURISTIC_STRUCTURAL_V2_UNCALIBRATED"
    assert out["probability_calibrated"] is False
    assert out["probability_semantics"] == (
        "deterministic_structural_pseudo_probability"
    )
    assert "vwap_slope" in out["feature_quality"]["ignored_unscaled_inputs"]
    assert "ltp_acceleration" in out["feature_quality"]["ignored_unscaled_inputs"]


def test_gaussian_model_missing_declared_feature_fails_closed(tmp_path):
    model_path = tmp_path / "regime_model.json"
    payload = {
        "feature_names": ["adx", "atr_pct"],
        "calibrated": False,
        "priors": {regime: 0.2 for regime in REGIMES},
        "means": {
            regime: {"adx": 20.0, "atr_pct": 0.005}
            for regime in REGIMES
        },
        "vars": {
            regime: {"adx": 10.0, "atr_pct": 0.0001}
            for regime in REGIMES
        },
    }
    model_path.write_text(json.dumps(payload), encoding="utf-8")
    out = RegimeProbModel(str(model_path)).predict({"adx": 25.0})
    assert out["regime_status"] == INSUFFICIENT_DATA
    assert out["primary_regime"] == "UNKNOWN"
    assert out["feature_quality"]["missing_required"] == ["atr_pct"]


def test_stabilizer_ignores_duplicate_bar_and_requires_confirmation():
    stabilizer = RegimeStabilizer(
        confirmation_bars=3,
        minimum_dwell_bars=0,
    )
    one = stabilizer.update(
        symbol="NIFTY",
        completed_bar=1,
        instantaneous_regime="TREND",
        top_probability=0.7,
        status=VALID,
    )
    duplicate = stabilizer.update(
        symbol="NIFTY",
        completed_bar=1,
        instantaneous_regime="TREND",
        top_probability=0.7,
        status=VALID,
    )
    two = stabilizer.update(
        symbol="NIFTY",
        completed_bar=2,
        instantaneous_regime="TREND",
        top_probability=0.7,
        status=VALID,
    )
    three = stabilizer.update(
        symbol="NIFTY",
        completed_bar=3,
        instantaneous_regime="TREND",
        top_probability=0.7,
        status=VALID,
    )
    assert one["stable_regime"] == "UNKNOWN"
    assert duplicate["transition_confirmation_count"] == 1
    assert two["stable_regime"] == "UNKNOWN"
    assert three["stable_regime"] == "TREND"


def test_event_fast_path_requires_high_probability():
    stabilizer = RegimeStabilizer(
        confirmation_bars=3,
        minimum_dwell_bars=0,
        fast_event_probability=0.80,
    )
    low = stabilizer.update(
        symbol="SENSEX",
        completed_bar=1,
        instantaneous_regime="EVENT",
        top_probability=0.79,
        status=VALID,
    )
    assert low["stable_regime"] == "UNKNOWN"
    high = stabilizer.update(
        symbol="BANKNIFTY",
        completed_bar=1,
        instantaneous_regime="PANIC",
        top_probability=0.85,
        status=VALID,
    )
    assert high["stable_regime"] == "PANIC"
