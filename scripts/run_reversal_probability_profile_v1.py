#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from research.reversal_probability_profile_v1.campaign import CampaignConfig, run_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RPP NIFTY reversal-structure V1 research campaign")
    parser.add_argument("--input", required=True, help="1-minute NIFTY OHLC CSV/Parquet")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    args = parser.parse_args()
    cfg = CampaignConfig(round_trip_cost_bps=float(args.cost_bps))
    report = run_campaign(args.input, args.output_dir, cfg)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
