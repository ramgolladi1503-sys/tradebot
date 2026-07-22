#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.structural_edge_campaign import (
    CampaignAdapterError,
    CampaignContract,
    CampaignContractError,
    build_ml_v2_development_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Adapt one side-specific ML V2 development result into campaign evidence"
    )
    parser.add_argument("--contract", required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--side", choices=("LONG", "SHORT"), required=True)
    parser.add_argument("--frozen-candidates", required=True)
    parser.add_argument("--partition-registry", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def write_hashed_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        contract = CampaignContract.load(args.contract)
        payload = build_ml_v2_development_evidence(
            contract=contract,
            hypothesis_id=args.hypothesis_id,
            side=args.side,
            frozen_candidates_path=args.frozen_candidates,
            partition_registry_path=args.partition_registry,
        )
    except (CampaignAdapterError, CampaignContractError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": "1.0",
            "stage": "development",
            "verdict": "CAMPAIGN_ADAPTER_INVALID_EVIDENCE",
            "error": str(exc),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
        write_hashed_json(Path(args.output), payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2
    write_hashed_json(Path(args.output), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
