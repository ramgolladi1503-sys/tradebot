#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.ml_strategy_discovery_v2.artifacts import resolve_code_sha
from research.structural_edge_campaign import CampaignContract
from research.structural_edge_campaign.option_repricing_lag import (
    audit_data_readiness,
    development_evidence_from_readiness,
    file_sha256,
    load_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit and prepare development evidence for the frozen "
            "DORL-V3 buy-only option repricing-lag hypothesis."
        )
    )
    parser.add_argument("--source-project-root", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--futures-ticks")
    parser.add_argument("--option-ticks")
    parser.add_argument("--instrument-master")
    parser.add_argument("--development-only", action="store_true", required=True)
    return parser.parse_args()


def _resolve_optional(root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


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
    contract_path = Path(args.contract).expanduser()
    if not contract_path.is_absolute():
        contract_path = (project_root / contract_path).resolve()
    output = Path(args.output).expanduser().resolve()

    contract = CampaignContract.load(contract_path)
    hypothesis = next(
        item
        for item in contract.hypotheses
        if item.hypothesis_id == "DORL_V3"
    )
    specification_path = (
        contract_path.parent / hypothesis.spec_path
    ).resolve()
    specification = json.loads(
        specification_path.read_text(encoding="utf-8")
    )

    futures_path = _resolve_optional(project_root, args.futures_ticks)
    option_path = _resolve_optional(project_root, args.option_ticks)
    master_path = _resolve_optional(project_root, args.instrument_master)

    readiness = audit_data_readiness(
        futures_ticks=load_table(futures_path),
        option_ticks=load_table(option_path),
        instrument_master=load_table(master_path),
        specification=specification,
    )
    input_hashes = {
        name: digest
        for name, digest in (
            ("futures_ticks", file_sha256(futures_path)),
            ("option_ticks", file_sha256(option_path)),
            ("instrument_master", file_sha256(master_path)),
        )
        if digest is not None
    }
    evidence = development_evidence_from_readiness(
        readiness,
        specification=specification,
        frozen_spec_sha256=hypothesis.frozen_spec_sha256,
        code_sha=resolve_code_sha(project_root),
        input_hashes=input_hashes,
    )
    write_hashed_json(output, evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
