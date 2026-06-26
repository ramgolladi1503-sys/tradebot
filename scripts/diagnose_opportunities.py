#!/usr/bin/env python3
"""Write read-only ranking/opportunity diagnostics.

No broker calls, order calls, ranking mutation, execution gate changes, depth
engine changes, or trade tuning are performed by this script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.opportunity_diagnostics import (
    build_opportunity_diagnostics,
    load_candidate_rows,
    write_opportunity_diagnostics_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose emitted rows vs ranked opportunity view"
    )
    parser.add_argument(
        "--input", default=None, help="Optional JSONL/JSON/CSV candidate export path"
    )
    parser.add_argument(
        "--logs-dir",
        default=None,
        help="Runtime logs directory; defaults to core.paths.logs_dir()",
    )
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument(
        "--tail",
        type=int,
        default=500,
        help="Number of JSONL rows to inspect when using logs",
    )
    parser.add_argument(
        "--print", action="store_true", help="Print report to stdout instead of writing"
    )
    args = parser.parse_args()

    if args.print:
        rows, source = load_candidate_rows(
            input_path=args.input, logs_dir=args.logs_dir, tail=args.tail
        )
        report = build_opportunity_diagnostics(rows, source_path=source)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    out = write_opportunity_diagnostics_report(
        input_path=args.input,
        logs_dir=args.logs_dir,
        output_path=args.output,
        tail=args.tail,
    )
    print(f"Wrote opportunity diagnostics: {Path(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
