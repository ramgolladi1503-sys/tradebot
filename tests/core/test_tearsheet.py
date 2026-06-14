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

def test_contamination_defaults_to_unknown():
    trades = pd.DataFrame([
        {"entry_idx": 1, "pl": 200, "outcome": "TARGET"},
    ])
    metrics = generate_tearsheet(trades)
    assert metrics["contamination"]["synthetic_chain_used"] == "unknown"
    assert metrics["contamination"]["close_only_rows_used"] == "unknown"

def test_real_executable_research_blocked_in_vectorized():
    import pytest
    from core.backtest_elite import VectorizedBacktestEngine, EliteBacktestConfig
    
    config = EliteBacktestConfig(research_mode="REAL_EXECUTABLE_RESEARCH")
    with pytest.raises(ValueError, match="cannot claim REAL_EXECUTABLE_RESEARCH"):
        VectorizedBacktestEngine(pd.DataFrame(), config)

def test_allow_derived_levels_default():
    from core.option_backtest.models import OptionBacktestConfig, ResearchMode
    from pathlib import Path
    
    cfg = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path("dummy.csv"),
        research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH
    )
    assert cfg.allow_derived_levels is False
