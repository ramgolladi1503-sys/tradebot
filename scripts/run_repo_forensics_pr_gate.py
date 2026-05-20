#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.repo_forensics.config_loader import ConfigError
from tools.repo_forensics.pr_gate import DEFAULT_BASELINE_SUMMARY, DEFAULT_PR_GATE_REPORT, run_pr_gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline-aware repo-forensics PR gate.")
    parser.add_argument("--repo", default=".", help="Repository root. Default: current directory.")
    parser.add_argument("--config", default=".gsd-forensics.yaml", help="Forensics config path.")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_SUMMARY, help="Committed baseline summary path.")
    parser.add_argument("--out", default=DEFAULT_PR_GATE_REPORT, help="PR gate report output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    try:
        result = run_pr_gate(
            repo_root,
            args.config,
            baseline_summary_path=args.baseline,
            current_report_path=args.out,
            gate_report_path=args.out,
        )
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"[repo-forensics-pr-gate][ERROR] {exc}")
        return 2

    print(f"[repo-forensics-pr-gate] verdict={result.verdict}")
    print(f"[repo-forensics-pr-gate] report={result.report_path}")
    print(f"[repo-forensics-pr-gate] hard_failures_delta={result.current.counts.hard_failures - result.baseline_counts.hard_failures}")
    print(f"[repo-forensics-pr-gate] unknowns_delta={result.current.counts.unknowns - result.baseline_counts.unknowns}")
    print(f"[repo-forensics-pr-gate] warnings_delta={result.current.counts.warnings - result.baseline_counts.warnings}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
