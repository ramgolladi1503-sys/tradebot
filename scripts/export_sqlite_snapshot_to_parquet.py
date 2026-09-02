#!/usr/bin/env python3
"""Canonical off-hours/live-safe SQLite snapshot Parquet export hook."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.sqlite_snapshot_parquet_exporter import export_once, run_export_loop


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=10.0)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--status-path", type=Path)
    args = parser.parse_args()
    if args.interval_seconds > 0:
        run_export_loop(
            args.production_db,
            args.output_dir,
            interval_seconds=args.interval_seconds,
            deadline_seconds=args.deadline_seconds,
            status_path=args.status_path,
        )
        return 0
    result = export_once(args.production_db, args.output_dir, deadline_seconds=args.deadline_seconds)
    print(result.as_dict())
    return 0 if result.status == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
