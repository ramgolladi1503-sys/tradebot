#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.backtesting.data_catalog import build_catalog_from_config, load_backtest_config, write_catalog


def run_import_catalog_scan(*, config_path: str | Path, output_path: str | Path | None = None) -> Path:
    config = load_backtest_config(config_path)
    catalog = build_catalog_from_config(config)
    if output_path is not None:
        target = Path(output_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(catalog.to_payload(), indent=2, sort_keys=True), encoding="utf-8")
        return target
    return write_catalog(catalog)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and register local historical data sources without broker calls.")
    parser.add_argument("--config", required=True, help="Path to JSON config for source roots.")
    parser.add_argument("--output", default="", help="Optional catalog output path override.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and write only the catalog manifest.")
    args = parser.parse_args(argv)

    out = run_import_catalog_scan(config_path=args.config, output_path=args.output or None)
    action = "catalog_only" if args.dry_run else "catalog_manifest_written"
    print(f"{action}: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
