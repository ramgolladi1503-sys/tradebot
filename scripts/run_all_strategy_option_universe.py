#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.option_e2e_recertification_v4.all_strategy_option_campaign_v1 import (
    build_campaign_universe,
    write_campaign_universe,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the exhaustive strategy/hypothesis universe for CE/PE analytics."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--allow-hard-gaps",
        action="store_true",
        help="Emit evidence but do not fail when unclassified strategy entities remain.",
    )
    args = parser.parse_args()

    universe = build_campaign_universe(args.repo_root)
    hashes = write_campaign_universe(universe, args.output_dir)
    result = {
        "summary": universe.summary,
        "artifact_hashes": hashes,
    }
    print(json.dumps(result, sort_keys=True, indent=2))
    if universe.summary["hard_gap_count"] and not args.allow_hard_gaps:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
