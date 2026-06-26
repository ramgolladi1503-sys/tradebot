#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.expectancy.shadow_validation import write_shadow_market_validation_report


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the shadow market validation runner."
    )
    parser.add_argument("--candidate-journal", required=True)
    parser.add_argument("--candidate-outcomes", required=True)
    parser.add_argument("--top-opportunities", required=True)
    parser.add_argument("--observations")
    parser.add_argument(
        "--out-dir", default=str(Path(".runtime") / "shadow_validation")
    )
    parser.add_argument("--session-date")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    json_path, md_path, session_path, report = write_shadow_market_validation_report(
        candidate_journal=Path(args.candidate_journal),
        candidate_outcomes=Path(args.candidate_outcomes),
        top_opportunities=Path(args.top_opportunities),
        observations=Path(args.observations) if args.observations else None,
        output_dir=Path(args.out_dir),
        session_date=args.session_date,
    )
    payload = report.to_payload()
    print(
        f"shadow_market_validation summary: recommendation={payload['recommendation']} avg_cost_adjusted_r={payload['avg_cost_adjusted_r']}"
    )
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    print(f"session={session_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
