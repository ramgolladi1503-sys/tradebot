import pytest
from core.regime_entropy_gate import evaluate_regime_entropy_gate
from core.market_data import _derive_unstable_reasons

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
