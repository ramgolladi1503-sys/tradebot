import json
import os
import pandas as pd
from core.option_backtest.adapter import _derive_timing_fields
from core.option_backtest.models import OptionBacktestConfig, ResearchMode
from pathlib import Path

def test_suspect_7():
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
    
    has_bug = False
    
    for case in cases:
        row = {
            "timestamp": pd.Timestamp("2024-01-01 09:15:00"),
            "feature_cutoff_ts": case,
            "signal_ts": case,
            "earliest_entry_ts": case
        }
        
        fc, sig, ee, age = _derive_timing_fields(row, config)
        
        parsed = pd.Timestamp(fc)
        if parsed.hour != 9:
            has_bug = True
            
    result = {
        "suspect_id": "7",
        "name": "Naive timestamp localization",
        "classification": "CONFIRMED_CORRUPTION" if has_bug else "NOT_A_BUG",
        "expected_value_rule": "All inputs should map to 09:15 local time.",
        "actual_value": f"Has bug: {has_bug}",
        "bias": "Incorrect localization shifts backtest events." if has_bug else "Works as expected."
    }

    out_path = "runtime/research/upstream_backtest_integrity_antigravity/timezone_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    existing = []
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try: existing = json.load(f)
            except: pass
    if not isinstance(existing, list): existing = []
    existing = [r for r in existing if r.get("suspect_id") != "7"]
    existing.append(result)
    
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    test_suspect_7()
