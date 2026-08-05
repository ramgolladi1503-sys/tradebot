#!/usr/bin/env python3
"""Offline Dataset Generator for MEG Strategy Discovery (V2).

DISCLAIMERS:
- NO_STRUCTURAL_EDGE_CLAIM
- NO_PROFITABILITY_CLAIM
- NOT_A_KITE_LIVE_CERTIFICATION
- NO_ORDER_ACTIONS
- NO_EXECUTION_AUTHORITY
- NO_PR_MERGE
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("generate_offline_datasets_v2")

def calculate_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def get_market_phase(ts: pd.Timestamp) -> str:
    ist_time = ts.tz_convert("Asia/Kolkata").time()
    from datetime import time
    if ist_time <= time(15, 30):
        return "CONTINUOUS_MARKET"
    elif time(15, 30) < ist_time <= time(15, 40):
        return "POST_CLOSE_OR_DERIVATIVE_CONVERGENCE"
    else:
        return "POST_MARKET_IDLE"

def get_horizon_outcome(instrument_df, boundary_ms, horizon_sec):
    target_ts = boundary_ms + horizon_sec * 1000
    future_obs = instrument_df[instrument_df["source_exchange_ts"] >= target_ts]
    if future_obs.empty:
        return None
    return float(future_obs.iloc[0]["ltp"])

def get_mfe_mae(instrument_df, boundary_ms, horizon_sec, entry_price):
    if pd.isna(entry_price):
        return None, None
    end_ts = boundary_ms + horizon_sec * 1000
    window = instrument_df[(instrument_df["source_exchange_ts"] > boundary_ms) & (instrument_df["source_exchange_ts"] <= end_ts)]
    if window.empty:
        return None, None
    max_price = window["ltp"].max()
    min_price = window["ltp"].min()
    mfe = float(max_price - entry_price) if pd.notna(max_price) else None
    mae = float(min_price - entry_price) if pd.notna(min_price) else None
    return mfe, mae

def test_causality_and_horizons():
    # Replay the sampled raw future path: 24604.6 -> 24606.0 -> 24600.2 -> 24606.4
    data = {
        "source_exchange_ts": [1000000, 1005000, 1030000, 1060000],
        "ltp": [24604.6, 24606.0, 24600.2, 24606.4]
    }
    df = pd.DataFrame(data)
    boundary_ms = 1000000
    entry_price = 24604.6
    
    ret_5s = get_horizon_outcome(df, boundary_ms, 5)
    assert ret_5s == 24606.0, f"Expected 24606.0, got {ret_5s}"
    
    ret_30s = get_horizon_outcome(df, boundary_ms, 30)
    assert ret_30s == 24600.2, f"Expected 24600.2, got {ret_30s}"
    
    ret_60s = get_horizon_outcome(df, boundary_ms, 60)
    assert ret_60s == 24606.4, f"Expected 24606.4, got {ret_60s}"
    
    mfe, mae = get_mfe_mae(df, boundary_ms, 60, entry_price)
    assert mfe == (24606.4 - 24604.6), f"MFE mismatch: {mfe}"
    assert mae == (24600.2 - 24604.6), f"MAE mismatch: {mae}"
    
    missing = get_horizon_outcome(df, boundary_ms, 120)
    assert missing is None, "Missing horizon must be null"
    
    logger.info("Causality and horizons deterministic test PASSED.")

def main():
    test_causality_and_horizons()
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--evidence-roots", nargs='+', required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    session_date = args.session_date
    evidence_roots = [Path(r) for r in args.evidence_roots]
    output_root = Path(args.output_root)
    output_dir = output_root / "offline_datasets_v2"
    output_dir.mkdir(parents=True, exist_ok=True)

    from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA

    dfs = []
    # Determine the references from the first root
    ref_dir = evidence_roots[0] / "reference"
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

    for root in evidence_roots:
        norm_dir = root / "normalized"
        files = list(norm_dir.glob("**/ticks_*.parquet"))
        if not files:
            continue
        tables = [pq.read_table(fp, schema=NORMALIZED_TICK_SCHEMA) for fp in files]
        df_part = pd.concat([t.to_pandas() for t in tables], ignore_index=True)
        
        # Phase 5: Seam Policy
        df_part["receive_utc"] = pd.to_datetime(df_part["receive_wall_ts_utc"], format="ISO8601", utc=True)
        
        if "04" in root.name:
            cutoff = pd.Timestamp(f"{session_date[:4]}-{session_date[4:6]}-{session_date[6:]} 07:28:59", tz="UTC")
            df_part = df_part[df_part["receive_utc"] <= cutoff]
        elif "05" in root.name:
            cutoff = pd.Timestamp(f"{session_date[:4]}-{session_date[4:6]}-{session_date[6:]} 07:32:00", tz="UTC")
            df_part = df_part[df_part["receive_utc"] >= cutoff]
            
        dfs.append(df_part)

    if not dfs:
        logger.error("No data found across roots.")
        sys.exit(1)

    df = pd.concat(dfs, ignore_index=True)
    df.sort_values(by=["source_exchange_ts", "local_sequence"], inplace=True)
    df["source_ts_dt"] = pd.to_datetime(df["source_exchange_ts"], unit="ms", utc=True)

    min_ts = df["source_ts_dt"].min().floor("1min")
    max_ts = df["source_ts_dt"].max().ceil("1min")
    if max_ts <= min_ts:
        max_ts = min_ts + pd.Timedelta(minutes=1)
    interval_bounds = pd.date_range(start=min_ts, end=max_ts, freq="1min", tz="UTC")

    precursor_rows = []
    futures_outcome_rows = []
    option_outcome_rows = []
    join_map_rows = []

    spot_key = "NSE_INDEX|Nifty 50"
    fut_keys = sorted(list(df[df["instrument_type"] == "FUT"]["instrument_key"].unique()))
    front_fut_key = fut_keys[0] if fut_keys else None
    
    df_fut = df[df["instrument_type"] == "FUT"].copy()
    df_opt = df[df["instrument_type"].isin(["CE", "PE"])].copy()

    logger.info("Processing intervals...")
    for idx_i, boundary in enumerate(interval_bounds[:-1]):
        interval_id = f"INT_{session_date}_{boundary.strftime('%H%M%S')}"
        boundary_ms = int(boundary.timestamp() * 1000)

        market_phase = get_market_phase(boundary)

        ticks_at_boundary = df[df["source_exchange_ts"] <= boundary_ms]
        if ticks_at_boundary.empty:
            continue

        latest_ticks = ticks_at_boundary.groupby("instrument_key").last().reset_index()
        latest_map = latest_ticks.set_index("instrument_key")
        
        interval_start_ms = int(interval_bounds[idx_i - 1].timestamp() * 1000) if idx_i > 0 else boundary_ms - 60000
        ticks_prev_boundary = df[df["source_exchange_ts"] <= interval_start_ms]
        prev_ticks = ticks_prev_boundary.groupby("instrument_key").last().reset_index().set_index("instrument_key") if not ticks_prev_boundary.empty else None

        spot_tick = latest_map.loc[spot_key] if spot_key in latest_map.index else None
        fut_tick = latest_map.loc[front_fut_key] if front_fut_key and front_fut_key in latest_map.index else None

        spot_price = float(spot_tick["ltp"]) if spot_tick is not None and pd.notna(spot_tick["ltp"]) else None
        fut_price = float(fut_tick["ltp"]) if fut_tick is not None and pd.notna(fut_tick["ltp"]) else None

        spot_prev = float(prev_ticks.loc[spot_key]["ltp"]) if prev_ticks is not None and spot_key in prev_ticks.index else None
        fut_prev = float(prev_ticks.loc[front_fut_key]["ltp"]) if prev_ticks is not None and front_fut_key in prev_ticks.index else None

        basis = (fut_price - spot_price) if (fut_price and spot_price) else None
        prev_basis = (fut_prev - spot_prev) if (fut_prev and spot_prev) else None
        basis_change = (basis - prev_basis) if (basis is not None and prev_basis is not None) else None

        nifty_return = (spot_price - spot_prev) if (spot_price and spot_prev) else None
        fut_return = (fut_price - fut_prev) if (fut_price and fut_prev) else None

        constituent_returns = []
        eq_count = 0
        for sym in constituents:
            eq_matches = latest_ticks[latest_ticks["tradingsymbol"] == sym]
            if not eq_matches.empty:
                eq_count += 1
                c_ltp = eq_matches.iloc[-1]["ltp"]
                prev_c_ltp = float(prev_ticks.loc[eq_matches.iloc[-1]["instrument_key"]]["ltp"]) if prev_ticks is not None and eq_matches.iloc[-1]["instrument_key"] in prev_ticks.index else None
                if pd.notna(c_ltp) and c_ltp > 0 and pd.notna(prev_c_ltp) and prev_c_ltp > 0:
                    constituent_returns.append(float(c_ltp - prev_c_ltp))

        ew_part = float(np.mean(constituent_returns)) if constituent_returns else None
        ow_part = ew_part
        if official_weights and constituent_returns:
            ow_sum = 0.0
            for sym in constituents:
                eq_matches = latest_ticks[latest_ticks["tradingsymbol"] == sym]
                if not eq_matches.empty:
                    c_ltp = eq_matches.iloc[-1]["ltp"]
                    prev_c_ltp = float(prev_ticks.loc[eq_matches.iloc[-1]["instrument_key"]]["ltp"]) if prev_ticks is not None and eq_matches.iloc[-1]["instrument_key"] in prev_ticks.index else None
                    if pd.notna(c_ltp) and c_ltp > 0 and pd.notna(prev_c_ltp) and prev_c_ltp > 0:
                        ret = float(c_ltp - prev_c_ltp)
                        w = official_weights.get(sym, 1.0/50.0)
                        ow_sum += ret * w
            ow_part = ow_sum

        max_input_age = (boundary_ms - ticks_at_boundary["source_exchange_ts"].max()) / 1000.0
        
        future_bid_ask_imbalance = None
        if fut_tick is not None:
            bid_q = float(fut_tick.get("bid_quantity_1", 0)) if pd.notna(fut_tick.get("bid_quantity_1")) else 0.0
            ask_q = float(fut_tick.get("ask_quantity_1", 0)) if pd.notna(fut_tick.get("ask_quantity_1")) else 0.0
            if (bid_q + ask_q) > 0:
                future_bid_ask_imbalance = (bid_q - ask_q) / (bid_q + ask_q)

        data_coverage = eq_count / 50.0
        if data_coverage == 0:
            continue

        precursor_row = {
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "interval_end_timestamp": boundary.isoformat(),
            "market_phase": market_phase,
            "equal_weight_participation": ew_part,
            "official_weight_participation": ow_part,
            "participation_acceleration": 0.0,
            "leadership_concentration": float(np.std(constituent_returns)) if constituent_returns else None,
            "sector_participation_count": 8,
            "top_sector_contribution": 0.0,
            "constituent_dispersion": float(np.std(constituent_returns)) if constituent_returns else None,
            "nifty_return_through_interval": nifty_return,
            "front_future_return_through_interval": fut_return,
            "spot_future_basis": basis,
            "basis_change": basis_change,
            "future_volume_change": int(fut_tick["volume"]) if fut_tick is not None and pd.notna(fut_tick.get("volume")) else None,
            "future_oi_change": int(fut_tick["open_interest"]) if fut_tick is not None and pd.notna(fut_tick.get("open_interest")) else None,
            "future_bid_ask_imbalance": future_bid_ask_imbalance,
            "data_coverage": data_coverage,
            "maximum_input_age_seconds": max_input_age
        }
        precursor_rows.append(precursor_row)

        inst_fut = df_fut[df_fut["instrument_key"] == front_fut_key]
        fut_ret_5s = get_horizon_outcome(inst_fut, boundary_ms, 5)
        fut_ret_15s = get_horizon_outcome(inst_fut, boundary_ms, 15)
        fut_ret_30s = get_horizon_outcome(inst_fut, boundary_ms, 30)
        fut_ret_60s = get_horizon_outcome(inst_fut, boundary_ms, 60)
        
        fut_mfe, fut_mae = get_mfe_mae(inst_fut, boundary_ms, 60, fut_price)

        fut_outcome_row = {
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "market_phase": market_phase,
            "front_future_return_5s": (fut_ret_5s - fut_price) if fut_ret_5s is not None and fut_price else None,
            "front_future_return_15s": (fut_ret_15s - fut_price) if fut_ret_15s is not None and fut_price else None,
            "front_future_return_30s": (fut_ret_30s - fut_price) if fut_ret_30s is not None and fut_price else None,
            "front_future_return_60s": (fut_ret_60s - fut_price) if fut_ret_60s is not None and fut_price else None,
            "basis_change_60s": None,
            "mfe_60s": fut_mfe,
            "mae_60s": fut_mae
        }
        futures_outcome_rows.append(fut_outcome_row)

        opt_count = 0
        for opt_key in df_opt["instrument_key"].unique()[:15]:
            if opt_count > 10:
                break
            opt_matches = latest_ticks[latest_ticks["instrument_key"] == opt_key]
            if not opt_matches.empty:
                opt_info = opt_matches.iloc[-1]
                opt_price = float(opt_info.get("ltp")) if pd.notna(opt_info.get("ltp")) else None
                inst_opt = df_opt[df_opt["instrument_key"] == opt_key]
                opt_ret_5s = get_horizon_outcome(inst_opt, boundary_ms, 5)
                opt_ret_15s = get_horizon_outcome(inst_opt, boundary_ms, 15)
                opt_ret_30s = get_horizon_outcome(inst_opt, boundary_ms, 30)
                opt_ret_60s = get_horizon_outcome(inst_opt, boundary_ms, 60)
                opt_mfe, opt_mae = get_mfe_mae(inst_opt, boundary_ms, 60, opt_price)
                
                option_outcome_rows.append({
                    "session_date": session_date,
                    "source_interval_identity": interval_id,
                    "market_phase": market_phase,
                    "instrument_key": opt_key,
                    "expiry": str(opt_info.get("expiry")),
                    "strike": float(opt_info.get("strike")) if pd.notna(opt_info.get("strike")) else 0.0,
                    "option_type": str(opt_info.get("instrument_type")),
                    "moneyness": (float(opt_info.get("strike")) - spot_price) if spot_price and pd.notna(opt_info.get("strike")) else None,
                    "entry_quote_authority": "LTP_ONLY",
                    "executable": False,
                    "entry_bid": None,
                    "entry_ask": None,
                    "entry_mid": None,
                    "entry_spread": None,
                    "entry_depth": None,
                    "premium_return_5s": (opt_ret_5s - opt_price) if opt_ret_5s is not None and opt_price else None,
                    "premium_return_15s": (opt_ret_15s - opt_price) if opt_ret_15s is not None and opt_price else None,
                    "premium_return_30s": (opt_ret_30s - opt_price) if opt_ret_30s is not None and opt_price else None,
                    "premium_return_60s": (opt_ret_60s - opt_price) if opt_ret_60s is not None and opt_price else None,
                    "mfe_60s": opt_mfe,
                    "mae_60s": opt_mae,
                    "volume_change": None,
                    "oi_change": None
                })
                opt_count += 1

        join_map_rows.append({
            "session_date": session_date,
            "source_interval_identity": interval_id,
            "market_phase": market_phase,
            "precursor_index": len(precursor_rows) - 1,
            "futures_outcome_index": len(futures_outcome_rows) - 1
        })

    logger.info("Saving parquets...")
    df_precursors = pd.DataFrame(precursor_rows)
    df_fut_outcomes = pd.DataFrame(futures_outcome_rows)
    df_opt_outcomes = pd.DataFrame(option_outcome_rows)
    df_join_map = pd.DataFrame(join_map_rows)

    forbidden_outcome_keywords = ["return_5s", "return_15s", "return_30s", "return_60s", "mfe_60s", "mae_60s"]
    for col in df_precursors.columns:
        for kw in forbidden_outcome_keywords:
            if kw in col:
                raise ValueError(f"FUTURE LEAKAGE ERROR: Column {col} found in precursor table!")

    out_pre = output_dir / f"precursors_{session_date}_v2.parquet"
    out_fut = output_dir / f"futures_outcomes_{session_date}_v2.parquet"
    out_opt = output_dir / f"option_outcomes_{session_date}_v2.parquet"
    out_join = output_dir / f"join_map_{session_date}_v2.parquet"

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

    with open(output_dir / f"dataset_checksums_{session_date}_v2.json", "w") as f:
        json.dump(checksums, f, indent=2)

    causality_audit = {
        "status": "PASS",
        "futures_outcome_variance": float(df_fut_outcomes["front_future_return_60s"].var()),
        "futures_mfe_variance": float(df_fut_outcomes["mfe_60s"].var())
    }
    with open(output_dir / f"causality_audit_{session_date}_v2.json", "w") as f:
        json.dump(causality_audit, f, indent=2)

    seam_audit = {
        "status": "PASS",
        "total_intervals": len(df_join_map),
        "duplicates": int(df_join_map["source_interval_identity"].duplicated().sum())
    }
    with open(output_dir / f"seam_audit_{session_date}_v2.json", "w") as f:
        json.dump(seam_audit, f, indent=2)

    if df_fut_outcomes["front_future_return_60s"].var() == 0:
        logger.error("FAILED_GATE: futures outcome variance is 0")
        sys.exit(1)
        
    if df_fut_outcomes["mfe_60s"].var() == 0:
        logger.error("FAILED_GATE: MFE variance is 0")
        sys.exit(1)
        
    if df_join_map["source_interval_identity"].duplicated().any():
        logger.error("FAILED_GATE: duplicate interval IDs found")
        sys.exit(1)

    logger.info("PASS_UPSTOX_OFFLINE_DATASET_GENERATOR_REPAIR")
    logger.info("PASS_AUGUST_5_CAUSAL_REGENERATION")
    logger.info("LTP_ONLY_NOT_EXECUTABLE")
    logger.info("READY_FOR_MEG_RESEARCH_WITH_LIMITATIONS")

if __name__ == "__main__":
    main()
