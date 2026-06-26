#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.repo_forensics.config_loader import ConfigError, load_config
from tools.repo_forensics.product_reality import (
    audit_product_reality,
    write_product_reality_report,
)


DEFAULT_OUTPUT = "docs/repo_forensics/reports/product_reality_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run static TradeBot product reality audit."
    )
    parser.add_argument(
        "--repo", default=".", help="Repository root. Default: current directory."
    )
    parser.add_argument(
        "--config", default=".gsd-forensics.yaml", help="Forensics config path."
    )
    parser.add_argument(
        "--out", default=DEFAULT_OUTPUT, help="Product reality report output path."
    )
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
        report = audit_product_reality(repo_root, config)
        written = write_product_reality_report(report, out_path)
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"[product-reality][ERROR] {exc}")
        return 2

    print(f"[product-reality] report={written}")
    print(f"[product-reality] proven={len(report.proven)}")
    print(f"[product-reality] partially_proven={len(report.partially_proven)}")
    print(f"[product-reality] theoretical={len(report.theoretical)}")
    print(f"[product-reality] mocked={len(report.mocked)}")
    print(f"[product-reality] unproven={len(report.unproven)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
