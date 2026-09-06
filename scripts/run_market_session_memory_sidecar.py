#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from core.market_session_memory_sidecar import capture_preflight

parser = argparse.ArgumentParser()
parser.add_argument("--session-id", required=True)
parser.add_argument("--source-sha", required=True)
parser.add_argument("--core-sha", required=True)
parser.add_argument("--sidecar-sha", required=True)
parser.add_argument("--storage-epoch", required=True)
parser.add_argument("--blocked", action="store_true")
args = parser.parse_args()
result = capture_preflight(session_id=args.session_id, source_sha=args.source_sha, core_sha=args.core_sha,
                           sidecar_sha=args.sidecar_sha, storage_epoch=args.storage_epoch,
                           storage_writable=not args.blocked, session_memory_available=not args.blocked)
print(json.dumps(result, sort_keys=True, default=str))
raise SystemExit(0 if result["outcome"] == "PASS" else 2)
