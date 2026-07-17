from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_research.historical import HistoricalCampaignConfig, run_historical_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the causal TREND_PULLBACK_v1 historical campaign")
    parser.add_argument("--input", required=True, help="Canonical NIFTY_F1 OHLCV CSV or parquet")
    parser.add_argument("--output-dir", default="agentic_research/edge_results/aeron7_trend_pullback")
    parser.add_argument("--source-repository", default="aeron7/nifty-banknifty-intraday-data")
    parser.add_argument("--source-commit", default="906fc2378b82e50de78f62844a3ecb3f9306a85d")
    parser.add_argument("--minimum-sessions", type=int, default=80)
    args = parser.parse_args()
    config = HistoricalCampaignConfig(minimum_sessions=args.minimum_sessions)
    result = run_historical_campaign(
        args.input,
        Path(args.output_dir),
        source_repository=args.source_repository,
        source_commit=args.source_commit,
        config=config,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
