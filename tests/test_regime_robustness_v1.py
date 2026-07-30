import math

from core.regime_contract_v2 import (
    INSUFFICIENT_DATA,
    INVALID_INPUT,
    RegimeStabilizer,
    VALID,
    normalize_iv,
    normalize_oi_delta,
    normalized_heuristic_scores,
    probability_diagnostics,
    stable_softmax,
)
from core.regime_prob_model import RegimeProbModel


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
    model = RegimeProbModel(str(tmp_path / "missing.json"))
    out = model.predict(valid_features(adx=None))
    assert out["regime_status"] == INSUFFICIENT_DATA
    assert out["primary_regime"] == "UNKNOWN"
    assert set(out["regime_probs"].values()) == {0.2}
    assert out["unstable_regime_flag"] is True


def test_zero_atr_is_invalid_not_confident_range(tmp_path):
    model = RegimeProbModel(str(tmp_path / "missing.json"))
    out = model.predict(valid_features(atr_pct=0.0))
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
