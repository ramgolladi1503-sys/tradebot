from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.edge_baseline_audit import build_edge_baseline_report, save_edge_baseline_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only EDGE-01 baseline audit from the paper outcome journal."
    )
    parser.add_argument(
        "--records-path",
        default=None,
        help="Optional JSONL outcome journal path. Defaults to runtime analytics family_outcomes.jsonl.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output JSON path. Defaults to runtime reports edge_baseline_audit.json.",
    )
    parser.add_argument(
        "--strategy-family",
        default=None,
        help="Optional single-family validation filter, for example ORB or VWAP trend.",
    )
    args = parser.parse_args()

    report = build_edge_baseline_report(
        records_path=args.records_path,
        strategy_family_filter=args.strategy_family,
    )
    output_path = save_edge_baseline_report(report, path=args.out)
    print(json.dumps({"report_path": str(output_path), **report}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
