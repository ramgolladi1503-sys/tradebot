#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from core.market_session_memory_sidecar import compare_replay
parser = argparse.ArgumentParser(); parser.add_argument("original"); parser.add_argument("replay")
args = parser.parse_args()
with open(args.original, encoding="utf-8") as f: original=json.load(f)
with open(args.replay, encoding="utf-8") as f: replay=json.load(f)
result=compare_replay(original=original, replay=replay); print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if result["status"] == "REPLAY_MATCH" else 2)
