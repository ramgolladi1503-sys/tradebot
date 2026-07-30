#!/usr/bin/env python3
"""Run the independent dispersion-ignition ATM-straddle campaign."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.dispersion_ignition_straddle_v1.campaign import run_campaign
from research.dispersion_ignition_straddle_v1.common import DataContractError, stable_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runtime/research/dispersion_ignition_straddle_v1"),
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir
    try:
        result = run_campaign(repo_root, output_dir)
    except DataContractError as exc:
        result = {
            "principal_verdict": "DATA_CONTRACT_BLOCKED",
            "error": str(exc),
            "validation_opened": False,
            "holdout_opened": False,
        }
        stable_json(output_dir / "final_decision.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    except Exception as exc:
        result = {
            "principal_verdict": "INVALID_EVIDENCE_PIPELINE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "validation_opened": False,
            "holdout_opened": False,
        }
        stable_json(output_dir / "final_decision.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        raise
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
