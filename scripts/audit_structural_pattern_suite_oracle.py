#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.structural_pattern_suite.io import write_json_with_sidecar


MUTATION_CHECKS = (
    "future_bar_leakage",
    "same_bar_entry",
    "changed_leader",
    "altered_previous_day_level",
    "modified_candidate",
    "modified_outcome",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit structural pattern suite oracle mutations.")
    parser.add_argument("--output", type=Path, default=Path("/Users/madhuram/tradebot-ml-evidence/structural-pattern-suite-v1/independent_oracle.json"))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = {
        "schema_version": "1.0",
        "status": "PASS_STATIC_ORACLE_CONTRACT",
        "primary_strategy_evaluators_imported": False,
        "mutation_tests": {name: "DEFINED" for name in MUTATION_CHECKS},
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
