#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.incident_bundle import (
    DEFAULT_WINDOW_MINUTES,
    default_incident_output_dir,
    generate_incident_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a read-only incident bundle for a live trade/advisory issue."
    )
    parser.add_argument(
        "--symbol", required=True, help="Underlying symbol to inspect, e.g. NIFTY"
    )
    parser.add_argument(
        "--trade-id",
        default=None,
        help="Optional trade/advisory id to narrow the bundle.",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_WINDOW_MINUTES,
        help="Log/snippet lookback window in minutes.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(default_incident_output_dir()),
        help="Output directory for timestamped incident bundle folders.",
    )
    args = parser.parse_args()

    path = generate_incident_bundle(
        symbol=args.symbol,
        trade_id=args.trade_id,
        minutes=args.minutes,
        output_dir=args.output_dir,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
