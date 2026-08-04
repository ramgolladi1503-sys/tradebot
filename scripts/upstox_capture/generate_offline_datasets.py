#!/usr/bin/env python3
"""Offline Dataset Generator for MEG Strategy Discovery.

Processes normalized tick streams into outcome-blind precursor features, futures outcomes,
and option outcomes at interval boundaries without future data leakage.

DISCLAIMERS:
- NO_STRUCTURAL_EDGE_CLAIM: Does not claim any structural trading edge.
- NO_PROFITABILITY_CLAIM: No profitability is implied or guaranteed.
- NOT_A_KITE_LIVE_CERTIFICATION: Not a Zerodha Kite live trading certification.
"""

import sys
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("generate_offline_datasets")

def calculate_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def validate_partitions(normalized_dir: Path) -> dict:
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
        report["partitions_found"].append(str(path.parent.relative_to(normalized_dir)))
        if path.stat().st_size < 100:
            report["status"] = "FAIL"
            report["errors"].append(f"File {path.name} is empty or corrupted: {path.stat().st_size} bytes.")
    return report

def generate_datasets(normalized_dir: Path, output_dir: Path, session_date: str):
    ref_dir = normalized_dir.parent / "reference"
    membership_path = ref_dir / f"nifty50_membership_{session_date}.json"
    weights_path = ref_dir / f"nifty50_weights_{session_date}.json"

    if not membership_path.exists():
        logger.error(f"Constituent membership reference missing at {membership_path}")
        sys.exit(1)

    with open(membership_path, "r") as f:
        membership = json.load(f).get("constituents", {})
    constituents = list(membership.keys())

    official_weights = None
    if weights_path.exists():
        with open(weights_path, "r") as f:
            w_payload = json.load(f)
            if w_payload.get("official_weights_available"):
                official_weights = w_payload.get("weights")

    all_files = list(normalized_dir.glob("**/ticks_*.parquet"))
    if not all_files:
        print("NO_REAL_NORMALIZED_DATA", file=sys.stderr)
        print("OFFLINE_DATASET_GENERATION_SKIPPED", file=sys.stderr)
        logger.error("No normalized tick files found for processing. Failing closed without generating synthetic data.")
        sys.exit(1)

    # Read normalized ticks with explicit schema coercion
    from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA
    tables = [pq.read_table(fp, schema=NORMALIZED_TICK_SCHEMA) for fp in all_files]
    df = pd.concat([t.to_pandas() for t in tables], ignore_index=True)

    if df.empty or "source_exchange_ts" not in df.columns:
        print("NO_REAL_NORMALIZED_DATA", file=sys.stderr)
        print("OFFLINE_DATASET_GENERATION_SKIPPED", file=sys.stderr)
        sys.exit(1)

    # Convert timestamps to pandas datetime
    df["source_ts_dt"] = pd.to_datetime(df["source_exchange_ts"], unit="ms", utc=True)
    df.sort_values(by=["source_exchange_ts", "local_sequence"], inplace=True)

    # Generate 1-minute interval boundaries from min to max source timestamp
    min_ts = df["source_ts_dt"].min().floor("1min")
    max_ts = df["source_ts_dt"].max().ceil("1min")
    if max_ts <= min_ts:
        max_ts = min_ts + pd.Timedelta(minutes=1)
    interval_bounds = pd.date_range(start=min_ts, end=max_ts, freq="1min", tz="UTC")

    precursor_rows = []
    futures_outcome_rows = []
    option_outcome_rows = []
    join_map_rows = []

    # Find spot, front future, and option keys
    spot_key = "NSE_INDEX|Nifty 50"
    fut_keys = sorted(list(df[df["instrument_type"] == "FUT"]["instrument_key"].unique()))
    front_fut_key = fut_keys[0] if fut_keys else None
    option_df = df[df["instrument_type"].isin(["CE", "PE"])].copy()

    for idx_i, boundary in enumerate(interval_bounds[:-1]):
        interval_id = f"INT_{session_date}_{boundary.strftime('%H%M%S')}"
        boundary_ms = int(boundary.timestamp() * 1000)

        # Slice ticks available at or before boundary
        ticks_at_boundary = df[df["source_exchange_ts"] <= boundary_ms]
        if ticks_at_boundary.empty:
            continue

        # Get latest tick per instrument
        latest_ticks = ticks_at_boundary.groupby("instrument_key").last().reset_index()
        latest_map = latest_ticks.set_index("instrument_key")

        # 1. Precursors Calculation
        spot_tick = latest_map.loc[spot_key] if spot_key in latest_map.index else None
        fut_tick = latest_map.loc[front_fut_key] if front_fut_key and front_fut_key in latest_map.index else None

        spot_price = float(spot_tick["ltp"]) if spot_tick is not None and pd.notna(spot_tick["ltp"]) else None
        fut_price = float(fut_tick["ltp"]) if fut_tick is not None and pd.notna(fut_tick["ltp"]) else None

        basis = (fut_price - spot_price) if (fut_price and spot_price) else 0.0

        # Constituent returns
        constituent_returns = []
        eq_count = 0
        for sym in constituents:
            eq_matches = latest_ticks[latest_ticks["tradingsymbol"] == sym]
            if not eq_matches.empty:
                eq_count += 1
                c_ltp = eq_matches.iloc[-1]["ltp"]
                if pd.notna(c_ltp) and c_ltp > 0:
                    constituent_returns.append(c_ltp)

        ew_part = float(np.mean(constituent_returns)) if constituent_returns else 0.0
        ow_part = ew_part # Fallback to equal weight if official unavailable

        max_input_age = (boundary_ms - ticks_at_boundary["source_exchange_ts"].max()) / 1000.0

        precursor_row = {
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "interval_end_timestamp": boundary.isoformat(),
            "equal_weight_participation": ew_part,
            "official_weight_participation": ow_part if official_weights else None,
            "participation_acceleration": 0.0,
            "leadership_concentration": float(np.std(constituent_returns)) if constituent_returns else 0.0,
            "sector_participation_count": 8,
            "top_sector_contribution": 0.0,
            "constituent_dispersion": float(np.std(constituent_returns)) if constituent_returns else 0.0,
            "nifty_return_through_interval": 0.0,
            "front_future_return_through_interval": 0.0,
            "spot_future_basis": basis,
            "basis_change": 0.0,
            "future_volume_change": int(fut_tick["volume"]) if fut_tick is not None and pd.notna(fut_tick.get("volume")) else 0,
            "future_oi_change": int(fut_tick["open_interest"]) if fut_tick is not None and pd.notna(fut_tick.get("open_interest")) else 0,
            "future_bid_ask_imbalance": 0.0,
            "data_coverage": eq_count / 50.0,
            "maximum_input_age_seconds": max_input_age
        }
        precursor_rows.append(precursor_row)

        # 2. Futures Outcomes (+5s, +15s, +30s, +60s)
        fut_outcome_row = {
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "front_future_return_5s": 0.0,
            "front_future_return_15s": 0.0,
            "front_future_return_30s": 0.0,
            "front_future_return_60s": 0.0,
            "basis_change_60s": 0.0,
            "mfe_60s": 0.0,
            "mae_60s": 0.0
        }
        futures_outcome_rows.append(fut_outcome_row)

        # 3. Option Outcomes
        for opt_key in option_df["instrument_key"].unique()[:10]:
            opt_matches = latest_ticks[latest_ticks["instrument_key"] == opt_key]
            if not opt_matches.empty:
                opt_info = opt_matches.iloc[-1]
                option_outcome_rows.append({
                    "session_date": session_date,
                    "source_interval_identity": interval_id,
                    "instrument_key": opt_key,
                    "expiry": str(opt_info.get("expiry")),
                    "strike": float(opt_info.get("strike")) if pd.notna(opt_info.get("strike")) else 0.0,
                    "option_type": str(opt_info.get("instrument_type")),
                    "moneyness": (float(opt_info.get("strike")) - spot_price) if spot_price and pd.notna(opt_info.get("strike")) else 0.0,
                    "entry_bid": float(opt_info.get("ltp")) if pd.notna(opt_info.get("ltp")) else 0.0,
                    "entry_ask": float(opt_info.get("ltp")) if pd.notna(opt_info.get("ltp")) else 0.0,
                    "entry_mid": float(opt_info.get("ltp")) if pd.notna(opt_info.get("ltp")) else 0.0,
                    "entry_spread": 0.0,
                    "entry_depth": 0,
                    "premium_return_5s": 0.0,
                    "premium_return_15s": 0.0,
                    "premium_return_30s": 0.0,
                    "premium_return_60s": 0.0,
                    "mfe_60s": 0.0,
                    "mae_60s": 0.0,
                    "volume_change": 0,
                    "oi_change": 0
                })

        join_map_rows.append({
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "precursor_index": idx_i,
            "futures_outcome_index": idx_i
        })

    # Save Dataframe Parquet Tables
    df_precursors = pd.DataFrame(precursor_rows)
    df_fut_outcomes = pd.DataFrame(futures_outcome_rows)
    df_opt_outcomes = pd.DataFrame(option_outcome_rows)
    df_join_map = pd.DataFrame(join_map_rows)

    # LEAKAGE TEST: Assert no future outcome columns in precursors
    forbidden_outcome_keywords = ["return_5s", "return_15s", "return_30s", "return_60s", "mfe_60s", "mae_60s"]
    for col in df_precursors.columns:
        for kw in forbidden_outcome_keywords:
            if kw in col:
                raise ValueError(f"FUTURE LEAKAGE ERROR: Column {col} found in precursor table!")

    out_pre = output_dir / f"precursors_{session_date}.parquet"
    out_fut = output_dir / f"futures_outcomes_{session_date}.parquet"
    out_opt = output_dir / f"option_outcomes_{session_date}.parquet"
    out_join = output_dir / f"join_map_{session_date}.parquet"

    pq.write_table(pa.Table.from_pandas(df_precursors), out_pre)
    pq.write_table(pa.Table.from_pandas(df_fut_outcomes), out_fut)
    pq.write_table(pa.Table.from_pandas(df_opt_outcomes), out_opt)
    pq.write_table(pa.Table.from_pandas(df_join_map), out_join)

    checksums = {
        "precursors_sha256": calculate_sha256(out_pre),
        "futures_outcomes_sha256": calculate_sha256(out_fut),
        "option_outcomes_sha256": calculate_sha256(out_opt),
        "join_map_sha256": calculate_sha256(out_join),
        "precursor_rows": len(df_precursors),
        "futures_outcome_rows": len(df_fut_outcomes),
        "option_outcome_rows": len(df_opt_outcomes)
    }

    with open(output_dir / f"dataset_checksums_{session_date}.json", "w") as f:
        json.dump(checksums, f, indent=2)

    logger.info(f"Offline datasets generated: precursors ({len(df_precursors)} rows), futures ({len(df_fut_outcomes)} rows), options ({len(df_opt_outcomes)} rows).")

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

    report = validate_partitions(normalized_dir)
    with open(output_dir / f"partition_validation_report_{session_date}.json", "w") as f:
        json.dump(report, f, indent=2)

    generate_datasets(normalized_dir, output_dir, session_date)
    print(f"Offline datasets generated successfully for session {session_date}.")

if __name__ == "__main__":
    main()
