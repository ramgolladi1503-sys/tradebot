#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from core.market_session_memory_sidecar import verify_evidence
parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True); parser.add_argument("--session-id", required=True)
args = parser.parse_args(); result = verify_evidence(args.root, session_id=args.session_id); print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if result["status"] == "PASS" else 2)
