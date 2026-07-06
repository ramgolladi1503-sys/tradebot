#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timedelta

def main():
    strat_id = "MEAN_REVERSION_EXTENSION"
    out_dir = Path(f"runtime/strategy_validation/{strat_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    start_date = datetime(2026, 4, 1)
    end_date = datetime(2026, 7, 3)
    symbols = ["NIFTY", "BANKNIFTY"]
    max_days_per_chunk = 7
    interval = "1minute"
    
    chunks = []
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=max_days_per_chunk - 1), end_date)
        chunks.append({
            "start_date": current.strftime("%Y-%m-%d"),
            "end_date": chunk_end.strftime("%Y-%m-%d"),
            "status": "pending"
        })
        current = chunk_end + timedelta(days=1)
        
    estimated_api_calls = len(chunks) * len(symbols)
    
    plan = {
        "strategy_id": strat_id,
        "mode": "CANDLE_LEVEL_RESEARCH_ONLY",
        "symbols": symbols,
        "interval": interval,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "chunk_size_days": max_days_per_chunk,
        "estimated_api_calls": estimated_api_calls,
        "resume_supported": True,
        "rate_limit_backoff_behavior": "exponential_backoff_on_429",
        "chunks": chunks,
        "paper_live_allowed": False,
        "live_allowed": False,
        "execution_allowed": False,
        "no_secret_values_logged": True,
        "fetched_market_data_committed": False
    }
    
    with open(out_dir / "historical_coverage_plan.json", "w") as f:
        json.dump(plan, f, indent=2)
        
    with open(out_dir / "historical_coverage_plan.md", "w") as f:
        f.write("# Historical Coverage Plan\n\n")
        f.write(f"- Mode: CANDLE_LEVEL_RESEARCH_ONLY\n")
        f.write(f"- Estimated API Calls: {estimated_api_calls}\n")
        f.write(f"- Resume Supported: True\n")
        f.write(f"- Live Flags: All False\n")

    print("Planned historical coverage.")

if __name__ == "__main__":
    main()
