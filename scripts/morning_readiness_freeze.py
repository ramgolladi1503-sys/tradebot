#!/usr/bin/env python3
"""Create a conservative offline night-before readiness artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.independent_morning_readiness_verifier import verify


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--next-session-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    clean = not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    independent = verify()
    payload = {
        "artifact": "MORNING_READINESS_V1_NIGHT_BEFORE_FREEZE",
        "next_session_date": args.next_session_date,
        "release_sha_requested": args.release,
        "release_sha_actual": actual,
        "release_sha_match": actual == args.release,
        "worktree_clean": clean,
        "offline_state_machine_certified": independent["pass"],
        "full_morning_readiness_certified": False,
        "next_live_session_ready": False,
        "reason": "master_launcher_and_eod_seal_not_certified",
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "orders_placed": 0,
    }
    payload["artifact_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
