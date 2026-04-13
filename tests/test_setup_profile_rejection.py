from core.setup_profile_rejection import evaluate_profile_rejection_setup


def test_profile_rejection_detected_from_strategy_identity():
    result = evaluate_profile_rejection_setup(
        {
            "symbol": "NIFTY",
            "strategy_family": "profile_rejection",
            "direction": "BUY_CALL",
            "execution_entry": 150.0,
            "stop_loss": 120.0,
            "target": 210.0,
        }
    )
    assert result.detected is True
    assert result.direction == "BUY_CALL"
    assert result.setup_score > 0.0
    assert result.trigger_score > 0.0
    assert result.entry_quality_score > 0.0
    assert result.rr > 0.0


def test_profile_rejection_not_detected_without_identity_hint():
    result = evaluate_profile_rejection_setup(
        {
            "symbol": "NIFTY",
            "strategy_family": "ensemble_opt",
            "direction": "BUY_CALL",
            "execution_entry": 150.0,
            "stop_loss": 120.0,
            "target": 210.0,
        }
    )
    assert result.detected is False

