#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.runtime_evidence_capture_guard import (
    RuntimeEvidenceCaptureOptions,
    generate_runtime_evidence_capture_guard_report,
    runtime_evidence_capture_guard_to_markdown,
)


def _parse_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate that a Tradebot live diagnostic evidence pack can produce deterministic diagnosis sections."
    )
    parser.add_argument(
        "evidence_source",
        help="Evidence directory or .tar.gz bundle, for example runtime/evidence/live_diag_20260522_evidence.tar.gz",
    )
    parser.add_argument(
        "--today",
        help="Trading date used for expired-contract detection, YYYY-MM-DD. Defaults to the replay analyzer behavior.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        help="Optional output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--max-jsonl-lines-per-file",
        type=int,
        default=5000,
        help="Maximum JSONL tail lines to inspect per file.",
    )
    parser.add_argument(
        "--quote-age-mismatch-tolerance-sec",
        type=float,
        default=5.0,
        help="Allowed difference between reported quote age and timestamp-derived age.",
    )
    parser.add_argument(
        "--score-flattening-tolerance",
        type=float,
        default=0.000001,
        help="Allowed difference between raw and final scores before reporting score flattening.",
    )
    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="Return exit code 2 when any required capture section is missing.",
    )
    args = parser.parse_args()

    options = RuntimeEvidenceCaptureOptions(
        today=_parse_date(args.today),
        quote_age_mismatch_tolerance_sec=max(
            0.0, float(args.quote_age_mismatch_tolerance_sec)
        ),
        max_jsonl_lines_per_file=max(1, int(args.max_jsonl_lines_per_file)),
        score_flattening_tolerance=max(0.0, float(args.score_flattening_tolerance)),
    )
    report = generate_runtime_evidence_capture_guard_report(
        args.evidence_source, options=options
    )

    if args.format == "json":
        rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str)
    else:
        rendered = runtime_evidence_capture_guard_to_markdown(report)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    if args.fail_on_incomplete and report.verdict != "CAPTURE_GUARD_OK":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
