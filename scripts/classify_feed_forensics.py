#!/usr/bin/env python3
"""Classify one completed or partial read-only session from feed_forensics.jsonl."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.feed_forensics import classify_session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    args = parser.parse_args()
    result = classify_session(args.evidence_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
