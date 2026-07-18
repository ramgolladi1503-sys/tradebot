#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.strategy_validation import (
    build_four_strategy_dataset_manifest_v2,
    build_upstox_corpus_inventory,
    sha256_file,
    write_inventory_and_sidecar,
    write_v2_manifest_and_sidecar,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the incremental Upstox corpus inventory and four-strategy manifest.")
    parser.add_argument(
        "--contract-bundle",
        "--bundle",
        dest="contract_bundle",
        type=Path,
        default=Path("docs/agent_reviews/four_strategy_contract_bundle_v1.json"),
        help="Frozen contract bundle path.",
    )
    parser.add_argument(
        "--input",
        "--root",
        dest="inputs",
        action="append",
        type=Path,
        required=True,
        help="Source root to inspect. May be repeated.",
    )
    parser.add_argument(
        "--previous-manifest",
        type=Path,
        default=Path("docs/agent_reviews/four_strategy_dataset_manifest_v1.json"),
        help="Previous immutable manifest to compare against.",
    )
    parser.add_argument(
        "--inventory-output",
        type=Path,
        default=Path("docs/agent_reviews/upstox_corpus_inventory_v2.json"),
        help="Inventory JSON output path.",
    )
    parser.add_argument(
        "--output",
        "--out",
        dest="output",
        type=Path,
        default=Path("docs/agent_reviews/four_strategy_dataset_manifest_v3.json"),
        help="Four-strategy V3 manifest output path.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        inventory = build_upstox_corpus_inventory(
            roots=args.inputs,
            bundle_path=args.contract_bundle,
            previous_manifest_path=args.previous_manifest,
        )
        manifest = build_four_strategy_dataset_manifest_v2(
            roots=args.inputs,
            bundle_path=args.contract_bundle,
            previous_manifest_path=args.previous_manifest,
            inventory=inventory,
        )
    except FileNotFoundError as exc:
        print(f"requested source root missing or unreadable: {exc}", file=sys.stderr)
        return 4
    inv_path, inv_sidecar = write_inventory_and_sidecar(inventory, output_path=args.inventory_output)
    inventory_sha256 = sha256_file(inv_path)
    inventory["inventory_sha256"] = inventory_sha256
    manifest["inventory_sha256"] = inventory_sha256
    man_path, man_sidecar = write_v2_manifest_and_sidecar(manifest, output_path=args.output)
    print(
        {
            "inventory": str(inv_path),
            "inventory_sha256": str(inv_sidecar),
            "manifest": str(man_path),
            "manifest_sha256": str(man_sidecar),
            "corpus_snapshot_id": inventory["corpus_snapshot_id"],
            "data_snapshot_id": inventory["data_snapshot_id"],
            "signal_verdict": manifest["signal_verdict"],
            "execution_verdict": manifest["execution_verdict"],
            "source_files": inventory["file_counts"]["total_source_files"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
