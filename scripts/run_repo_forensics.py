#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.repo_forensics.config_loader import ConfigError, load_config
from tools.repo_forensics.repo_cartographer import build_repo_map
from tools.repo_forensics.report_writer import write_repo_map_report


DEFAULT_CONFIG = ".gsd-forensics.yaml"
DEFAULT_OUTPUT = "docs/repo_forensics/reports/repo_map_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local, read-only TradeBot repo-forensics checks.")
    parser.add_argument("--repo", default=".", help="Repository root to scan. Default: current directory.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Forensics config path. Default: .gsd-forensics.yaml")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Repo map Markdown report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = repo_root / out_path

    try:
        config = load_config(config_path)
        repo_map = build_repo_map(repo_root, config)
        report_path = write_repo_map_report(repo_map, out_path)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"[repo-forensics][ERROR] {exc}")
        return 2

    missing_required = len(repo_map.missing_required_entrypoints)
    missing_critical = len(repo_map.missing_critical_modules)
    print(f"[repo-forensics] report={report_path}")
    print(f"[repo-forensics] files={repo_map.inventory.total_files}")
    print(f"[repo-forensics] missing_required_entrypoints={missing_required}")
    print(f"[repo-forensics] missing_critical_modules={missing_critical}")
    if missing_required or missing_critical:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
