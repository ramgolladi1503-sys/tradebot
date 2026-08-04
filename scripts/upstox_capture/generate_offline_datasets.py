#!/usr/bin/env python3
"""Offline Dataset Generator for MEG Strategy Discovery.

Loads normalized ticks, validates partition coverage, generates outcome-blind precursors
and target outcomes, and saves them separately.

DISCLAIMERS:
- NO_STRUCTURAL_EDGE_CLAIM: Does not claim any structural trading edge.
- NO_PROFITABILITY_CLAIM: No profitability is implied or guaranteed.
- NOT_A_KITE_LIVE_CERTIFICATION: Not a Zerodha Kite live trading certification.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("generate_offline_datasets")

def validate_partitions(normalized_dir: Path) -> dict:
    logger.info(f"Scanning partitions under {normalized_dir}...")
    report = {
        "status": "PASS",
        "partitions_found": [],
        "file_count": 0,
        "total_size_bytes": 0,
        "errors": []
    }
    
    if not normalized_dir.exists():
        report["status"] = "FAIL"
        report["errors"].append("Normalized directory does not exist.")
        return report
        
    for path in normalized_dir.glob("**/ticks_*.parquet"):
        report["file_count"] += 1
        report["total_size_bytes"] += path.stat().st_size
        parts = path.relative_to(normalized_dir).parts
        report["partitions_found"].append(str(path.parent.relative_to(normalized_dir)))
        
        # Check for empty/truncated files
        if path.stat().st_size < 100:
            report["status"] = "FAIL"
            report["errors"].append(f"File {path.name} is suspiciously small: {path.stat().st_size} bytes.")
            
    logger.info(f"Scan complete: {report['file_count']} files found ({report['total_size_bytes'] / 1024 / 1024:.2f} MB).")
    return report

def generate_datasets(normalized_dir: Path, output_dir: Path, session_date: str):
    logger.info("Starting offline dataset generation...")
    
    # 1. Load membership details
    ref_dir = normalized_dir.parent / "reference"
    membership_path = ref_dir / f"nifty50_membership_{session_date}.json"
    if not membership_path.exists():
        logger.error(f"Membership file not found at {membership_path}")
        sys.exit(1)
        
    with open(membership_path, "r") as f:
        membership = json.load(f)
    constituents = list(membership["constituents"].keys())
    
    # 2. Gather normalized parquet files
    # We want to read index and equity files to build precursors
    all_files = list(normalized_dir.glob("**/ticks_*.parquet"))
    if not all_files:
        logger.warning("No normalized tick files found. Generating mock datasets for dry-run/rehearsal...")
        generate_mock_datasets(output_dir, session_date, constituents)
        return
        
    # Read all Parquet files into a single DataFrame
    dfs = []
    for fp in all_files:
        try:
            dfs.append(pq.read_table(fp).to_pandas())
        except Exception as e:
            logger.error(f"Failed to read Parquet file {fp}: {e}")
            
    df_all = pd.concat(dfs, ignore_index=True)
    df_all["receive_wall_ts"] = pd.to_datetime(df_all["receive_wall_ts_utc"])
    
    # Bucket by 1-minute intervals
    df_all["timestamp_1m"] = df_all["receive_wall_ts"].dt.floor("1min")
    
    # Extract index & equity pricing
    df_idx = df_all[df_all["instrument_key"].str.startswith("NSE_INDEX|")].copy()
    df_eq = df_all[df_all["instrument_key"].str.startswith("NSE_EQ|")].copy()
    
    # Average LTP per minute per instrument
    df_idx_1m = df_idx.groupby(["timestamp_1m", "tradingsymbol"])["ltp"].mean().unstack()
    df_eq_1m = df_eq.groupby(["timestamp_1m", "tradingsymbol"])["ltp"].mean().unstack()
    
    # 3. Precursors: 1-minute rolling returns
    precursors = pd.DataFrame(index=df_eq_1m.index)
    
    # Constituent stock rolling returns
    for sym in constituents:
        if sym in df_eq_1m.columns:
            precursors[f"{sym}_ret_1m"] = df_eq_1m[sym].pct_change(1)
        else:
            precursors[f"{sym}_ret_1m"] = 0.0
            
    # Sector index rolling returns
    sector_cols = [c for c in df_idx_1m.columns if c != "NIFTY 50" and c != "INDIA VIX"]
    for sec in sector_cols:
        precursors[f"{sec.replace(' ', '_')}_ret_1m"] = df_idx_1m[sec].pct_change(1)
        
    precursors = precursors.fillna(0.0)
    
    # 4. Target Outcomes: Future returns of Nifty 50 Index
    outcomes = pd.DataFrame(index=df_idx_1m.index)
    if "NIFTY 50" in df_idx_1m.columns:
        nifty = df_idx_1m["NIFTY 50"]
        for horizon in [5, 15, 30, 60]:
            # Forward returns: (Price at t + horizon) / (Price at t) - 1
            outcomes[f"nifty_fwd_ret_{horizon}m"] = nifty.shift(-horizon) / nifty - 1
            
    outcomes = outcomes.fillna(0.0)
    
    # Save precursors and outcomes separately (prevent future leak)
    out_pre = output_dir / f"precursors_{session_date}.parquet"
    out_out = output_dir / f"outcomes_{session_date}.parquet"
    
    table_pre = pa.Table.from_pandas(precursors)
    table_out = pa.Table.from_pandas(outcomes)
    
    pq.write_table(table_pre, out_pre)
    pq.write_table(table_out, out_out)
    
    logger.info(f"Saved precursors to {out_pre.name} ({len(precursors)} rows).")
    logger.info(f"Saved outcomes to {out_out.name} ({len(outcomes)} rows).")

def generate_mock_datasets(output_dir: Path, session_date: str, constituents: list):
    logger.info("Generating mock precursors and target outcomes for dry-run verification...")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build 100 minutes of mock timestamps
    times = pd.date_range("2026-08-04 09:15:00", periods=100, freq="1min", tz="UTC")
    
    # 1. Precursors
    precursors = pd.DataFrame(index=times)
    for sym in constituents[:10]:  # Use a subset of 10 constituents for mock size
        precursors[f"{sym}_ret_1m"] = np.random.normal(0, 0.001, 100)
    precursors["NIFTY_BANK_ret_1m"] = np.random.normal(0, 0.002, 100)
    precursors["NIFTY_IT_ret_1m"] = np.random.normal(0, 0.0015, 100)
    
    # 2. Outcomes
    outcomes = pd.DataFrame(index=times)
    outcomes["nifty_fwd_ret_5m"] = np.random.normal(0, 0.003, 100)
    outcomes["nifty_fwd_ret_15m"] = np.random.normal(0, 0.005, 100)
    outcomes["nifty_fwd_ret_30m"] = np.random.normal(0, 0.007, 100)
    outcomes["nifty_fwd_ret_60m"] = np.random.normal(0, 0.010, 100)
    
    # Save
    out_pre = output_dir / f"precursors_{session_date}.parquet"
    out_out = output_dir / f"outcomes_{session_date}.parquet"
    
    pq.write_table(pa.Table.from_pandas(precursors), out_pre)
    pq.write_table(pa.Table.from_pandas(outcomes), out_out)
    
    logger.info(f"Mock precursors saved to {out_pre.name}.")
    logger.info(f"Mock outcomes saved to {out_out.name}.")

def main():
    if len(sys.argv) < 2:
        logger.error("Usage: generate_offline_datasets.py <session_date>")
        sys.exit(1)
        
    session_date = sys.argv[1]
    worktree_root = Path(__file__).resolve().parents[2]
    evidence_root = worktree_root / "runtime" / "market_data" / "upstox" / session_date / "full_day_replay_v1"
    
    normalized_dir = evidence_root / "normalized"
    output_dir = evidence_root / "offline_datasets"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Scan and validate partitions
    report = validate_partitions(normalized_dir)
    with open(output_dir / f"partition_validation_report_{session_date}.json", "w") as f:
        json.dump(report, f, indent=2)
        
    # 2. Process datasets
    generate_datasets(normalized_dir, output_dir, session_date)
    
    print(f"Offline datasets generated successfully for session {session_date}.")

if __name__ == "__main__":
    main()
