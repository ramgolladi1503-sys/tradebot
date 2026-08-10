#!/usr/bin/env python3
"""Read-only progress view for the canonical feed-forensics ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.feed_forensics import classify_session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.evidence_root
    ledger = root / "feed_forensics.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger.is_file() else []
    latest = {}
    for row in rows:
        latest[row.get("event_type")] = row
    result = {
        "process_alive": (root / "process_identity.json").is_file() and not (root / "shutdown_drain.json").is_file(),
        "last_ws_callback_epoch": (latest.get("WS_CALLBACK") or {}).get("receipt_epoch"),
        "last_full_packet_epoch": (latest.get("FULL_PACKET_PROGRESS") or {}).get("receipt_epoch"),
        "last_tick_persist_epoch": (latest.get("TICK_PERSISTENCE_PROGRESS") or {}).get("receipt_epoch"),
        "last_depth_persist_epoch": (latest.get("DEPTH_PERSISTENCE_PROGRESS") or {}).get("receipt_epoch"),
        "last_runtime_snapshot_epoch": (latest.get("RUNTIME_PERSISTENCE_PROGRESS") or {}).get("receipt_epoch"),
        "feed_session_id": (latest.get("WS_CALLBACK") or {}).get("feed_session_id"),
        "reconnect_generation": (latest.get("WS_CALLBACK") or {}).get("reconnect_generation"),
        "tick_queue_depth": (latest.get("TICK_PERSISTENCE_PROGRESS") or {}).get("queue_depth"),
        "depth_queue_depth": (latest.get("DEPTH_PERSISTENCE_PROGRESS") or {}).get("queue_depth"),
        "runtime_queue_depth": (latest.get("RUNTIME_PERSISTENCE_PROGRESS") or {}).get("queue_depth"),
        "watchdog_state": (latest.get("FEED_WATCHDOG") or {}).get("status"),
        "recovery_state": (latest.get("RECOVERY_SUCCEEDED") or latest.get("RECOVERY_FAILED") or {}).get("event_type"),
        "disk_free": None,
        "forensic_classification": classify_session(root),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
