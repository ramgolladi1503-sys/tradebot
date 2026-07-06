#!/usr/bin/env python3
import json
import argparse
import pandas as pd
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=str, required=True)
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()
    
    root = Path(args.root)
    out_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if not root.exists():
        print("No upstox replay data found.")
        return
        
    audit_results = []
    failed_blockers = set()
    
    for d_path in root.iterdir():
        if d_path.is_dir() and d_path.name.isdigit():
            underlying_dir = d_path / "underlying"
            if underlying_dir.exists():
                for pq_file in underlying_dir.glob("*.parquet"):
                    df = pd.read_parquet(pq_file)
                    
                    row_count = len(df)
                    is_usable = row_count >= 50
                    
                    if row_count < 50:
                        failed_blockers.add("CANDLE_FILE_TOO_FEW_ROWS")
                    if row_count == 1:
                        failed_blockers.add("NO_USABLE_INTRADAY_SEQUENCE")
                        
                    if 'timestamp' not in df.columns:
                        failed_blockers.add("CANDLE_FILE_MISSING_TIMESTAMP")
                    elif df['timestamp'].isnull().any():
                        failed_blockers.add("CANDLE_FILE_MISSING_TIMESTAMP")
                        
                    if df['timestamp'].duplicated().any():
                        failed_blockers.add("CANDLE_FILE_DUPLICATE_TIMESTAMPS")
                        
                    for col in ['open', 'high', 'low', 'close']:
                        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                            failed_blockers.add("CANDLE_FILE_INVALID_OHLC")
                    
                    audit_results.append({
                        "file_path": str(pq_file),
                        "symbol": pq_file.stem.split("_")[0],
                        "row_count": row_count,
                        "usable_for_t_plus_1": row_count > 1,
                        "enough_intraday_rows": is_usable
                    })
                    
    failed_blockers = list(failed_blockers)
    
    if not audit_results:
        classification = "UPSTOX_CANDLE_FILES_INVALID"
    elif failed_blockers:
        classification = "UPSTOX_CANDLE_FILES_INVALID"
    else:
        classification = "UPSTOX_CANDLE_FILES_VALID"
        
    audit_report = {
        "classification": classification,
        "files_audited": len(audit_results),
        "blockers": failed_blockers,
        "details": audit_results
    }
    
    with open(out_dir / "upstox_candle_file_audit.json", "w") as f:
        json.dump(audit_report, f, indent=2)
        
    with open(out_dir / "upstox_candle_file_audit.md", "w") as f:
        f.write("# Upstox Candle File Audit\n\n")
        f.write(f"- Classification: {classification}\n")
        f.write(f"- Files Audited: {len(audit_results)}\n")
        if failed_blockers:
            f.write(f"- Blockers: {', '.join(failed_blockers)}\n")

    print(f"Candle files audited. Result: {classification}")

if __name__ == "__main__":
    main()
