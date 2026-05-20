#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.code_excellence.pr_evidence_pack import build_pr_evidence_pack_from_paths, write_pr_evidence_pack


DEFAULT_OUTPUT = "docs/code_excellence/reports/pr_evidence_pack_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a PR-ready Code Excellence evidence pack.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--config", default=".gsd-forensics.yaml")
    parser.add_argument("--changed-paths-file", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--test-command", action="append", required=True)
    parser.add_argument("--next", default="Review CI and merge only if green.")
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = build_pr_evidence_pack_from_paths(
        repo_root=Path(args.repo),
        config_path=Path(args.config),
        changed_paths_file=Path(args.changed_paths_file),
        pr_label=args.label,
        test_commands=args.test_command,
        next_step=args.next,
    )
    output_path = write_pr_evidence_pack(pack, Path(args.out))
    print(f"[pr-evidence-pack] report={output_path}")
    print(f"[pr-evidence-pack] changed_files={len(pack.changed_files)}")
    print(f"[pr-evidence-pack] gate_exit_code={pack.exit_code}")
    return pack.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
