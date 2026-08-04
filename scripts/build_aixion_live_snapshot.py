#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.live_snapshot import build_live_session_snapshot
from aixion_trade_intelligence.session import SessionAnalyzer
from aixion_trade_intelligence.storage import iter_events, verify_event_log


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a fail-closed in-session Aixion monitoring snapshot.")
    parser.add_argument("--event-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verification = verify_event_log(args.event_log)
    events = list(iter_events(args.event_log))
    analysis = SessionAnalyzer().analyze(events)
    snapshot = build_live_session_snapshot(analysis, verification=verification)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot.to_record(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "monitoring_verdict": snapshot.monitoring_verdict,
                "monitoring_valid": snapshot.monitoring_valid,
                "output": args.output.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0 if snapshot.monitoring_valid else 3


if __name__ == "__main__":
    raise SystemExit(main())
