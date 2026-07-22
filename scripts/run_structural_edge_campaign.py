#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.structural_edge_campaign import (
    CampaignContract,
    CampaignContractError,
    CampaignEvidenceError,
    evaluate_campaign,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a preregistered structural-edge campaign without opening "
            "protected evidence out of order."
        )
    )
    parser.add_argument("--contract", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _write_json_with_sidecar(path: Path, payload: dict) -> None:
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
    output = Path(args.output).expanduser().resolve()
    try:
        contract = CampaignContract.load(args.contract)
        evaluation = evaluate_campaign(contract, args.evidence_root)
        payload = evaluation.to_mapping()
        exit_code = 0
    except (CampaignContractError, CampaignEvidenceError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": "1.0",
            "verdict": "CAMPAIGN_INVALID_EVIDENCE",
            "error": str(exc),
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }
        exit_code = 2
    _write_json_with_sidecar(output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
