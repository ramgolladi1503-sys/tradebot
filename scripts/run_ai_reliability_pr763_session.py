#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from core.ai_reliability_agent.pr763_session import certify_pr763_session


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify one sealed PR #763 evidence root and runtime-authority snapshots."
    )
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument(
        "--authority-snapshot",
        action="append",
        default=[],
        help="JSON or JSONL authority snapshot; repeat for multiple files.",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = certify_pr763_session(
        evidence_root=args.evidence_root,
        authority_snapshot_paths=args.authority_snapshot,
        output_dir=args.output_dir,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["verdict"] != "FAILED_CLOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
