import pytest
import math
from research.opening_state_momentum.development_wfa_controls import (
    bootstrap_confidence_intervals,
    calculate_return_from_prices,
    inverted_direction_control,
    direction_randomization_control,
    chronological_concentration_control
)

def test_bootstrap():
    returns = [0.1, -0.05, 0.05, 0.2] * 5
    res = bootstrap_confidence_intervals(returns, 100, 42, 0.0)
    assert "mean_return_95_ci" in res
    assert "win_rate_95_ci" in res
    assert len(res["mean_return_95_ci"]) == 2

def test_inverted_direction():
    outcomes = [
        {"entry_price": 100, "exit_price": 110, "direction": "LONG"},
        {"entry_price": 100, "exit_price": 90, "direction": "SHORT"}
    ]
    # LONG true return: (110-100)/100 = 0.1. Inverted -> SHORT: (100-110)/100 = -0.1
    # SHORT true return: (100-90)/100 = 0.1. Inverted -> LONG: (90-100)/100 = -0.1
    res = inverted_direction_control(outcomes, 0.0)
    assert math.isclose(res["mean_return"], -0.1)

def test_direction_randomization():
    outcomes = [
        {"entry_price": 100, "exit_price": 110, "direction": "LONG"},
        {"entry_price": 100, "exit_price": 90, "direction": "SHORT"}
    ]
    # Actual mean is 0.1
    res = direction_randomization_control(outcomes, 100, 42, 0.0, 0.1)
    assert "empirical_p_value" in res
    assert 0 <= res["empirical_p_value"] <= 1.0

def test_chronological_concentration():
    returns = [0.1, -0.05, 0.05, 0.2] * 5
    res = chronological_concentration_control(returns, 100, 42, 0.0, 0.05, 1)
    assert "drawdown_p_value" in res
    assert "losing_streak_p_value" in res
