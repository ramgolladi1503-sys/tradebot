#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.gate_revisit_report import write_gate_revisit_report


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the blocked-gate revisit analytics report.")
    parser.add_argument("--desk", default=None)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--first-blocking-only", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = write_gate_revisit_report(
        desk=args.desk,
        trade_date=args.trade_date,
        db_path=args.db_path,
        output_dir=Path(args.out_dir) if args.out_dir else None,
        limit=args.limit,
        first_blocking_only=int(args.first_blocking_only),
    )
    print(
        f"gate_revisit report: desk={payload['desk']} rows={len(payload['rows'])} "
        f"json={payload['report_path']} markdown={payload['markdown_path']}"
    )
    for row in payload["rows"][:10]:
        print(
            f"{row['gate_name']}: target_rate={row['target_rate']:.2%} "
            f"stop_rate={row['stop_rate']:.2%} timeout_rate={row['timeout_rate']:.2%} "
            f"missed_expectancy={row['missed_expectancy']:.3f} recommendation={row['recommendation']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
