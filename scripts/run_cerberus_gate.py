#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.code_excellence.cerberus_gate import (
    read_changed_paths_file,
    run_cerberus_gate,
    write_cerberus_gate_report,
)


DEFAULT_OUTPUT = "docs/code_excellence/cerberus/reports/cerberus_gate_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Cerberus static safety regression gate."
    )
    parser.add_argument("--repo", default=".")
    parser.add_argument("--config", default=".gsd-forensics.yaml")
    parser.add_argument("--changed-paths-file", required=True)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed_paths = read_changed_paths_file(args.changed_paths_file)
    report = run_cerberus_gate(
        repo_root=Path(args.repo),
        config_path=Path(args.config),
        changed_paths=changed_paths,
    )
    output_path = write_cerberus_gate_report(report, Path(args.out))
    print(f"[cerberus-gate] report={output_path}")
    print(f"[cerberus-gate] findings={len(report.findings)}")
    print(f"[cerberus-gate] pass_count={report.pass_count}")
    print(f"[cerberus-gate] block_count={report.block_count}")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
