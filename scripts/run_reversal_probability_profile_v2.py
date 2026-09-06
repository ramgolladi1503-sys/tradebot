#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import replace

from research.reversal_probability_profile_v2 import RPPV2Config, run_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description="Run causal RPP NIFTY zone-interaction V2 research")
    parser.add_argument("--input", required=True, help="NIFTY OHLC or long-form index/constituent CSV/Parquet")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    args = parser.parse_args()

    cfg = replace(RPPV2Config(), round_trip_cost_bps=args.cost_bps)
    report = run_experiment(args.input, args.output_dir, cfg)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    # A negative research verdict is a valid experiment result, not a process error.
    # Only malformed/unreadable input should make Python exit non-zero via exception.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
