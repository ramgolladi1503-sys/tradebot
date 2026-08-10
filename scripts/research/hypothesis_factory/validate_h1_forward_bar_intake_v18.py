#!/usr/bin/env python3
"""
Validate H1 Forward Bar Intake V18
Validates completed NIFTY 5-minute OHLC CSV/parquet input files without connecting to broker APIs.
"""
import os
import sys
import json
import argparse
import pandas as pd

def validate_input_bars(input_bars_path, output_audit_path, observation_date):
    if not os.path.exists(input_bars_path):
        verdict = {
            "schema_version": 1,
            "observation_date": observation_date,
            "input_bars_path": str(input_bars_path),
            "validation_verdict": "FORWARD_BAR_INTAKE_BLOCKED_NO_INPUT",
            "reason": f"Input bar file does not exist at {input_bars_path}"
        }
        if output_audit_path:
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    try:
        if input_bars_path.endswith('.parquet'):
            df = pd.read_parquet(input_bars_path)
        else:
            df = pd.read_csv(input_bars_path)
    except Exception as e:
        verdict = {
            "schema_version": 1,
            "observation_date": observation_date,
            "input_bars_path": str(input_bars_path),
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_SCHEMA",
            "reason": f"Failed to parse bar file: {str(e)}"
        }
        if output_audit_path:
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    required_cols = ['open', 'high', 'low', 'close']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        verdict = {
            "schema_version": 1,
            "observation_date": observation_date,
            "input_bars_path": str(input_bars_path),
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_SCHEMA",
            "reason": f"Missing required columns: {missing_cols}"
        }
        if output_audit_path:
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    ts_col = 'datetime' if 'datetime' in df.columns else ('timestamp' if 'timestamp' in df.columns else None)
    if not ts_col:
        verdict = {
            "schema_version": 1,
            "observation_date": observation_date,
            "input_bars_path": str(input_bars_path),
            "validation_verdict": "FORWARD_BAR_INTAKE_INVALID_SCHEMA",
            "reason": "Missing timestamp or datetime column"
        }
        if output_audit_path:
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    ts = pd.to_datetime(df[ts_col])
    if ts.dt.tz is None:
        ts_ist = ts.dt.tz_localize('Asia/Kolkata')
    else:
        ts_ist = ts.dt.tz_convert('Asia/Kolkata')

    time_str = ts_ist.dt.strftime('%H:%M')
    in_opening = (time_str >= "09:15") & (time_str <= "11:30")
    bars_opening = int(in_opening.sum())

    if bars_opening == 0:
        verdict = {
            "schema_version": 1,
            "observation_date": observation_date,
            "input_bars_path": str(input_bars_path),
            "validation_verdict": "FORWARD_BAR_INTAKE_BLOCKED_NO_OPENING_BARS",
            "reason": "No bars exist in 09:15-11:30 IST opening window"
        }
        if output_audit_path:
            with open(output_audit_path, "w") as f:
                json.dump(verdict, f, indent=2)
        return verdict

    verdict = {
        "schema_version": 1,
        "observation_date": observation_date,
        "input_bars_path": str(input_bars_path),
        "validation_verdict": "FORWARD_BAR_INTAKE_VALID",
        "bars_total": len(df),
        "bars_in_opening_window": bars_opening,
        "first_timestamp_ist": str(ts_ist.iloc[0]),
        "last_timestamp_ist": str(ts_ist.iloc[-1]),
        "reason": "Input bar file passed all schema and temporal validation checks."
    }

    if output_audit_path:
        os.makedirs(os.path.dirname(output_audit_path), exist_ok=True)
        with open(output_audit_path, "w") as f:
            json.dump(verdict, f, indent=2)

    return verdict

def main():
    parser = argparse.ArgumentParser(description="Validate H1 Forward Bar Intake V18")
    parser.add_argument("--input-bars", required=True)
    parser.add_argument("--output-audit", required=True)
    parser.add_argument("--observation-date", default="2026-08-10")
    args = parser.parse_args()

    v = validate_input_bars(args.input_bars, args.output_audit, args.observation_date)
    print(f"BAR INTAKE VALIDATION RESULT: {v['validation_verdict']}")

if __name__ == "__main__":
    main()
