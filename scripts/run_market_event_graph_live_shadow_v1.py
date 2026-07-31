#!/usr/bin/env python3
"""Run the Market Event Graph Stage A/B read-only observation campaign."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.market_event_graph_live_shadow import CampaignConfig, load_jsonl, run_campaign


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Captured market snapshot metadata JSONL")
    parser.add_argument("--output", required=True, type=Path, help="Campaign artifact directory")
    parser.add_argument("--mode", choices=("LIVE", "REPLAY"), default="REPLAY")
    parser.add_argument("--session-date", default=None)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--universe", type=Path, default=None, help="Optional constituent universe manifest JSON")
    args = parser.parse_args()

    snapshots = load_jsonl(args.input)
    reports = run_campaign(
        snapshots,
        args.output,
        config=CampaignConfig(
            session_date=args.session_date,
            symbol=args.symbol,
            observation_mode=args.mode,
        ),
        universe=_load_json(args.universe),
    )
    print(json.dumps(reports, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
