#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

def main() -> int:
    parser = argparse.ArgumentParser(description="Audit live option truth capture.")
    parser.add_argument("--input", type=Path, help="Input data file (jsonl, parquet, csv, etc.)")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--out-dir", type=Path, default=Path("runtime/live_evidence"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    
    verdict = "OPTION_TRUTH_READY"
    
    if not args.input or not args.input.exists() or args.input.stat().st_size == 0:
        verdict = "NOT_READY_FOR_EXECUTABLE_REPLAY"
        df = pd.DataFrame()
    else:
        try:
            if args.input.suffix == ".csv":
                df = pd.read_csv(args.input)
            elif args.input.suffix == ".parquet":
                df = pd.read_parquet(args.input)
            elif args.input.suffix == ".json" or args.input.suffix == ".jsonl":
                df = pd.read_json(args.input, lines=args.input.suffix == ".jsonl")
            else:
                df = pd.DataFrame()
                verdict = "NOT_READY_FOR_EXECUTABLE_REPLAY"
        except Exception:
            df = pd.DataFrame()
            verdict = "NOT_READY_FOR_EXECUTABLE_REPLAY"

    if verdict == "OPTION_TRUTH_READY" and df.empty:
        verdict = "NOT_READY_FOR_EXECUTABLE_REPLAY"
        
    if verdict == "OPTION_TRUTH_READY":
        cols = set(df.columns)
        if not {"ltp"}.intersection(cols):
            verdict = "MISSING_OPTION_LTP"
        elif not {"bid", "best_bid"}.intersection(cols) or not {"ask", "best_ask"}.intersection(cols):
            verdict = "MISSING_BID_ASK"
        elif not {"spread", "spread_pct"}.intersection(cols):
            verdict = "MISSING_SPREAD"
        elif not {"quote_age_sec", "option_quote_age_sec", "age_ms", "age_sec", "quote_age"}.intersection(cols):
            verdict = "MISSING_QUOTE_AGE"
        elif not {"candidate_id"}.intersection(cols) or not {"instrument_id", "symbol", "tradingsymbol"}.intersection(cols):
            verdict = "MISSING_CANDIDATE_LINKAGE"
        elif "reason" in cols and "executable" in cols:
            # Check if fallback/advisory candidate is marked executable
            fallback_rows = df[df["reason"].astype(str).str.contains("fallback|advisory|recovered", case=False, na=False)]
            if not fallback_rows.empty and fallback_rows["executable"].any():
                verdict = "NOT_READY_FOR_EXECUTABLE_REPLAY"

    report = {
        "verdict": verdict,
        "date": args.date,
        "input": str(args.input) if args.input else None,
    }
    
    json_path = args.out_dir / f"option_truth_capture_report_{args.date}.json"
    json_path.write_text(json.dumps(report, indent=2))
    
    md_path = args.out_dir / f"option_truth_capture_report_{args.date}.md"
    md_content = f"# Option Truth Capture Report {args.date}\n\n**Verdict**: {verdict}\n"
    md_path.write_text(md_content)
    
    print(f"Generated {json_path} and {md_path}")
    print(f"Verdict: {verdict}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
