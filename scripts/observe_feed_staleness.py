#!/usr/bin/env python3
"""Generate read-only feed/staleness observability evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.feed_staleness_observability import build_feed_staleness_report, write_feed_staleness_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate feed/staleness observability evidence")
    parser.add_argument("--logs-dir", default=".runtime/logs", help="Runtime logs directory")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--print", action="store_true", help="Print report JSON to stdout")
    args = parser.parse_args()

    if args.print:
        report = build_feed_staleness_report(args.logs_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    out = write_feed_staleness_report(args.logs_dir, args.output)
    print(f"Wrote feed/staleness observability report: {Path(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
