"""Migration note:
Runs deterministic outcome/truth reconciliation for ops and acceptance gates.
Creates/updates a status artifact without crashing fresh installs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.outcome_truth_pipeline import run_outcome_truth_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile outcomes from trades and refresh truth dataset.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when blockers exist.")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Only assess counts/thresholds without mutating outcomes/truth files.",
    )
    args = parser.parse_args()

    payload = run_outcome_truth_pipeline(
        strict=bool(args.strict),
        refresh=not bool(args.no_refresh),
        write_status=True,
    )
    print(json.dumps(payload, indent=2, default=str))
    return 1 if str(payload.get("status")) == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

