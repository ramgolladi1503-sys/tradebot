#!/usr/bin/env python3
"""Independently audit Market Event Graph live captured-metadata JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.market_event_graph_live_source import independent_raw_jsonl_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Raw live captured metadata JSONL")
    parser.add_argument("--out", type=Path, default=None, help="Optional audit report JSON path")
    args = parser.parse_args()

    report = independent_raw_jsonl_audit(args.input)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("verdict") == "PASS_RAW_LIVE_JSONL_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
