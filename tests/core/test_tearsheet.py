import pandas as pd
from core.tearsheet import generate_tearsheet

def test_generate_tearsheet_negative_expectancy_warning():
    # Trades that have negative expectancy
    trades = pd.DataFrame([
        {"entry_idx": 1, "pl": 100, "outcome": "TARGET"},
        {"entry_idx": 2, "pl": -200, "outcome": "STOP"},
        {"entry_idx": 3, "pl": -100, "outcome": "STOP"},
    ])
    
    metrics = generate_tearsheet(trades)
    
    assert metrics["after_cost_expectancy"] < 0
    assert "WARNING: Negative or zero after-cost expectancy! Win rate is irrelevant." in metrics["warnings"]
    assert metrics["win_rate_pct"] == (1/3) * 100.0

def test_generate_tearsheet_positive_expectancy_no_warning():
    # Trades that have positive expectancy
    trades = pd.DataFrame([
        {"entry_idx": 1, "pl": 200, "outcome": "TARGET"},
        {"entry_idx": 2, "pl": 100, "outcome": "TARGET"},
        {"entry_idx": 3, "pl": -100, "outcome": "STOP"},
    ])
    
    metrics = generate_tearsheet(trades)
    
    assert metrics["after_cost_expectancy"] > 0
    assert "WARNING: Negative or zero after-cost expectancy! Win rate is irrelevant." not in metrics["warnings"]

def test_generate_tearsheet_oos_profit_factor():
    trades = pd.DataFrame([
        {"entry_idx": 1, "pl": 200, "outcome": "TARGET", "is_oos": True},
        {"entry_idx": 2, "pl": 100, "outcome": "TARGET", "is_oos": False},
        {"entry_idx": 3, "pl": -100, "outcome": "STOP", "is_oos": True},
    ])
    
    metrics = generate_tearsheet(trades)
    
    assert metrics["profit_factor_oos"] == 2.0  # (200 / 100)
