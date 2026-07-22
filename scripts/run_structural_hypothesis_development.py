#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.ml_strategy_discovery.upstox_source import (
    load_certified_upstox_underlying,
)
from research.ml_strategy_discovery_v2.artifacts import (
    resolve_code_sha,
    sha256_file,
)
from research.ml_strategy_discovery_v2.data import load_registry
from research.ml_strategy_discovery_v2.source import (
    development_manifest_payload,
    load_and_verify_manifest,
    verify_selected_record_files,
)
from research.structural_edge_campaign import CampaignContract
from research.structural_edge_campaign.development import (
    run_preregistered_development_screen,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a frozen development-only HIM-30 or EOGF-30 screen"
        )
    )
    parser.add_argument("--source-project-root", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--hypothesis-id", choices=("HIM_30", "EOGF_30"), required=True)
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--permutation-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--development-only", action="store_true", required=True)
    return parser.parse_args()


def write_hashed_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    project_root = Path(args.source_project_root).expanduser().resolve()
    contract_path = Path(args.contract).expanduser().resolve()
    source_manifest = Path(args.source_manifest).expanduser()
    if not source_manifest.is_absolute():
        source_manifest = (project_root / source_manifest).resolve()
    output = Path(args.output).expanduser().resolve()

    contract = CampaignContract.load(contract_path)
    hypothesis = next(
        item
        for item in contract.hypotheses
        if item.hypothesis_id == args.hypothesis_id
    )
    specification_path = (contract_path.parent / hypothesis.spec_path).resolve()
    specification = json.loads(specification_path.read_text(encoding="utf-8"))
    registry_path = project_root / "research/ml_strategy_discovery/v2_validation_registry.json"
    registry = load_registry(registry_path)
    source_payload, source_identity = load_and_verify_manifest(source_manifest)
    selected_manifest = development_manifest_payload(
        source_payload,
        instrument=args.instrument,
        registry=registry,
    )
    selected_manifest_path = output.with_name(
        f"{args.hypothesis_id.lower()}_development_source_selection_manifest.json"
    )
    selected_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    selected_manifest_path.write_text(
        json.dumps(selected_manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    selected_manifest_sha256 = sha256_file(selected_manifest_path)
    verification = verify_selected_record_files(
        project_root, selected_manifest["records"]
    )
    source_bundle = load_certified_upstox_underlying(
        source_project_root=project_root,
        source_manifest_path=selected_manifest_path,
        instrument=args.instrument,
    )
    result = run_preregistered_development_screen(
        source_bundle.bars,
        specification=specification,
        frozen_spec_sha256=hypothesis.frozen_spec_sha256,
        source_manifest_sha256=selected_manifest_sha256,
        code_sha=resolve_code_sha(project_root),
        bootstrap_iterations=args.bootstrap_iterations,
        permutation_iterations=args.permutation_iterations,
        seed=args.seed,
    )
    result["source_manifest_authority_sha256"] = source_identity["manifest_sha256"]
    result["development_source_selection_manifest_sha256"] = selected_manifest_sha256
    result["development_source_record_count"] = len(
        selected_manifest["records"]
    )
    result["development_source_file_verification"] = verification
    write_hashed_json(output, result)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
