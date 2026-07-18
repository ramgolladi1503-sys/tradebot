import pytest
import math
from research.opening_state_momentum.development_wfa_metrics import calculate_metrics, wilson_score_interval

def test_empty_metrics():
    res = calculate_metrics([], 0.0)
    assert res["trade_count"] == 0
    assert res["positive_return_count"] == 0
    assert res["mean_return"] is None
    assert res["profit_factor"] is None

def test_basic_metrics():
    returns = [0.1, -0.05, 0.05, 0.2]
    res = calculate_metrics(returns, 0.0)
    assert res["trade_count"] == 4
    assert res["positive_return_count"] == 3
    assert res["negative_return_count"] == 1
    assert res["zero_return_count"] == 0
    assert math.isclose(res["mean_return"], 0.075)
    assert math.isclose(res["median_return"], 0.075)
    assert math.isclose(res["win_rate"], 0.75)
    assert math.isclose(res["average_winner"], 0.11666666666666668)
    assert math.isclose(res["average_loser"], -0.05)
    assert math.isclose(res["payoff_ratio"], abs(0.11666666666666668 / -0.05))
    assert math.isclose(res["profit_factor"], 7.0) # (0.1+0.05+0.2)/0.05 = 0.35/0.05 = 7.0
    assert math.isclose(res["cumulative_arithmetic_return"], 0.3)
    # compounded: 1.1 * 0.95 * 1.05 * 1.2 = 1.045 * 1.05 * 1.2 = 1.09725 * 1.2 = 1.3167
    assert math.isclose(res["cumulative_compounded_return"], 0.3167)
    
    # max drawdown
    # peaks: 1.0 -> 1.1 -> 1.045 (dd: 0.05/1.1 = 0.04545) -> 1.09725 -> 1.3167
    assert math.isclose(res["maximum_drawdown"], 0.05)
    
    assert res["longest_winning_streak"] == 2
    assert res["longest_losing_streak"] == 1

def test_profit_factor_undefined():
    res = calculate_metrics([0.1, 0.2], 0.0)
    assert isinstance(res["profit_factor"], dict)
    assert res["profit_factor"]["null_reason"] == "No losses to divide by"

def test_friction_application():
    # 0.1 - 2*0.01 = 0.08
    # -0.05 - 2*0.01 = -0.07
    returns = [0.1, -0.05]
    res = calculate_metrics(returns, 0.01)
    assert math.isclose(res["mean_return"], 0.005)
    assert math.isclose(res["average_winner"], 0.08)
    assert math.isclose(res["average_loser"], -0.07)

def test_wilson_interval():
    lower, upper = wilson_score_interval(1, 4)
    # n=4, p=0.25, z=1.96
    # Should not crash
    assert 0 <= lower <= 0.25
    assert 0.25 <= upper <= 1.0
