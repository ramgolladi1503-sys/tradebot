from core.setup_profile_rejection import evaluate_profile_rejection_setup


def test_detects_valid_rejection_setup():
    candidate = {
        "current_price": 105,
        "session_profile": {"vah": 100, "poc": 90, "lvns": [{"price": 95}]},
        "latest_candle": {"open": 104, "close": 101, "high": 106, "low": 100},
        "regime": "RANGE",
    }

    setup = evaluate_profile_rejection_setup(candidate)

    assert setup.detected is True
    assert setup.direction == "SELL"
    assert setup.rr > 1.0


def test_blocks_without_rejection():
    candidate = {
        "current_price": 105,
        "session_profile": {"vah": 100, "poc": 90},
        "latest_candle": {"open": 100, "close": 105, "high": 106, "low": 99},
        "regime": "RANGE",
    }

    setup = evaluate_profile_rejection_setup(candidate)

    assert setup.detected is False


def test_blocks_in_trend_countertrend():
    candidate = {
        "current_price": 105,
        "session_profile": {"vah": 100, "poc": 90},
        "latest_candle": {"open": 104, "close": 101, "high": 106, "low": 100},
        "regime": "TREND",
        "countertrend": True,
    }

    setup = evaluate_profile_rejection_setup(candidate)

    assert setup.detected is False
