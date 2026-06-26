#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.agents.trade_quality_truth_audit import build_trade_quality_truth_audit


def _truthy(value: str | bool | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Trade Quality Truth Audit.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--runtime-dir", default=".runtime")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument(
        "--out-dir", default=str(Path(".runtime") / "trade_quality_audit")
    )
    parser.add_argument(
        "--format", choices=("json", "markdown", "both"), default="both"
    )
    parser.add_argument("--copy-latest", default="false")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_trade_quality_truth_audit(
        repo_root=Path(args.repo_root),
        runtime_dir=Path(args.runtime_dir),
        logs_dir=Path(args.logs_dir),
        out_dir=Path(args.out_dir),
        format=args.format,
        copy_latest=_truthy(args.copy_latest),
    )
    report_dict = report.to_dict()
    print(f"trade_quality_truth_audit summary: {report_dict['summary']}")
    print(f"verdict={report_dict['verdict']}")
    print(f"next_pr={report_dict['next_pr_recommendation']['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
