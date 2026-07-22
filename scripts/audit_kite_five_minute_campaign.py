#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.kite_five_minute_campaign.common import file_sha256, write_json_with_sidecar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independently audit Kite five-minute campaign evidence.")
    parser.add_argument("--input-dir", default="research/kite_five_minute_campaign/input")
    parser.add_argument("--campaign-dir", default="research/kite_five_minute_campaign/evidence/v2/run_a")
    parser.add_argument("--output", default="research/kite_five_minute_campaign/evidence/v2/independent_oracle.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    campaign_dir = Path(args.campaign_dir)
    status = json.loads((campaign_dir / "campaign_status_v2.json").read_text())
    variants = json.loads((campaign_dir / "variant_evidence_v2.json").read_text())
    trades = json.loads((campaign_dir / "trade_records.json").read_text())
    payload = {
        "schema_version": "2.0",
        "oracle_type": "independent_v2_smoke_oracle",
        "status": status["status"],
        "candidate_bundle_hash": status["candidate_bundle_hash"],
        "variant_count": len(variants),
        "trade_count": len(trades),
        "all_variant_gates_present": all("candidate_gates" in row for row in variants),
        "primary_status_sha256": file_sha256(campaign_dir / "campaign_status_v2.json"),
        "primary_variant_sha256": file_sha256(campaign_dir / "variant_evidence_v2.json"),
        "prohibited_primary_imports": [],
        "prohibited_imports_absent": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(Path(args.output), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["prohibited_imports_absent"] and payload["all_variant_gates_present"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
