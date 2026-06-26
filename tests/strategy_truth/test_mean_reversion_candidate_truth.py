from core.mean_reversion_candidate_generator import build_mean_reversion_candidate_intents

def _mock_market_state(overrides):
    base = {
        "instrument": "NIFTY",
        "ltp": 100.0,
        "vwap": 100.0,
        "oscillator": 0.0,
        "regime": "RANGE",
    }
    base.update(overrides)
    return base

def test_mean_reversion_valid_bullish_maps_correctly():
    # To get BUY_CALL, we need ltp < vwap by at least 30 bps. (e.g. 99.6, vwap 100.0 => -40 bps)
    # We also need oscillator >= 0.2 (if min_oscillator_confirmation is 0.2)
    state = _mock_market_state({"ltp": 99.6, "vwap": 100.0, "oscillator": 0.5})
    report = build_mean_reversion_candidate_intents(
        state,
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    assert report.valid is True
    intent = report.generated_intents[0]
    assert intent.direction == "BUY_CALL"
    assert intent.intent_type == "ENTRY"

def test_mean_reversion_valid_bearish_maps_correctly():
    # To get BUY_PUT, we need ltp > vwap by at least 30 bps. (e.g. 100.4, vwap 100.0 => 40 bps)
    # We also need oscillator <= -0.2
    state = _mock_market_state({"ltp": 100.4, "vwap": 100.0, "oscillator": -0.5})
    report = build_mean_reversion_candidate_intents(
        state,
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    assert report.valid is True
    intent = report.generated_intents[0]
    assert intent.direction == "BUY_PUT"
    assert intent.intent_type == "ENTRY"

def test_mean_reversion_neutral_blocks():
    # deviation too small
    state = _mock_market_state({"ltp": 100.1, "vwap": 100.0, "oscillator": 0.0})
    report = build_mean_reversion_candidate_intents(
        state,
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    intent = report.generated_intents[0]
    assert intent.intent_type == "NO_TRADE"
    assert "mean_reversion_deviation_too_small" in intent.blockers

def test_mean_reversion_nan_input_fails_closed():
    state = _mock_market_state({"ltp": float("nan")})
    report = build_mean_reversion_candidate_intents(
        state,
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    intent = report.generated_intents[0]
    assert intent.intent_type == "NO_TRADE"
    assert "mean_reversion_invalid_numeric_input" in intent.blockers
    assert "mean_reversion_missing_ltp" in intent.blockers

def test_mean_reversion_missing_input_fails_closed():
    state = {"instrument": "NIFTY"}
    report = build_mean_reversion_candidate_intents(
        state,
        min_deviation_bps=30.0,
        min_oscillator_confirmation=0.2,
    )
    intent = report.generated_intents[0]
    assert intent.intent_type == "NO_TRADE"
    assert "mean_reversion_missing_ltp" in intent.blockers
    assert "mean_reversion_missing_anchor" in intent.blockers
