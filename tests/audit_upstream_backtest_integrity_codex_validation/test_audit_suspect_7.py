import pytest
import pandas as pd
from pathlib import Path
from core.option_backtest.adapter import _derive_timing_fields
from core.option_backtest.models import OptionBacktestConfig, ResearchMode

def test_suspect_7_naive_timestamp_localization():
    config = OptionBacktestConfig(
        symbol="NIFTY",
        data_path=Path("."),
        research_mode=ResearchMode.PROXY_RESEARCH,
        timezone="Asia/Kolkata"
    )
    
    cases = [
        "2024-01-01 09:15:00", # naive
        "2024-01-01T09:15:00+05:30", # offset
        "2024-01-01T03:45:00Z" # UTC
    ]
    
    for case in cases:
        row = {
            "timestamp": pd.Timestamp("2024-01-01 09:15:00"),
            "feature_cutoff_ts": case,
            "signal_ts": case,
            "earliest_entry_ts": case
        }
        
        fc, sig, ee, age = _derive_timing_fields(row, config)
        
        parsed = pd.Timestamp(fc)
        # Verify that it correctly maps to 9 AM IST.
        assert parsed.hour == 9, f"Timestamp mapping failed for {case}"
