import pytest
from core.regime_entropy_gate import evaluate_regime_entropy_gate
from core.market_data import _derive_unstable_reasons
from core.regime_prob_model import RegimeProbModel
from core.regime_session_context import resolve_canonical_session_context

def test_entropy_range_override():
    result = evaluate_regime_entropy_gate(
        raw_entropy=1.327,
        probabilities={},
        regime_count=5,
        primary_regime='RANGE',
        market_data={"symbol": "BANKNIFTY"}
    )
    assert result['threshold'] == 1.0
    assert result['uncertain'] == False

def test_entropy_no_primary_regime_fails_closed():
    result = evaluate_regime_entropy_gate(
        raw_entropy=1.327,
        probabilities={},
        regime_count=5,
        primary_regime='',
        market_data={"symbol": "BANKNIFTY"}
    )
    assert result['threshold'] == 0.80
    assert result['uncertain'] == True

def test_entropy_nifty_trend():
    result = evaluate_regime_entropy_gate(
        raw_entropy=1.1,
        probabilities={},
        regime_count=5,
        primary_regime='TREND_UP',
        market_data={"symbol": "NIFTY"}
    )
    assert result['threshold'] == 0.80
    assert result['uncertain'] == False

def test_derive_unstable_reasons_banknifty_range():
    reasons = _derive_unstable_reasons(
        indicators_ok=True,
        ohlc_bars_count=100,
        min_bars=50,
        regime_probs={},
        regime_entropy=1.327,
        regime_transition_rate=0.0,
        primary_regime="RANGE",
        symbol="BANKNIFTY"
    )
    assert "entropy_too_high" not in reasons

def test_derive_unstable_reasons_missing_regime():
    reasons = _derive_unstable_reasons(
        indicators_ok=True,
        ohlc_bars_count=100,
        min_bars=50,
        regime_probs={},
        regime_entropy=1.327,
        regime_transition_rate=0.0,
        primary_regime="",
        symbol="BANKNIFTY"
    )
    assert "entropy_too_high" in reasons

def test_derive_unstable_reasons_sensex_range_volatile_policy():
    reasons = _derive_unstable_reasons(
        indicators_ok=True,
        ohlc_bars_count=100,
        min_bars=50,
        regime_probs={},
        regime_entropy=1.350,
        regime_transition_rate=0.0,
        primary_regime="RANGE_VOLATILE",
        symbol="SENSEX"
    )
    assert "entropy_too_high" not in reasons

def test_derive_unstable_reasons_nifty_trend():
    reasons = _derive_unstable_reasons(
        indicators_ok=True,
        ohlc_bars_count=100,
        min_bars=50,
        regime_probs={},
        regime_entropy=1.327,
        regime_transition_rate=0.0,
        primary_regime="TREND_UP",
        symbol="NIFTY"
    )
    assert "entropy_too_high" in reasons


def test_canonical_session_context_boundaries():
    assert resolve_canonical_session_context("2026-07-02T09:20:00+05:30").canonical_session_bucket == "OPEN_DISCOVERY"
    assert resolve_canonical_session_context("2026-07-02T11:00:00+05:30").canonical_session_bucket == "MID_SESSION"
    assert resolve_canonical_session_context("2026-07-02T15:10:00+05:30").canonical_session_bucket == "CLOSING_VOL"


def test_regime_prob_model_derives_session_bucket_from_timestamp(monkeypatch):
    from config import config as config_module

    monkeypatch.setattr(config_module, "REGIME_ENTROPY_NORMALIZED_MAX_OPEN_DISCOVERY", 0.6, raising=False)
    monkeypatch.setattr(config_module, "REGIME_ENTROPY_NORMALIZED_MAX_DEFAULT", 0.2, raising=False)
    model = RegimeProbModel()
    model.model = None
    out = model.predict(
        {
            "timestamp_ist": "2026-07-02T09:20:00+05:30",
            "adx": 0.0,
            "vwap_slope": 0.0,
            "vol_z": 0.0,
            "atr_pct": 0.0,
            "iv_mean": 0.0,
            "ltp_acceleration": 0.0,
            "option_chain_skew": 0.0,
            "oi_delta": 0.0,
            "depth_imbalance": 0.0,
            "regime_transition_rate": 0.0,
            "shock_score": 0.0,
            "uncertainty_index": 0.0,
            "macro_direction_bias": 0.0,
            "x_regime_align": 0.0,
            "x_vol_spillover": 0.0,
            "x_lead_lag": 0.0,
        }
    )
    assert out["regime_entropy_threshold"] == 0.6
