import pytest
from core.regime_classifier import RegimeClassifier, get_current_regime

def test_regime_classifier_high_vol_trend():
    classifier = RegimeClassifier()
    data = {
        "iv": 22.0,
        "rv": 21.0,
        "ib_volume_ratio": 1.3,
        "is_event_day": False
    }
    regime = classifier.classify_regime(data)
    assert regime == "HIGH_VOL_TREND"

def test_regime_classifier_low_vol_chop():
    classifier = RegimeClassifier()
    data = {
        "iv": 14.0,
        "rv": 12.0,
        "ib_volume_ratio": 0.7,
        "is_event_day": False
    }
    regime = classifier.classify_regime(data)
    assert regime == "LOW_VOL_CHOP"

def test_regime_classifier_mean_revert_skew():
    classifier = RegimeClassifier()
    data = {
        "iv": 30.0,
        "rv": 20.0,
        "ib_volume_ratio": 1.0,
        "is_event_day": False
    }
    regime = classifier.classify_regime(data)
    assert regime == "MEAN_REVERT_SKEW"

def test_regime_classifier_event_shock():
    classifier = RegimeClassifier()
    data = {
        "iv": 40.0,
        "rv": 40.0,
        "ib_volume_ratio": 2.0,
        "is_event_day": True
    }
    regime = classifier.classify_regime(data)
    assert regime == "EVENT_SHOCK"

def test_regime_classifier_vrp_calculation():
    classifier = RegimeClassifier()
    vrp = classifier.calculate_volatility_risk_premium(iv=25.5, rv=20.0)
    assert vrp == 5.5

def test_get_current_regime_convenience():
    data = {
        "iv": 14.0,
        "rv": 12.0,
        "ib_volume_ratio": 0.7,
        "is_event_day": False
    }
    regime = get_current_regime(data)
    assert regime == "LOW_VOL_CHOP"
