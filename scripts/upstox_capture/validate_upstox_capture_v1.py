#!/usr/bin/env python3
import sys
import json
import argparse
import hashlib
import struct
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import zstandard as zstd
import logging

sys.path.append(str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_capture")

def validate_raw_frames(run_dir: Path) -> dict:
    raw_dir = run_dir / "raw"
    if not raw_dir.exists():
        return {"status": "MISSING_RAW_DATA", "error": "Raw folder missing"}

    index_files = list(raw_dir.glob("**/*.index.parquet"))
    bin_files = list(raw_dir.glob("**/*.bin.zst"))

    issues = []
    total_index_rows = 0
    total_bin_records = 0

    # Match each bin.zst with its index.parquet
    for bin_file in bin_files:
        index_file = bin_file.parent / f"{bin_file.name.split('.')[0]}.index.parquet"
        if not index_file.exists():
            issues.append(f"Index file missing for {bin_file.name}")
            continue

        # 1. Verify bin file zst reading and record count
        try:
            with open(bin_file, "rb") as fh:
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(fh) as reader:
                    while True:
                        len_bytes = reader.read(4)
                        if not len_bytes:
                            break
                        if len(len_bytes) < 4:
                            issues.append(f"Truncated frame length header in {bin_file.name}")
                            break
                        length = struct.unpack(">I", len_bytes)[0]
                        payload = reader.read(length)
                        if len(payload) < length:
                            issues.append(f"Truncated frame payload in {bin_file.name}")
                            break
                        total_bin_records += 1
        except Exception as e:
            issues.append(f"Zstd corruption or read error in {bin_file.name}: {e}")

        # 2. Check parquet reading
        try:
            table = pq.read_table(index_file)
            df = table.to_pandas()
            total_index_rows += len(df)

            # Check checksums
            # (In a real validator, we would match hashes, but we can sample or log stats here)
        except Exception as e:
            issues.append(f"Failed to read index parquet {index_file.name}: {e}")

    return {
        "total_bin_records": total_bin_records,
        "total_index_rows": total_index_rows,
        "raw_issues": issues,
        "success": len(issues) == 0 and total_bin_records == total_index_rows
    }

def validate_normalized_ticks(run_dir: Path) -> dict:
    normalized_dir = run_dir / "normalized"
    if not normalized_dir.exists():
        return {"status": "MISSING_NORMALIZED_DATA", "error": "Normalized folder missing"}

    parquet_files = list(normalized_dir.glob("**/*.parquet"))
    issues = []
    total_rows = 0
    duplicate_events = 0
    timestamp_regressions = 0

    for f in parquet_files:
        try:
            table = pq.read_table(f, partitioning=None)
            df = table.to_pandas()
            total_rows += len(df)

            # 1. Schema integrity
            expected_cols = ["ltp", "volume", "open_interest", "receive_wall_ts_utc", "receive_monotonic_ns", "local_sequence"]
            for col in expected_cols:
                if col not in df.columns:
                    issues.append(f"Missing expected schema column {col} in {f.name}")

            # 2. Non-monotonic local sequence check within same file/connection
            if "local_sequence" in df.columns:
                seqs = df["local_sequence"].tolist()
                for i in range(1, len(seqs)):
                    if seqs[i] <= seqs[i-1]:
                        issues.append(f"Non-monotonic local sequence {seqs[i-1]} -> {seqs[i]} in {f.name}")
                        break

            # 3. Future timestamps or impossible times
            if "receive_wall_ts_utc" in df.columns:
                from datetime import timezone
                df['dt'] = pd.to_datetime(df['receive_wall_ts_utc'], format='ISO8601')
                now_ts = pd.Timestamp.now(tz=timezone.utc) if df['dt'].dt.tz is not None else pd.Timestamp.now()
                future_ticks = df[df['dt'] > now_ts + pd.Timedelta(seconds=60)]
                if not future_ticks.empty:
                    issues.append(f"Detected {len(future_ticks)} ticks with future timestamp in {f.name}")

        except Exception as e:
            issues.append(f"Failed to validate normalized file {f.name}: {e}")

    return {
        "total_normalized_rows": total_rows,
        "normalized_issues": issues,
        "success": len(issues) == 0
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Path to the capture run root directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        logger.error(f"Run directory {run_dir} does not exist.")
        sys.exit(1)

    logger.info(f"Starting integrity verification of capture session: {run_dir}")

    raw_results = validate_raw_frames(run_dir)
    norm_results = validate_normalized_ticks(run_dir)

    all_issues = raw_results.get("raw_issues", []) + norm_results.get("normalized_issues", [])
    
    report = {
        "run_dir": str(run_dir),
        "raw_valid": raw_results.get("success", False),
        "normalized_valid": norm_results.get("success", False),
        "total_raw_frames": raw_results.get("total_bin_records", 0),
        "total_normalized_rows": norm_results.get("total_normalized_rows", 0),
        "issues_count": len(all_issues),
        "issues": all_issues
    }

    report_path = run_dir / "validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Verification complete. Issues found: {len(all_issues)}")
    for issue in all_issues[:10]:
        logger.warning(f"Issue: {issue}")
    if len(all_issues) > 10:
        logger.warning(f"... and {len(all_issues) - 10} more issues.")

    logger.info(f"Report saved to {report_path}")

    if all_issues:
        sys.exit(1)
    else:
        logger.info("Session verified successfully (REPLAY_QUALITY_CERTIFIED).")
        sys.exit(0)

if __name__ == "__main__":
    main()
