#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.candidate_executability_evidence import write_candidate_executability_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a read-only candidate executability evidence pack from a log file.")
    parser.add_argument("--log-file", required=True, help="Path to a log file or evidence transcript to parse.")
    parser.add_argument(
        "--output-dir",
        default=".runtime/reports/candidate_executability",
        help="Directory where the JSON and Markdown summaries will be written.",
    )
    parser.add_argument("--source-name", default=None, help="Optional source label to embed in the report.")
    parser.add_argument("--session-id", default=None, help="Optional session identifier to embed in the report.")
    args = parser.parse_args()

    json_path, markdown_path, _report = write_candidate_executability_evidence(
        log_file=Path(args.log_file),
        output_dir=Path(args.output_dir),
        source_name=args.source_name,
        session_id=args.session_id,
    )
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
