#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.keltner_hm_shadow.live_verifier import verify_live_session


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one complete Keltner/Hilega read-only live-shadow session.")
    parser.add_argument("--session-root", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = verify_live_session(args.session_root, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
