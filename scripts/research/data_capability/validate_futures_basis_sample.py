#!/usr/bin/env python3
"""
Sample Validator Stub for Futures Basis Data (TradeBot / MROS)
Read-only validation script that verifies vendor-supplied sample files against futures_basis_schema_contract.json.
"""
import argparse
import json
import sys
import pandas as pd
from pathlib import Path

def validate_sample(file_path: str):
    p = Path(file_path)
    if not p.exists():
        return {
            "status": "BLOCKED_FILE_NOT_FOUND",
            "file_path": file_path,
            "validation_passed": False
        }

    try:
        df = pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p)
    except Exception as e:
        return {
            "status": "BLOCKED_CORRUPT_FILE",
            "error": str(e),
            "validation_passed": False
        }

    required_fields = ["timestamp", "spot_close", "futures_symbol", "futures_close", "volume"]
    missing = [f for f in required_fields if f not in df.columns]

    if missing:
        return {
            "status": "FAILED_SCHEMA_VALIDATION",
            "missing_fields": missing,
            "validation_passed": False
        }

    return {
        "status": "SAMPLE_VALIDATED_SUCCESSFULLY",
        "rows": len(df),
        "validation_passed": True
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-file", type=str, required=True)
    args = parser.parse_args()

    res = validate_sample(args.sample_file)
    print(json.dumps(res, indent=2))
    if not res["validation_passed"]:
        sys.exit(1)
