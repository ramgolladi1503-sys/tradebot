from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.strategy_validation.data_suitability import (
    build_four_strategy_dataset_manifest,
    write_manifest_and_sidecar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the four-strategy dataset suitability manifest.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/agent_reviews/four_strategy_dataset_manifest_v1.json"),
        help="Output JSON manifest path.",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("docs/agent_reviews/four_strategy_contract_bundle_v1.json"),
        help="Frozen contract bundle path.",
    )
    parser.add_argument(
        "--root",
        dest="roots",
        action="append",
        type=Path,
        help="Additional source root to inspect. May be repeated.",
    )
    args = parser.parse_args()
    manifest = build_four_strategy_dataset_manifest(roots=args.roots, bundle_path=args.bundle)
    write_manifest_and_sidecar(manifest, output_path=args.out)
    print(
        {
            "datasets": manifest["dataset_count"],
            "corpus_status": manifest["corpus_status"],
            "output": str(args.out),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
