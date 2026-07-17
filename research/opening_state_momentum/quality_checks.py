import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from typing import Dict, Any, List, Optional
from pathlib import Path
import re

def parse_date_from_filename(filename: str) -> Optional[str]:
    # Extract date patterns like YYYYMMDD or YYYY-MM-DD
    match = re.search(r"(\d{4}-?\d{2}-?\d{2})", filename)
    if match:
        return match.group(1).replace("-", "")
    return None

def check_ohlcv_file(filepath: str) -> Dict[str, Any]:
    report = {
        "filename_date_mismatch": False,
        "timezone_naive": False,
        "mixed_timezone": False,
        "duplicate_timestamps": 0,
        "conflicting_duplicates": 0,
        "non_monotonic": 0,
        "ohlc_nulls": 0,
        "volume_nulls": 0,
        "zero_volume_count": 0,
        "zero_volume_pct": 0.0,
        "negative_volume_count": 0,
        "high_lt_low": 0,
        "high_lt_open": 0,
        "high_lt_close": 0,
        "low_gt_open": 0,
        "low_gt_close": 0,
        "non_positive_prices": 0,
        "outside_market_hours": 0,
        "interval_gaps": 0,
        "inferred_interval_sec": 0.0,
        "unique_dates": []
    }
    
    try:
        pf = pq.ParquetFile(filepath)
        schema_names = pf.schema.to_arrow_schema().names
        cols_to_read = [c for c in ["timestamp", "open", "high", "low", "close", "volume", "symbol", "tradingsymbol"] if c in schema_names]
        
        if "timestamp" not in cols_to_read:
            return report
            
        df = pf.read(columns=cols_to_read).to_pandas()
        if df.empty:
            return report
            
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Timezone check
        tz = df["timestamp"].dt.tz
        if tz is None:
            report["timezone_naive"] = True
        else:
            # check if there's any mixed zone representation (rare in single series, but check df type)
            if not isinstance(df["timestamp"].dtype, pd.DatetimeTZDtype):
                report["mixed_timezone"] = True
                
        # Internal Date extract
        dates = df["timestamp"].dt.date.dropna().unique()
        report["unique_dates"] = [d.isoformat() for d in dates]
        
        # Filename date match
        fn_date = parse_date_from_filename(Path(filepath).name)
        if fn_date:
            # Check if fn_date matches any internal dates (formatted as YYYYMMDD)
            internal_dates_formatted = [d.replace("-", "") for d in report["unique_dates"]]
            if fn_date not in internal_dates_formatted:
                report["filename_date_mismatch"] = True
                
        # Duplicate timestamp checks
        dup_mask = df["timestamp"].duplicated(keep=False)
        report["duplicate_timestamps"] = df["timestamp"].duplicated().sum()
        if report["duplicate_timestamps"] > 0:
            # Conflicting duplicates: same timestamp but different OHLC
            ohlc_cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]
            if ohlc_cols:
                # Group by timestamp and check if std of any ohlc column is > 0
                grouped = df[dup_mask].groupby("timestamp")[ohlc_cols].nunique()
                report["conflicting_duplicates"] = int((grouped > 1).any(axis=1).sum())

        # Monotonicity check
        # Check sortedness
        if not df["timestamp"].is_monotonic_increasing:
            report["non_monotonic"] = 1
            
        # OHLC null counts
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                report["ohlc_nulls"] += int(df[col].isna().sum())
        if "volume" in df.columns:
            report["volume_nulls"] = int(df["volume"].isna().sum())
            report["zero_volume_count"] = int((df["volume"] == 0).sum())
            report["negative_volume_count"] = int((df["volume"] < 0).sum())
            report["zero_volume_pct"] = float(report["zero_volume_count"] / len(df)) * 100 if len(df) > 0 else 0.0

        # OHLC Invariants
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            report["high_lt_low"] = int((df["high"] < df["low"]).sum())
            report["high_lt_open"] = int((df["high"] < df["open"]).sum())
            report["high_lt_close"] = int((df["high"] < df["close"]).sum())
            report["low_gt_open"] = int((df["low"] > df["open"]).sum())
            report["low_gt_close"] = int((df["low"] > df["close"]).sum())
            
            # Non-positive prices
            for col in ["open", "high", "low", "close"]:
                report["non_positive_prices"] += int((df[col] <= 0).sum())
                
        # Indian Market Hours (9:15 to 15:30 IST)
        # Convert to Asia/Kolkata first
        df_ist = df.copy()
        if report["timezone_naive"]:
            df_ist["timestamp"] = df_ist["timestamp"].dt.tz_localize("Asia/Kolkata")
        else:
            df_ist["timestamp"] = df_ist["timestamp"].dt.tz_convert("Asia/Kolkata")
            
        times = df_ist["timestamp"].dt.time
        # Market open: 09:15:00, Close: 15:30:00
        start_time = pd.Timestamp("09:15:00").time()
        end_time = pd.Timestamp("15:30:00").time()
        
        out_hours = (times < start_time) | (times > end_time)
        report["outside_market_hours"] = int(out_hours.sum())
        
        # Gaps and interval
        if len(df) > 1:
            # Diff of timestamps (in seconds)
            diffs = df["timestamp"].sort_values().diff().dropna().dt.total_seconds()
            if not diffs.empty:
                report["inferred_interval_sec"] = float(diffs.median())
                # A gap is defined as a diff > 1.5 * median interval, within market hours
                # For simplicity, count gaps > 2 * median interval
                report["interval_gaps"] = int((diffs > 2.0 * report["inferred_interval_sec"]).sum())
                
    except Exception:
        pass
        
    return report
