#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from tools.code_excellence.ariadne_clustering import (
    cluster_findings,
    load_normalized_findings,
    write_ariadne_cluster_report,
)


DEFAULT_OUTPUT = "docs/code_excellence/ariadne/reports/ariadne_clusters_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cluster normalized Code Excellence findings with Ariadne."
    )
    parser.add_argument(
        "--findings", required=True, help="Path to normalized findings JSON file."
    )
    parser.add_argument(
        "--out", default=DEFAULT_OUTPUT, help="Ariadne cluster report output path."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        findings = load_normalized_findings(args.findings)
        report = cluster_findings(findings)
        written = write_ariadne_cluster_report(report, Path(args.out))
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ariadne][ERROR] {exc}")
        return 2

    print(f"[ariadne] report={written}")
    print(f"[ariadne] clusters={report.cluster_count}")
    print(f"[ariadne] findings={report.finding_count}")
    print(f"[ariadne] duplicates={report.duplicate_count}")
    print(f"[ariadne] rejected={len(report.rejected_findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
