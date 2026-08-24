#!/usr/bin/env python3
"""Validate one session's read-only artifacts without contacting the broker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.read_only_pipeline_validation import validate_session_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--require-e2e", action="store_true")
    args = parser.parse_args()
    result = validate_session_artifacts(
        runtime_root=args.runtime_root, source_sha=args.source_sha,
        require_e2e=args.require_e2e,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["promotion_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

