#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from aixion_trade_intelligence.report import write_analysis_bundle
from aixion_trade_intelligence.session import SessionAnalyzer
from aixion_trade_intelligence.storage import iter_events, verify_event_log


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and analyze one Aixion Trade Intelligence session event log."
    )
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    verification = verify_event_log(args.event_log)
    if not verification["valid"]:
        print(json.dumps({"verification": verification}, indent=2))
        return 2

    events = list(iter_events(args.event_log))
    analysis = SessionAnalyzer().analyze(events)
    paths = write_analysis_bundle(analysis, args.output_dir)
    result = {
        "verification": verification,
        "analysis": analysis.to_record(),
        "artifacts": paths,
    }
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if analysis.manifest["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
