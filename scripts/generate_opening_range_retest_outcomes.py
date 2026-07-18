#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.strategy_outcomes.artifacts import write_json_artifact  # noqa: E402
from research.strategy_outcomes.contract import HORIZONS_MINUTES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ORB underlying outcome contract artifact.")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "schema_version": 1,
        "strategy_id": "opening_range_retest_v1",
        "mode": "RESEARCH_OUTCOME_CONTRACT",
        "entry_policy": "first_bar_after_proposal_ready_at",
        "horizons_minutes": list(HORIZONS_MINUTES),
        "same_bar_stop_target_policy": "AMBIGUOUS_SAME_BAR",
        "claim_boundary": "underlying_descriptive_outcomes_only",
        "is_order_action": False,
        "broker_api_called": False,
    }
    digest = write_json_artifact(args.out_dir / "opening_range_retest_outcome_contract_v1.json", payload)
    print(json.dumps({"verdict": "ORB_OUTCOME_CONTRACT_WRITTEN", "semantic_hash": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
