#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.code_excellence.remediation_planner import (
    RemediationPlannerError,
    plan_remediation,
    write_remediation_report,
)
from tools.repo_forensics.config_loader import ConfigError


DEFAULT_CONFIG = ".gsd-forensics.yaml"
DEFAULT_OUTPUT = "docs/code_excellence/daedalus/reports/remediation_plan_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a read-only Daedalus remediation plan from CE findings."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to Ariadne clusters or normalized findings JSON.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="Forensics config path. Default: .gsd-forensics.yaml",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUTPUT,
        help=f"Markdown report output path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = plan_remediation(
            source_path=Path(args.input), config_path=Path(args.config)
        )
        output_path = write_remediation_report(report, Path(args.out))
    except (ConfigError, RemediationPlannerError, FileNotFoundError, ValueError) as exc:
        print(f"[daedalus-planner][ERROR] {exc}")
        return 2

    print(f"[daedalus-planner] report={output_path}")
    print(f"[daedalus-planner] total_plans={report.total_plans}")
    print(f"[daedalus-planner] blocked_count={report.blocked_count}")
    print(f"[daedalus-planner] accepted_unknown_count={report.accepted_unknown_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
