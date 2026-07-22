#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.kite_five_minute_campaign import audit_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independently audit Kite five-minute campaign evidence.")
    parser.add_argument("--input-dir", default="research/kite_five_minute_campaign/input")
    parser.add_argument("--campaign-dir", default="research/kite_five_minute_campaign/evidence/run_a")
    parser.add_argument("--output", default="research/kite_five_minute_campaign/evidence/independent_audit.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = audit_campaign(Path(args.input_dir), Path(args.campaign_dir), Path(args.output))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["matches_primary_verdict"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
