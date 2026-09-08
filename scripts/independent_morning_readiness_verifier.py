#!/usr/bin/env python3
"""Independent verifier for the offline Morning Readiness state contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.morning_readiness_v1 import FATAL_INVARIANTS, NON_FATAL_INVARIANTS
from scripts.morning_readiness_matrix import run


def verify() -> dict[str, object]:
    report = run()
    checks = {
        "matrix_all_pass": report["all_pass"],
        "fatal_registry_nonempty": bool(FATAL_INVARIANTS),
        "non_fatal_registry_nonempty": bool(NON_FATAL_INVARIANTS),
        "authority_false": report["read_only"] is True and report["orders_placed"] == 0,
    }
    return {"verifier": "independent_morning_readiness_v1", "checks": checks, "pass": all(checks.values()), "read_only": True, "orders_placed": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
