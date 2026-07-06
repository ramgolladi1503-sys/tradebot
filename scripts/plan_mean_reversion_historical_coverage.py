#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, required=False)
    parser.add_argument("--end-date", type=str, required=False)
    parser.add_argument("--symbols", nargs="+", required=False)
    parser.add_argument("--interval", type=str, default="1minute")
    parser.add_argument("--max-days-per-chunk", type=int, default=30)
    args = parser.parse_args()

    base_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    plan = {
        "classification": "MEAN_REVERSION_HISTORICAL_FETCH_PLAN_READY",
        "symbols": ["NIFTY", "BANKNIFTY"],
        "interval": "1minute",
        "mode": "CANDLE_LEVEL_RESEARCH",
        "minimum_backtest_trading_days": 30,
        "minimum_wfa_windows": 6,
        "suggested_wfa_design": {
            "train_window": "3 months",
            "test_window": "1 month",
            "rolling_walk_forward": True
        },
        "preferred_date_range": {
            "start": "2024-01-01",
            "end": "2026-07-03"
        },
        "chunk_size_days": 30,
        "resume_supported": True,
        "fetched_market_data_committed": False
    }

    with open(base_dir / "historical_coverage_plan.json", "w") as f:
        json.dump(plan, f, indent=2)

    with open(base_dir / "historical_coverage_plan.md", "w") as f:
        f.write("# MEAN_REVERSION_EXTENSION Historical Coverage Plan\n\n")
        f.write(f"- Classification: {plan['classification']}\n")
        f.write(f"- Symbols: {plan['symbols']}\n")
        f.write(f"- Min backtest days: {plan['minimum_backtest_trading_days']}\n")
        
    print(f"Generated fetch plan. Classification: {plan['classification']}")

if __name__ == "__main__":
    main()
