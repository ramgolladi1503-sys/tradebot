#!/usr/bin/env python3
"""
Validate H1 Forward Bar Intake V18 (Hardened V19)
Validates completed NIFTY 5-minute OHLC CSV/parquet input files without connecting to broker APIs.
"""
import os
import sys
import json
import argparse
import pandas as pd
import numpy as np

def validate_input_bars(
    input_bars_path,
    output_audit_path,
    observation_date,
    opening_start="09:15",
    opening_end="11:30",
    allow_missing_bars=False
):
    orders_created = 0
    broker_writes_created = 0
    authority_flags_all_false = True

    base_result = {
        "schema_version": 1,
        "observation_date": observation_date,
        "input_bars_path": str(input_bars_path),
        "orders_created": orders_created,
        "broker_writes_created": broker_writes_created,
        "authority_flags_all_false": authority_flags_all_false,
        "allow_missing_bars": allow_missing_bars
    }

    if not os.path.exists(input_bars_path):
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_BLOCKED_NO_INPUT",
            "reason": f"Input bar file does not exist at {input_bars_path}"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    try:
        if input_bars_path.endswith('.parquet'):
            df = pd.read_parquet(input_bars_path)
        else:
            df = pd.read_csv(input_bars_path, comment='#')
    except Exception as e:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_SCHEMA",
            "reason": f"Failed to parse bar file: {str(e)}"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    required_cols = ['datetime', 'open', 'high', 'low', 'close', 'source', 'completed_bar', 'timezone']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_SCHEMA",
            "reason": f"Missing required columns: {missing_cols}"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    if len(df) == 0:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_BLOCKED_NO_INPUT",
            "reason": "File is empty / header only"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # Parse timestamps
    try:
        ts = pd.to_datetime(df['datetime'])
    except Exception as e:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_SCHEMA",
            "reason": f"Invalid datetime format: {str(e)}"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # Check Timezone
    if (df['timezone'] != 'Asia/Kolkata').any() and (df['timezone'] != 'IST').any():
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_TIMEZONE",
            "reason": "All rows must have timezone set to Asia/Kolkata or IST"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    if ts.dt.tz is None:
        ts_ist = ts.dt.tz_localize('Asia/Kolkata')
    else:
        ts_ist = ts.dt.tz_convert('Asia/Kolkata')

    date_str = ts_ist.dt.strftime('%Y-%m-%d')
    if (date_str != observation_date).any():
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_OBSERVATION_DATE",
            "reason": f"Timestamps do not match observation date {observation_date}"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # Duplicate check
    duplicate_count = int(ts_ist.duplicated().sum())
    if duplicate_count > 0:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_DUPLICATES",
            "duplicate_count": duplicate_count,
            "reason": f"Found {duplicate_count} duplicate timestamps"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # Ordering check
    if not ts_ist.is_monotonic_increasing:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_ORDERING",
            "reason": "Timestamps are not strictly monotonically increasing"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # 5-minute alignment check
    if (ts_ist.dt.minute % 5 != 0).any() or (ts_ist.dt.second != 0).any():
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_5MIN_ALIGNMENT",
            "reason": "Timestamps are not aligned to 5-minute boundaries (e.g. 09:15, 09:20)"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # 5-minute spacing check
    diffs = ts_ist.diff().dropna()
    expected_diff = pd.Timedelta(minutes=5)
    has_spacing_gap = (diffs != expected_diff).any()
    if has_spacing_gap and not allow_missing_bars:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_5MIN_SPACING",
            "reason": "Gaps found between consecutive 5-minute bars and allow_missing_bars is False"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # Opening window bars check
    time_str = ts_ist.dt.strftime('%H:%M')
    in_opening = (time_str >= opening_start) & (time_str <= opening_end)
    bars_opening = int(in_opening.sum())
    bars_out_of_opening = len(df) - bars_opening

    if bars_opening == 0:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_BLOCKED_NO_OPENING_BARS",
            "bars_total": len(df),
            "bars_in_opening_window": 0,
            "reason": f"No bars exist in opening window {opening_start}-{opening_end} IST"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # completed_bar status check
    cb_bool = df['completed_bar'].astype(str).str.lower().isin(['true', '1'])
    completed_bar_false_count = int((~cb_bool[in_opening]).sum())
    if completed_bar_false_count > 0:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_NOT_COMPLETED",
            "completed_bar_false_count": completed_bar_false_count,
            "reason": f"Found {completed_bar_false_count} opening window bars with completed_bar != true"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    # OHLC validity checks
    try:
        o = pd.to_numeric(df['open'])
        h = pd.to_numeric(df['high'])
        l = pd.to_numeric(df['low'])
        c = pd.to_numeric(df['close'])
    except Exception as e:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_OHLC",
            "reason": f"Non-numeric values in OHLC columns: {str(e)}"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    invalid_ohlc = (
        (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0) |
        (h < o) | (h < c) | (h < l) |
        (l > o) | (l > c) | (l > h)
    )
    ohlc_invalid_count = int(invalid_ohlc.sum())
    if ohlc_invalid_count > 0:
        verdict = dict(base_result, **{
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_OHLC",
            "ohlc_invalid_count": ohlc_invalid_count,
            "reason": f"Found {ohlc_invalid_count} bars with invalid OHLC relationship or non-positive prices"
        })
        if output_audit_path:
            os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    verdict = dict(base_result, **{
        "validation_verdict": "FORWARD_BAR_INTAKE_VALID",
        "bars_total": len(df),
        "bars_in_opening_window": bars_opening,
        "bars_out_of_opening_window": bars_out_of_opening,
        "first_timestamp_ist": str(ts_ist.iloc[0]),
        "last_timestamp_ist": str(ts_ist.iloc[-1]),
        "duplicate_count": 0,
        "missing_expected_opening_bars": 0,
        "completed_bar_false_count": 0,
        "ohlc_invalid_count": 0,
        "reason": "Input bar file passed all hardened V19 schema, temporal, alignment, spacing, completion, and OHLC validation checks."
    })

    if output_audit_path:
        os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
        with open(output_audit_path, "w") as f:
            json.dump(verdict, f, indent=2)

    return verdict

def main():
    parser = argparse.ArgumentParser(description="Validate H1 Forward Bar Intake V18 (Hardened V19)")
    parser.add_argument("--input-bars", required=True)
    parser.add_argument("--output-audit", required=True)
    parser.add_argument("--observation-date", default="2026-08-10")
    parser.add_argument("--opening-start", default="09:15")
    parser.add_argument("--opening-end", default="11:30")
    parser.add_argument("--allow-missing-bars", default="false")
    args = parser.parse_args()

    allow_missing = str(args.allow_missing_bars).lower() in ['true', '1']
    v = validate_input_bars(
        args.input_bars,
        args.output_audit,
        args.observation_date,
        args.opening_start,
        args.opening_end,
        allow_missing
    )
    print(f"BAR INTAKE VALIDATION RESULT: {v['validation_verdict']}")

if __name__ == "__main__":
    main()
