from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.structural_edge_discovery_v3.engine import independent_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently audit structural edge discovery V3 outputs.")
    parser.add_argument("output_dir", type=Path, nargs="?", default=Path("research/structural_edge_discovery_v3"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    report = independent_audit(out)
    print(report)
    return 0 if report.get("audit_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
