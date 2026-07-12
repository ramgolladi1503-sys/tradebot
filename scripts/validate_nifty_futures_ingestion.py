#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from core.nifty_futures_ingestion_validation import validate_candle_artifact, write_public_metadata


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local NIFTY futures candle artifact and emit public-safe metadata.")
    parser.add_argument("--artifact", required=True, help="Local candle artifact path (.csv, .json, .jsonl, .parquet).")
    parser.add_argument("--output", required=True, help="Output metadata JSON path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    report = validate_candle_artifact(Path(args.artifact), output_path=Path(args.output))
    write_public_metadata(report, Path(args.output))
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str))
    return 0 if report.validation_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
