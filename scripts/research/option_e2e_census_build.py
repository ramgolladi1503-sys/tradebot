#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.option_e2e_recertification_v4.data_census import build_census, default_roots, write_census_artifacts


FOUNDATION_HASH = "118cc813127005e75e6eec94aa197a1795648d70d3311356c61fb9885275c37b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only option E2E data census v4 artifacts.")
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        default=None,
        help="Local data root to inspect. May be repeated. Defaults to known local historical data roots.",
    )
    parser.add_argument(
        "--output-dir",
        default="research/option_e2e_recertification_v4/data_census",
        help="Owned output directory for deterministic census artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    sidecar = repo_root / "research/option_e2e_recertification_v4/foundation_manifest.json.sha256"
    content = sidecar.read_text(encoding="utf-8").strip()
    if not content.startswith(FOUNDATION_HASH + "  foundation_manifest.json"):
        print(f"FAIL foundation hash mismatch: {content}", file=sys.stderr)
        return 2

    roots = tuple(Path(item) for item in args.roots) if args.roots else default_roots(repo_root)
    files, summary = build_census(roots, repo_root=repo_root)
    write_census_artifacts(files, summary, repo_root / args.output_dir)
    print(
        "option_e2e_census "
        f"files={summary.files_classified} "
        f"option_quote_files={summary.option_quote_files} "
        f"executable_quote_files={summary.executable_quote_files} "
        f"instrument_master_files={summary.instrument_master_files} "
        f"point_in_time_authority_files={summary.point_in_time_authority_files} "
        f"blocked_files={summary.blocked_files} "
        f"census_sha256={summary.census_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
