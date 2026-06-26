#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.code_excellence.minerva_gate import (
    read_changed_paths_file,
    run_minerva_gate,
    write_minerva_gate_report,
)


DEFAULT_OUTPUT = "docs/code_excellence/minerva/reports/minerva_gate_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Minerva test reality gate.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--config", default=".gsd-forensics.yaml")
    parser.add_argument("--changed-paths-file")
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed_paths = (
        read_changed_paths_file(args.changed_paths_file)
        if args.changed_paths_file
        else None
    )
    report = run_minerva_gate(
        repo_root=Path(args.repo),
        config_path=Path(args.config),
        changed_paths=changed_paths,
    )
    output_path = write_minerva_gate_report(report, Path(args.out))
    print(f"[minerva-gate] report={output_path}")
    print(f"[minerva-gate] findings={len(report.findings)}")
    print(f"[minerva-gate] pass_count={report.pass_count}")
    print(f"[minerva-gate] block_count={report.block_count}")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
