from core.setup_breakout_continuation import evaluate_breakout_continuation_setup


def test_breakout_continuation_detected_from_price_action():
    result = evaluate_breakout_continuation_setup(
        {
            "symbol": "NIFTY",
            "execution_entry": 203.0,
            "day_high": 200.0,
            "day_low": 180.0,
            "candle_open": 198.0,
            "candle_close": 203.0,
        }
    )
    assert result.detected is True
    assert result.direction == "BUY_CALL"
    assert result.setup_score > 0.0
    assert result.trigger_score > 0.0
    assert result.entry_quality_score > 0.0
    assert result.rr > 0.0


def test_breakout_continuation_not_detected_for_weak_breakout():
    result = evaluate_breakout_continuation_setup(
        {
            "symbol": "NIFTY",
            "execution_entry": 200.1,
            "day_high": 200.0,
            "day_low": 180.0,
            "candle_open": 199.9,
            "candle_close": 200.0,
        }
    )
    assert result.detected is False

