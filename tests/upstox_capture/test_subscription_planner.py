import json
import csv
from pathlib import Path
import pytest
from core.upstox_capture.subscription_planner import build_subscription_plan

@pytest.fixture
def mock_instrument_master(tmp_path):
    instruments = [
        # Indices
        {"instrument_key": "NSE_INDEX|Nifty 50", "trading_symbol": "NIFTY 50", "instrument_type": "INDEX"},
        {"instrument_key": "NSE_INDEX|Nifty Bank", "trading_symbol": "NIFTY BANK", "instrument_type": "INDEX"},
        # Futures
        {"instrument_key": "NSE_FO|111", "name": "NIFTY", "instrument_type": "FUT", "expiry": "2026-08-27"},
        {"instrument_key": "NSE_FO|222", "name": "BANKNIFTY", "instrument_type": "FUT", "expiry": "2026-08-27"},
        # Options
        {"instrument_key": "NSE_FO|333", "name": "NIFTY", "instrument_type": "CE", "expiry": "2026-08-06", "strike_price": 24500.0},
        {"instrument_key": "NSE_FO|444", "name": "NIFTY", "instrument_type": "PE", "expiry": "2026-08-06", "strike_price": 24500.0},
        # Constituents
        {"instrument_key": "NSE_EQ|INE002A01018", "trading_symbol": "RELIANCE", "instrument_type": "EQ", "exchange": "NSE"},
        {"instrument_key": "NSE_EQ|INE040A01034", "trading_symbol": "HDFCBANK", "instrument_type": "EQ", "exchange": "NSE"}
    ]
    path = tmp_path / "complete.json"
    with open(path, "w") as f:
        json.dump(instruments, f)
    return path

def test_subscription_planner_resolution(mock_instrument_master, tmp_path):
    output_dir = tmp_path / "plan_out"
    prices = {"NIFTY": 24500.0, "BANKNIFTY": 52200.0, "SENSEX": 80000.0}

    plan = build_subscription_plan(mock_instrument_master, output_dir, prices)

    assert "full" in plan
    assert "ltpc" in plan
    
    # Verify index spot is resolved
    assert "NSE_INDEX|Nifty 50" in plan["full"]
    # Verify constituent EQ is resolved
    assert "NSE_EQ|INE002A01018" in plan["full"]
    # Verify futures are resolved
    assert "NSE_FO|111" in plan["full"]

    # Verify files created
    assert (output_dir / "universe_plan.json").exists()
    assert (output_dir / "exclusions.csv").exists()
