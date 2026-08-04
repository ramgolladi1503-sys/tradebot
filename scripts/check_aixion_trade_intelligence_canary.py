#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from aixion_trade_intelligence.readiness import evaluate_canary_readiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed readiness check for an Aixion read-only paper/shadow canary."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    readiness = evaluate_canary_readiness(args.config)
    record = readiness.to_record()
    rendered = json.dumps(record, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if readiness.ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
