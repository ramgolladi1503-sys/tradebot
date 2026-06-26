from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.runtime_readiness_failure_snapshot import (
    build_runtime_readiness_failure_snapshot,
    save_runtime_readiness_failure_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only report explaining why a PAPER run produced no edge evidence."
    )
    parser.add_argument(
        "--runtime-health",
        default=None,
        help="Optional runtime_health_latest.json path.",
    )
    parser.add_argument(
        "--feed-runtime", default=None, help="Optional feed_runtime_latest.json path."
    )
    parser.add_argument(
        "--engine-status", default=None, help="Optional engine_cycle_status.json path."
    )
    parser.add_argument(
        "--family-outcomes", default=None, help="Optional family_outcomes.jsonl path."
    )
    parser.add_argument(
        "--paper-log", default=None, help="Optional paper_market_*.log path."
    )
    parser.add_argument("--out", default=None, help="Optional output JSON path.")
    args = parser.parse_args()

    report = build_runtime_readiness_failure_snapshot(
        runtime_health_path=args.runtime_health,
        feed_runtime_path=args.feed_runtime,
        engine_status_path=args.engine_status,
        family_outcomes_path=args.family_outcomes,
        paper_log_path=args.paper_log,
    )
    output_path = save_runtime_readiness_failure_snapshot(report, path=args.out)
    print(
        json.dumps(
            {"report_path": str(output_path), **report},
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
