#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.repo_forensics.baseline import (
    DEFAULT_BASELINE_AGENT_EVIDENCE,
    DEFAULT_BASELINE_REPORT,
    DEFAULT_PR_SUMMARY,
    generate_baseline_audit,
)
from tools.repo_forensics.config_loader import ConfigError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TradeBot repo-forensics baseline evidence.")
    parser.add_argument("--repo", default=".", help="Repository root. Default: current directory.")
    parser.add_argument("--config", default=".gsd-forensics.yaml", help="Forensics config path.")
    parser.add_argument("--report", default=DEFAULT_BASELINE_REPORT, help="Baseline report output path.")
    parser.add_argument("--agent-evidence", default=DEFAULT_BASELINE_AGENT_EVIDENCE, help="3-agent evidence output path.")
    parser.add_argument("--pr-summary", default=DEFAULT_PR_SUMMARY, help="PR summary output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    try:
        result = generate_baseline_audit(
            repo_root,
            args.config,
            report_path=args.report,
            agent_evidence_path=args.agent_evidence,
            pr_summary_path=args.pr_summary,
        )
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"[repo-forensics-baseline][ERROR] {exc}")
        return 2

    print(f"[repo-forensics-baseline] verdict={result.run_result.verdict}")
    print(f"[repo-forensics-baseline] report={result.report_path}")
    print(f"[repo-forensics-baseline] agent_evidence={result.agent_evidence_path}")
    print(f"[repo-forensics-baseline] pr_summary={result.pr_summary_path}")
    print(f"[repo-forensics-baseline] hard_failures={result.run_result.counts.hard_failures}")
    print(f"[repo-forensics-baseline] unknowns={result.run_result.counts.unknowns}")
    print(f"[repo-forensics-baseline] warnings={result.run_result.counts.warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
