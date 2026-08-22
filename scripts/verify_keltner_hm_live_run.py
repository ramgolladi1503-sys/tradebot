#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.events).read_text().splitlines() if line.strip()]
    ids = [row["event_id"] for row in rows]
    violations = [row for row in rows if any((row.get("rankable"), row.get("executable"),
        row.get("execution_allowed"), row.get("broker_api_called"), row.get("is_order_action")))]
    entries = [row for row in rows if row["event_type"] == "KELTNER_HM_SHADOW_ENTRY"]
    outcomes = [row for row in rows if row["event_type"] == "KELTNER_HM_SHADOW_OUTCOME"]
    verdict = "PASS_LIVE_SHADOW_RUN" if len(ids) == len(set(ids)) and not violations and outcomes else "LIVE_SHADOW_EVIDENCE_INCOMPLETE"
    result = {"verdict": verdict, "events": len(rows), "entries": len(entries), "outcomes": len(outcomes),
        "duplicate_event_ids": len(ids) - len(set(ids)), "authority_violations": len(violations)}
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if verdict == "PASS_LIVE_SHADOW_RUN" else 2

if __name__ == "__main__":
    raise SystemExit(main())
