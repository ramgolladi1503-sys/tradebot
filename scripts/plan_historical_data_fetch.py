#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, default="2024-01-01")
    parser.add_argument("--end-date", type=str, default="2026-07-03")
    parser.add_argument("--symbols", nargs="+", default=["NIFTY", "BANKNIFTY"])
    parser.add_argument("--interval", type=str, default="1minute")
    parser.add_argument("--max-days-per-chunk", type=int, default=30)
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")

    chunks = []
    for symbol in args.symbols:
        curr_dt = start_dt
        while curr_dt <= end_dt:
            chunk_end = min(curr_dt + timedelta(days=args.max_days_per_chunk - 1), end_dt)
            chunks.append({
                "symbol": symbol,
                "start_date": curr_dt.strftime("%Y-%m-%d"),
                "end_date": chunk_end.strftime("%Y-%m-%d"),
                "interval": args.interval
            })
            curr_dt = chunk_end + timedelta(days=1)

    plan = {
        "chunks": chunks,
        "expected_artifact_paths": [
            f"runtime/upstox_candidate_replay/history_{chunk['symbol']}_{chunk['start_date']}_{chunk['end_date']}.parquet"
            for chunk in chunks
        ],
        "estimated_calls": len(chunks),
        "rate_limit_strategy": "Sleep 1s per chunk to avoid hitting rate limits. Backoff if 429 received.",
        "resume_support": True,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }

    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "historical_data_fetch_plan.json", "w") as f:
        json.dump(plan, f, indent=2)

    with open(out_dir / "historical_data_fetch_plan.md", "w") as f:
        f.write("# Historical Data Fetch Plan\n\n")
        f.write(f"- Chunks: {len(chunks)}\n")
        f.write(f"- Start: {args.start_date}\n")
        f.write(f"- End: {args.end_date}\n")
        f.write(f"- Symbols: {', '.join(args.symbols)}\n")

    print(f"Generated fetch plan with {len(chunks)} chunks.")

if __name__ == "__main__":
    main()
