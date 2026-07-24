import pandas as pd

from core.tearsheet import generate_tearsheet


def test_oos_metrics_are_calculated_only_from_oos_rows_with_nondefault_index():
    trades = pd.DataFrame(
        {
            "pl": [100.0, 100.0, -10.0, -20.0],
            "outcome": ["TARGET", "TARGET", "STOP", "STOP"],
            "is_oos": [False, False, True, True],
        },
        index=[10, 20, 30, 40],
    )

    metrics = generate_tearsheet(trades)

    assert metrics["after_cost_expectancy"] == 42.5
    assert metrics["oos_trade_count"] == 2
    assert metrics["after_cost_expectancy_oos"] == -15.0
    assert metrics["profit_factor_oos"] == 0.0
    assert metrics["total_pnl_oos"] == -30.0
    assert metrics["win_rate_pct_oos"] == 0.0
    assert metrics["max_drawdown_abs_oos"] == -30.0


def test_no_oos_rows_return_none_oos_metrics():
    trades = pd.DataFrame(
        {"pl": [10.0, -5.0], "outcome": ["TARGET", "STOP"]}
    )
    metrics = generate_tearsheet(trades)

    assert metrics["oos_trade_count"] == 0
    assert metrics["profit_factor_oos"] is None
    assert metrics["after_cost_expectancy_oos"] is None


def test_first_trade_loss_drawdown_is_measured_from_initial_capital():
    trades = pd.DataFrame(
        {"pl": [-100.0, 25.0], "outcome": ["STOP", "TARGET"]}
    )
    metrics = generate_tearsheet(trades, initial_capital=1000.0)

    assert metrics["max_drawdown_abs"] == -100.0
    assert metrics["max_drawdown_pct"] == -10.0


def test_all_zero_pnl_has_zero_not_infinite_profit_factor():
    trades = pd.DataFrame(
        {"pl": [0.0, 0.0], "outcome": ["TIMEOUT", "TIMEOUT"]}
    )
    metrics = generate_tearsheet(trades)

    assert metrics["profit_factor"] == 0.0
    assert metrics["after_cost_expectancy"] == 0.0
