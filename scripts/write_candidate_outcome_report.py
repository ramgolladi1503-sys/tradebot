from __future__ import annotations

import argparse
from pathlib import Path

from core.candidate_outcome_report_writer import write_candidate_outcome_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Write an offline candidate outcome report from committed fixtures.")
    parser.add_argument(
        "--fixture-dir",
        default="tests/fixtures/candidate_outcomes",
        help="Directory containing committed candidate outcome fixtures.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/code_excellence/reports/candidate_outcomes",
        help="Directory to write the JSON and Markdown reports.",
    )
    args = parser.parse_args()

    json_path, markdown_path = write_candidate_outcome_reports(Path(args.fixture_dir), Path(args.output_dir))
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
