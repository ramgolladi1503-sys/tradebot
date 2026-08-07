#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.pr806_certifier_calibration_v1.calibration import build_calibration_report, run_calibration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-zip", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sparse-trials", type=int, default=200)
    parser.add_argument("--null-worlds", type=int, default=1000)
    args = parser.parse_args()

    result = run_calibration(
        args.artifact_zip,
        sparse_trials=args.sparse_trials,
        null_worlds=args.null_worlds,
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "calibration_authority.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (args.output_root / "REPORT.md").write_text(
        build_calibration_report(result),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "principal_verdict": result["principal_verdict"],
                "semantic_sha256": result["semantic_sha256"],
                "sealed_unopened_scored": result["sealed_unopened_scored"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
