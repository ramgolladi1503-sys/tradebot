#!/usr/bin/env python3
"""
Convert raw tick JSONL files to compressed Parquet format.
"""

import argparse
import json
import logging
from pathlib import Path
import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("parquet_converter")


def convert_jsonl_to_parquet(input_file: Path, delete_original: bool = False):
    if not input_file.exists():
        logger.error(f"Input file does not exist: {input_file}")
        return

    output_file = input_file.with_suffix(".parquet")

    logger.info(
        f"Reading JSONL from {input_file} (this may take a moment for large files)..."
    )

    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse line {i + 1}: {line[:100]}")

    if not records:
        logger.warning(f"No valid records found in {input_file}.")
        return

    logger.info(f"Loaded {len(records)} records. Converting to DataFrame...")
    df = pd.DataFrame(records)

    # Optionally cast columns to optimize further
    if "ts" in df.columns:
        df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    if "ltp" in df.columns:
        df["ltp"] = pd.to_numeric(df["ltp"], errors="coerce")
    if "bid" in df.columns:
        df["bid"] = pd.to_numeric(df["bid"], errors="coerce")
    if "ask" in df.columns:
        df["ask"] = pd.to_numeric(df["ask"], errors="coerce")
    if "vol" in df.columns:
        df["vol"] = pd.to_numeric(df["vol"], errors="coerce")

    logger.info(f"Writing to Parquet file: {output_file}")

    # Write to parquet
    df.to_parquet(output_file, engine="pyarrow", compression="snappy", index=False)

    in_size_mb = input_file.stat().st_size / (1024 * 1024)
    out_size_mb = output_file.stat().st_size / (1024 * 1024)

    logger.info(f"Conversion complete!")
    logger.info(f"Original JSONL size: {in_size_mb:.2f} MB")
    logger.info(f"New Parquet size:    {out_size_mb:.2f} MB")

    if delete_original:
        logger.info(f"Deleting original file: {input_file}")
        input_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="Convert tick JSONL to Parquet")
    parser.add_argument("input_file", help="Path to the .jsonl file")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the original .jsonl file after successful conversion",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    convert_jsonl_to_parquet(input_path, delete_original=args.delete)


if __name__ == "__main__":
    main()
