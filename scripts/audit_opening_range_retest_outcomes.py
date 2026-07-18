#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ORB outcome contract artifact.")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    path = args.artifact_dir / "opening_range_retest_outcome_contract_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "strategy_id",
        "entry_policy",
        "horizons_minutes",
        "same_bar_stop_target_policy",
        "claim_boundary",
    }
    absent = sorted(required - set(payload))
    if absent:
        print(json.dumps({"verdict": "AUDIT_INVALID", "absent_fields": absent}, sort_keys=True))
        return 1
    if payload["entry_policy"] != "first_bar_after_proposal_ready_at":
        print(json.dumps({"verdict": "AUDIT_INVALID", "reason": "entry_policy_mismatch"}, sort_keys=True))
        return 1
    print(json.dumps({"verdict": "ORB_OUTCOME_CONTRACT_READY"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
