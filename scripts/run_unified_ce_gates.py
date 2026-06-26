#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.code_excellence.unified_gate_runner import (
    load_changed_paths,
    run_unified_ce_gates,
    write_unified_ce_gate_report,
)


DEFAULT_OUTPUT = "docs/code_excellence/reports/unified_ce_gate_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run unified Code Excellence gates.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--config", default=".gsd-forensics.yaml")
    parser.add_argument("--changed-paths-file", required=True)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed_paths = load_changed_paths(args.changed_paths_file)
    report = run_unified_ce_gates(
        repo_root=Path(args.repo),
        config_path=Path(args.config),
        changed_paths=changed_paths,
    )
    output_path = write_unified_ce_gate_report(report, Path(args.out))
    print(f"[unified-ce-gates] report={output_path}")
    print(f"[unified-ce-gates] changed_paths={len(report.changed_paths)}")
    print(f"[unified-ce-gates] total_findings={report.total_findings}")
    print(f"[unified-ce-gates] total_blocks={report.total_blocks}")
    print(f"[unified-ce-gates] exit_code={report.exit_code}")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
