#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.evidence_replay_report import (
    EvidenceReplayOptions,
    generate_evidence_replay_report,
    report_to_markdown,
)


def _parse_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Tradebot live diagnostic evidence without broker calls."
    )
    parser.add_argument(
        "evidence_source",
        help="Evidence directory or .tar.gz bundle, for example runtime/evidence/live_diag_20260522_evidence.tar.gz",
    )
    parser.add_argument(
        "--today",
        help="Trading date used for expired-contract detection, YYYY-MM-DD. Defaults to date inferred from source name or local date.",
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
    args = parser.parse_args()

    options = EvidenceReplayOptions(
        today=_parse_date(args.today),
        max_jsonl_lines_per_file=max(1, int(args.max_jsonl_lines_per_file)),
        quote_age_mismatch_tolerance_sec=max(
            0.0, float(args.quote_age_mismatch_tolerance_sec)
        ),
    )
    report = generate_evidence_replay_report(args.evidence_source, options=options)

    if args.format == "json":
        rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str)
    else:
        rendered = report_to_markdown(report)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
