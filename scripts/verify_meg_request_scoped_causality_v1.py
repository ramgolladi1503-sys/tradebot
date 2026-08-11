#!/usr/bin/env python3
"""Verify one explicit sealed MEG #803 evidence root, read-only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.meg_request_scoped_causality import verify_root

EXIT_CODES = {
    "PASS_MEG_REQUEST_SCOPED_CAUSALITY": 0,
    "FAIL_MEG_REQUEST_SCOPED_CAUSALITY": 1,
    "INCOMPLETE_MEG_REQUEST_SCOPED_CAUSALITY_EVIDENCE": 2,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.evidence_root.expanduser().resolve()
    if not root.is_dir():
        result = {"evidence_root": str(root), "verdict": "INCOMPLETE_MEG_REQUEST_SCOPED_CAUSALITY_EVIDENCE", "error": "evidence_root_missing"}
    else:
        result = verify_root(root)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return EXIT_CODES.get(str(result.get("verdict")), 2)


if __name__ == "__main__":
    raise SystemExit(main())
