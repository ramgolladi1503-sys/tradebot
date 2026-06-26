from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.expectancy.edge_readiness_report import write_edge_readiness_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write the edge readiness report from explicit inputs."
    )
    parser.add_argument(
        "--expectancy-path",
        required=True,
        help="Path to strategy_regime_expectancy_latest.json",
    )
    parser.add_argument(
        "--top-opportunities-path",
        required=True,
        help="Path to top_opportunities_latest.json",
    )
    parser.add_argument(
        "--shadow-validation-path",
        required=True,
        help="Path to shadow_validation_latest.json",
    )
    parser.add_argument(
        "--topn-replay-quality-path",
        default=None,
        help="Optional explicit path to topn_replay_quality_latest.json.",
    )
    parser.add_argument(
        "--candidate-journal-summary",
        default=None,
        help="Optional explicit path to a candidate journal summary JSON/JSONL file.",
    )
    parser.add_argument(
        "--fallback-exclusion-summary",
        default=None,
        help="Optional explicit path to a fallback exclusion summary JSON/JSONL file.",
    )
    parser.add_argument(
        "--out-dir",
        default="reports",
        help="Directory for reports/edge_readiness_latest.*",
    )
    parser.add_argument(
        "--mirror-runtime",
        action="store_true",
        help="Also write runtime mirror reports under .runtime/reports/.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    json_path, md_path, report = write_edge_readiness_report(
        expectancy_path=Path(args.expectancy_path),
        top_opportunities_path=Path(args.top_opportunities_path),
        shadow_validation_path=Path(args.shadow_validation_path),
        topn_replay_quality_path=Path(args.topn_replay_quality_path)
        if args.topn_replay_quality_path
        else None,
        candidate_journal_summary=Path(args.candidate_journal_summary)
        if args.candidate_journal_summary
        else None,
        fallback_exclusion_summary=Path(args.fallback_exclusion_summary)
        if args.fallback_exclusion_summary
        else None,
        output_dir=Path(args.out_dir),
        mirror_runtime=bool(args.mirror_runtime),
    )
    sys.stdout.write(f"{json_path}\n{md_path}\n{report.recommendation}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
