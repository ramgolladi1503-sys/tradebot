#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

def main() -> int:
    parser = argparse.ArgumentParser(description="Audit live shadow outcome tracker.")
    parser.add_argument("--input", type=Path, help="Input data file (jsonl, parquet, csv, etc.)")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--out-dir", type=Path, default=Path("runtime/live_evidence"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    
    verdict = "LIVE_SHADOW_READY"
    
    if not args.input or not args.input.exists() or args.input.stat().st_size == 0:
        verdict = "LIVE_SHADOW_NOT_READY"
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
                verdict = "LIVE_SHADOW_NOT_READY"
        except Exception:
            df = pd.DataFrame()
            verdict = "LIVE_SHADOW_NOT_READY"

    if verdict == "LIVE_SHADOW_READY" and df.empty:
        verdict = "LIVE_SHADOW_NOT_READY"
        
    if verdict == "LIVE_SHADOW_READY":
        cols = set(df.columns)
        required_cols = {
            "candidate_id", "instrument_id", "strategy"
        }
        if not required_cols.issubset(cols):
            verdict = "LIVE_SHADOW_NOT_READY"
        elif not {"birth_timestamp", "entry_timestamp", "timestamp"}.intersection(cols):
            verdict = "LIVE_SHADOW_NOT_READY"
        elif not {"outcome_timestamp", "5m_outcome", "future_quote_path"}.intersection(cols):
            verdict = "LIVE_SHADOW_NOT_READY"
        else:
            # Ensure entry timestamp is before outcome timestamp
            entry_col = [c for c in ["entry_timestamp", "birth_timestamp", "timestamp"] if c in cols][0]
            outcome_col = [c for c in ["outcome_timestamp", "5m_outcome_timestamp"] if c in cols]
            if outcome_col:
                outcome_c = outcome_col[0]
                # check if entry < outcome
                invalid_times = df[df[entry_col] >= df[outcome_c]]
                if not invalid_times.empty:
                    verdict = "LIVE_SHADOW_NOT_READY"

    report = {
        "verdict": verdict,
        "date": args.date,
        "input": str(args.input) if args.input else None,
    }
    
    json_path = args.out_dir / f"shadow_outcome_report_{args.date}.json"
    json_path.write_text(json.dumps(report, indent=2))
    
    md_path = args.out_dir / f"shadow_outcome_report_{args.date}.md"
    md_content = f"# Shadow Outcome Report {args.date}\n\n**Verdict**: {verdict}\n"
    md_path.write_text(md_content)
    
    print(f"Generated {json_path} and {md_path}")
    print(f"Verdict: {verdict}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
