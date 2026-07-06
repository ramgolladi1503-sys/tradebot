import json
from pathlib import Path

def test_historical_data_catalog_with_one_trading_day_blocks_phases():
    path = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_data_catalog.json")
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
            
        if data.get("trading_days_count") == 1:
            assert data.get("phase_4_can_run") is False
            assert data.get("phase_5_wfa_can_run") is False
            assert "INSUFFICIENT_HISTORICAL_DAYS_FOR_BACKTEST" in data.get("blockers", [])
            assert "MINIMUM_WFA_WINDOWS_NOT_MET" in data.get("blockers", [])
            assert data.get("classification") == "MEAN_REVERSION_HISTORICAL_CATALOG_BLOCKED"
            
def test_historical_data_catalog_validates_data_integrity():
    path = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_data_catalog.json")
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
            
        # These fields must exist in the report to ensure checks happened
        assert "duplicate_timestamps" in data
        assert "invalid_ohlc_rows" in data
        
        # In a real validation context, if these were True, Phase 4 would be blocked
        if data.get("duplicate_timestamps") is True:
            assert "DUPLICATE_TIMESTAMPS" in data.get("blockers", [])
        if data.get("invalid_ohlc_rows") is True:
            assert "INVALID_OHLC_ROWS" in data.get("blockers", [])
