#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.expectancy.topn_replay_quality import write_topn_replay_quality_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Top-N replay quality report from explicit inputs."
    )
    parser.add_argument(
        "--candidate-outcomes",
        required=True,
        help="Path to candidate outcomes JSON/JSONL.",
    )
    parser.add_argument(
        "--top-opportunities", required=True, help="Path to top opportunities JSON."
    )
    parser.add_argument(
        "--candidate-journal",
        default=None,
        help="Optional explicit candidate journal JSON/JSONL source used for diagnostics.",
    )
    parser.add_argument(
        "--observations",
        default=None,
        help="Optional explicit observation source JSON/JSONL used for diagnostics.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(".runtime") / "replay_quality"),
        help="Directory for Top-N replay quality outputs.",
    )
    parser.add_argument(
        "--mirror-runtime",
        action="store_true",
        help="Also write a runtime mirror under .runtime/replay_quality/.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    session_rows = None
    if args.candidate_journal:
        session_rows = Path(args.candidate_journal)
    elif args.observations:
        session_rows = Path(args.observations)
    json_path, md_path, report = write_topn_replay_quality_report(
        candidate_outcomes=Path(args.candidate_outcomes),
        top_opportunities=Path(args.top_opportunities),
        session_rows=session_rows,
        output_dir=Path(args.out_dir),
        mirror_runtime=bool(args.mirror_runtime),
    )
    print(f"topn_replay_quality verdict={report.verdict} reason={report.reason}")
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
