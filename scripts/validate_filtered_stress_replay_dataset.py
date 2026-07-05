import argparse
import json
import pandas as pd
from pathlib import Path
import re
import warnings

# Suppress pandas warning about datetime timezone
warnings.filterwarnings('ignore', category=FutureWarning)

def validate_dataset(ticks_path, token_index_path):
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "dataset_path": str(ticks_path),
        "token_index_path": str(token_index_path),
        "classification": "FILTERED_STRESS_REPLAY_DATASET_BLOCKED",
        "certification_use_rule": "ONLY_ROWS_WITH_RESOLVED_OPTION_TOKENS_ARE_CERTIFIABLE",
        "total_rows": 0,
        "unique_tokens": 0,
        "unresolved_tokens_present": [],
        "missing_required_columns": [],
        "invalid_ltp_rows": 0,
        "invalid_bid_ask_rows": 0,
        "invalid_spread_rows": 0,
        "invalid_depth_rows": 0,
        "timestamp_start": None,
        "timestamp_end": None,
        "expected_date_from_filename": None,
        "timestamp_start_utc": None,
        "timestamp_end_utc": None,
        "timestamp_start_ist": None,
        "timestamp_end_ist": None,
        "trading_dates_ist": [],
        "date_alignment_ok": False,
        "session_rows": 0,
        "outside_session_rows": 0,
        "session_coverage_ratio": 0.0,
        "spread_summary": {
            "min": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "max": 0.0
        },
        "spread_to_ltp_summary": {
            "median": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0
        },
        "extreme_spread_rows_gt_20pct_ltp": 0,
        "extreme_spread_rows_gt_50pct_ltp": 0,
        "rows_per_token_summary": {
            "min": 0,
            "median": 0,
            "max": 0
        },
        "blockers": [],
        "warnings": [],
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }
    
    try:
        # 1. Parse date from filename
        fname = Path(ticks_path).name
        match = re.search(r'(\d{4})(\d{2})(\d{2})', fname)
        if match:
            report["expected_date_from_filename"] = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            
        with open(token_index_path) as f:
            token_index = json.load(f)
            
        resolved_tokens = set()
        for rt in token_index.get("resolved_option_tokens", []):
            resolved_tokens.add(str(rt.get("instrument_token")))
            
        df = pd.read_parquet(ticks_path)
        report["total_rows"] = len(df)
        
        required_cols = ["instrument_token", "symbol", "last_price", "best_bid", "best_ask", "depth_json"]
        ts_cols = ["local_ts", "exchange_timestamp"]
        
        missing = []
        for c in required_cols:
            if c not in df.columns:
                missing.append(c)
                
        has_ts = False
        ts_col_used = None
        for c in ts_cols:
            if c in df.columns:
                has_ts = True
                ts_col_used = c
                break
                
        if not has_ts:
            missing.append("local_ts or exchange_timestamp")
            
        report["missing_required_columns"] = missing
        
        if missing:
            report["blockers"].append("FILTERED_DATASET_MISSING_REQUIRED_COLUMNS")
            
        if "instrument_token" in df.columns:
            df["_token_str"] = df["instrument_token"].astype(str)
            unique_tokens = df["_token_str"].unique()
            report["unique_tokens"] = len(unique_tokens)
            
            unresolved = []
            for t in unique_tokens:
                if t not in resolved_tokens:
                    unresolved.append(t)
            
            report["unresolved_tokens_present"] = unresolved
            if unresolved:
                report["blockers"].append("FILTERED_DATASET_CONTAINS_UNRESOLVED_TOKENS")
                
            counts = df["_token_str"].value_counts()
            if len(counts) > 0:
                report["rows_per_token_summary"] = {
                    "min": int(counts.min()),
                    "median": int(counts.median()),
                    "max": int(counts.max())
                }
        else:
            report["blockers"].append("FILTERED_DATASET_MISSING_REQUIRED_COLUMNS")

        if "last_price" in df.columns:
            invalid_ltp = df[df["last_price"] <= 0]
            report["invalid_ltp_rows"] = len(invalid_ltp)
            if len(invalid_ltp) > 0:
                report["blockers"].append("FILTERED_DATASET_INVALID_LTP")
        else:
            report["blockers"].append("FILTERED_DATASET_MISSING_REQUIRED_COLUMNS")
            
        if "best_bid" in df.columns and "best_ask" in df.columns:
            invalid_ba = df[(df["best_bid"] <= 0) | (df["best_ask"] <= 0)]
            report["invalid_bid_ask_rows"] = len(invalid_ba)
            if len(invalid_ba) > 0:
                report["blockers"].append("FILTERED_DATASET_INVALID_BID_ASK")
                
            invalid_spread = df[df["best_ask"] < df["best_bid"]]
            report["invalid_spread_rows"] = len(invalid_spread)
            if len(invalid_spread) > 0:
                report["blockers"].append("FILTERED_DATASET_INVALID_SPREAD")
                
            valid_spreads = df[(df["best_ask"] >= df["best_bid"]) & (df["best_bid"] > 0) & (df["best_ask"] > 0) & (df["last_price"] > 0)].copy()
            if len(valid_spreads) > 0:
                valid_spreads["_spread"] = valid_spreads["best_ask"] - valid_spreads["best_bid"]
                valid_spreads["_spread_to_ltp"] = valid_spreads["_spread"] / valid_spreads["last_price"]
                
                s = valid_spreads["_spread"]
                report["spread_summary"] = {
                    "min": float(s.min()),
                    "median": float(s.median()),
                    "p95": float(s.quantile(0.95)),
                    "max": float(s.max())
                }
                
                r = valid_spreads["_spread_to_ltp"]
                report["spread_to_ltp_summary"] = {
                    "median": float(r.median()),
                    "p95": float(r.quantile(0.95)),
                    "p99": float(r.quantile(0.99)),
                    "max": float(r.max())
                }
                
                report["extreme_spread_rows_gt_20pct_ltp"] = int((r > 0.20).sum())
                report["extreme_spread_rows_gt_50pct_ltp"] = int((r > 0.50).sum())
                
                if report["extreme_spread_rows_gt_20pct_ltp"] > 0:
                    report["warnings"].append("FILTERED_DATASET_EXTREME_SPREAD_OUTLIERS")
                    
                if report["extreme_spread_rows_gt_20pct_ltp"] > len(df) * 0.10 or report["extreme_spread_rows_gt_50pct_ltp"] > len(df) * 0.05:
                    report["blockers"].append("FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH")
        else:
            report["blockers"].append("FILTERED_DATASET_MISSING_REQUIRED_COLUMNS")
            
        if "depth_json" in df.columns:
            def is_invalid_depth(d):
                if pd.isna(d): return True
                d_str = str(d).strip()
                if not d_str or d_str == "{}" or d_str == "[]" or d_str.lower() == "null": return True
                if len(d_str) < 10: return True  # arbitrarily small
                return False
                
            invalid_depth = df["depth_json"].apply(is_invalid_depth)
            report["invalid_depth_rows"] = int(invalid_depth.sum())
            if report["invalid_depth_rows"] > 0:
                report["blockers"].append("FILTERED_DATASET_INVALID_DEPTH")
        else:
            report["blockers"].append("FILTERED_DATASET_MISSING_REQUIRED_COLUMNS")
            
        if has_ts:
            valid_ts = df[ts_col_used].dropna().copy()
            if len(valid_ts) > 0:
                try:
                    ts_num = pd.to_numeric(valid_ts)
                    ts_sorted = ts_num.sort_values()
                    report["timestamp_start"] = str(ts_sorted.iloc[0])
                    report["timestamp_end"] = str(ts_sorted.iloc[-1])
                    
                    # Convert to datetime
                    # Determine unit based on magnitude
                    if ts_sorted.iloc[0] > 1e16:
                        dt = pd.to_datetime(ts_num, unit='ns', utc=True)
                    elif ts_sorted.iloc[0] > 1e12:
                        dt = pd.to_datetime(ts_num, unit='ms', utc=True)
                    else:
                        dt = pd.to_datetime(ts_num, unit='s', utc=True)
                        
                    dt_sorted = dt.sort_values()
                    report["timestamp_start_utc"] = str(dt_sorted.iloc[0])
                    report["timestamp_end_utc"] = str(dt_sorted.iloc[-1])
                    
                    dt_ist = dt.dt.tz_convert('Asia/Kolkata')
                    dt_ist_sorted = dt_ist.sort_values()
                    report["timestamp_start_ist"] = str(dt_ist_sorted.iloc[0])
                    report["timestamp_end_ist"] = str(dt_ist_sorted.iloc[-1])
                    
                    dates_ist = dt_ist.dt.strftime('%Y-%m-%d').unique().tolist()
                    report["trading_dates_ist"] = sorted(dates_ist)
                    
                    if report["expected_date_from_filename"] and report["expected_date_from_filename"] not in dates_ist:
                        report["blockers"].append("FILTERED_DATASET_DATE_MISMATCH")
                        report["date_alignment_ok"] = False
                    else:
                        report["date_alignment_ok"] = True
                        
                    # Calculate session rows (09:15 to 15:30 IST)
                    time_ist = dt_ist.dt.time
                    from datetime import time
                    t_start = time(9, 15)
                    t_end = time(15, 30)
                    
                    in_session = (time_ist >= t_start) & (time_ist <= t_end)
                    report["session_rows"] = int(in_session.sum())
                    report["outside_session_rows"] = int((~in_session).sum())
                    
                    if len(df) > 0:
                        report["session_coverage_ratio"] = report["session_rows"] / len(df)
                        
                    if report["session_coverage_ratio"] < 0.5:
                        report["blockers"].append("FILTERED_DATASET_SESSION_COVERAGE_INVALID")
                        
                except Exception as e:
                    report["blockers"].append(f"FILTERED_DATASET_INVALID_TIMESTAMPS: {e}")
            else:
                report["blockers"].append("FILTERED_DATASET_INVALID_TIMESTAMPS")
                
    except Exception as e:
        report["blockers"].append(f"ERROR: {str(e)}")
        
    if not report["blockers"]:
        report["classification"] = "FILTERED_STRESS_REPLAY_DATASET_VALID"
        
    with open(out_dir / "filtered_stress_replay_dataset_quality_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    md = [
        "# Filtered Stress Replay Dataset Quality Report",
        f"- **Dataset Path:** {report['dataset_path']}",
        f"- **Token Index Path:** {report['token_index_path']}",
        f"- **Classification:** {report['classification']}",
        f"- **Total Rows:** {report['total_rows']}",
        f"- **Unique Tokens:** {report['unique_tokens']}",
        f"- **Unresolved Tokens Present:** {report['unresolved_tokens_present']}",
        f"- **Missing Columns:** {report['missing_required_columns']}",
        f"- **Blockers:** {report['blockers']}",
        f"- **Warnings:** {report['warnings']}",
        "## Date & Time Alignment",
        f"- Expected Date from Filename: {report['expected_date_from_filename']}",
        f"- Actual UTC Start/End: {report['timestamp_start_utc']} -> {report['timestamp_end_utc']}",
        f"- Actual IST Start/End: {report['timestamp_start_ist']} -> {report['timestamp_end_ist']}",
        f"- Actual Trading Dates (IST): {report['trading_dates_ist']}",
        f"- Date Alignment OK: {report['date_alignment_ok']}",
        "## Session Coverage",
        f"- Session Rows (09:15-15:30 IST): {report['session_rows']}",
        f"- Outside Session Rows: {report['outside_session_rows']}",
        f"- Coverage Ratio: {report['session_coverage_ratio']:.3f}",
        "## Validation Metrics",
        f"- Invalid LTP Rows: {report['invalid_ltp_rows']}",
        f"- Invalid Bid/Ask Rows: {report['invalid_bid_ask_rows']}",
        f"- Invalid Spread Rows: {report['invalid_spread_rows']}",
        f"- Invalid Depth Rows: {report['invalid_depth_rows']}",
        "## Spread Summary",
        f"- Min: {report['spread_summary']['min']}",
        f"- Median: {report['spread_summary']['median']}",
        f"- P95: {report['spread_summary']['p95']}",
        f"- Max: {report['spread_summary']['max']}",
        "## Spread-to-LTP Ratio",
        f"- Median: {report['spread_to_ltp_summary']['median']:.4f}",
        f"- P95: {report['spread_to_ltp_summary']['p95']:.4f}",
        f"- P99: {report['spread_to_ltp_summary']['p99']:.4f}",
        f"- Max: {report['spread_to_ltp_summary']['max']:.4f}",
        f"- Rows > 20% LTP: {report['extreme_spread_rows_gt_20pct_ltp']}",
        f"- Rows > 50% LTP: {report['extreme_spread_rows_gt_50pct_ltp']}",
        "## Rows Per Token",
        f"- Min: {report['rows_per_token_summary']['min']}",
        f"- Median: {report['rows_per_token_summary']['median']}",
        f"- Max: {report['rows_per_token_summary']['max']}",
        "## Safety Flags",
        f"- paper_live_allowed: {report['paper_live_allowed']}",
        f"- live_allowed: {report['live_allowed']}",
        f"- broker_order_allowed: {report['broker_order_allowed']}",
        f"- execution_allowed: {report['execution_allowed']}"
    ]
    
    with open(out_dir / "filtered_stress_replay_dataset_quality_report.md", "w") as f:
        f.write("\n".join(md))
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", required=True)
    parser.add_argument("--token-index", required=True)
    args = parser.parse_args()
    validate_dataset(args.ticks, args.token_index)
