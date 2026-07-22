#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from research.upstox_depth_shadow_capture_v2.universe import (
    build_shadow_universe,
    write_universe_atomic,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic Upstox depth-shadow instrument universe from a local BOD master."
    )
    parser.add_argument(
        "--instrument-master",
        type=Path,
        default=Path("runtime/upstox_instruments/complete.json"),
    )
    parser.add_argument(
        "--as-of-date",
        default=date.today().isoformat(),
        help="Session date in YYYY-MM-DD",
    )
    parser.add_argument("--future-expiry-count", type=int, default=2)
    parser.add_argument("--maximum-instruments", type=int, default=2000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    as_of = datetime.strptime(args.as_of_date, "%Y-%m-%d").date()
    payload = json.loads(args.instrument_master.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = list(payload.values())
    if not isinstance(payload, list):
        raise ValueError("instrument master must contain a list or mapping of instruments")

    universe = build_shadow_universe(
        payload,
        as_of_date=as_of,
        future_expiry_count=args.future_expiry_count,
        maximum_instruments=args.maximum_instruments,
    )
    destination = args.output or Path(
        f".runtime/research/upstox_depth_shadow_v2/universes/universe_{as_of.strftime('%Y%m%d')}.json"
    )
    write_universe_atomic(destination, universe)
    print(json.dumps({
        "classification": universe["classification"],
        "instrument_count": universe["instrument_count"],
        "role_counts": universe["role_counts"],
        "output": str(destination),
        "execution_allowed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
