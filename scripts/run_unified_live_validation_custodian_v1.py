#!/usr/bin/env python3
"""Single-owner custodian for one governed unified-live child run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from core.unified_live_validation_pr748_756.campaign_contract import CampaignIdentity
from core.unified_live_validation_pr748_756.launcher import launch_runtime_child


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _status(root: Path, **updates: object) -> None:
    path = root / "custodian_status.json"
    current = {}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    current.update(updates)
    current["updated_ts"] = time.time()
    _write_atomic(path, current)


def run(args: argparse.Namespace) -> int:
    root = Path(args.run_root)
    identity = CampaignIdentity(
        run_id=args.run_id,
        schema_version=1,
        session_date=args.session_date,
        campaign_commit_sha=args.commit_sha,
        composition_manifest_sha=args.composition_sha,
        evidence_root=str(root),
    )
    pgid = os.getpgrp()
    _write_atomic(root / "custodian_identity.json", {
        "schema_version": 1, "run_id": args.run_id, "run_root": str(root),
        "session_date": args.session_date, "expected_commit_sha": args.commit_sha,
        "origin_main_sha": args.origin_main_sha, "mode": "live",
        "timeout_sec": args.timeout_sec, "graceful_shutdown_sec": 15,
        "forced_kill_sec": 5, "custodian_pid": os.getpid(), "custodian_pgid": pgid,
        "custodian_sid": os.getsid(0), "created_wall_ts_utc": time.time(),
        "created_monotonic_ns": time.monotonic_ns(),
    })
    _status(root, state="STARTING_CHILD", reason="custodian_started", custodian_pid=os.getpid(),
            child_pid=None, terminal=False, sealed=False, timeout_deadline=time.time() + args.timeout_sec)
    try:
        result = launch_runtime_child(identity, ["./run_live.sh"], cwd=Path(args.cwd), timeout_sec=args.timeout_sec)
        state = "SEALED_SUCCESS" if result.sealed and result.exit_code == 0 else "FAILED_SEAL"
        _status(root, state=state, reason="child_and_exact_root_finalized", child_pid=result.child_pid,
                manifest_path=str(root / "artifact_manifest.json"), sealed=result.sealed,
                terminal=True, exit_code=result.exit_code)
        return 0 if result.sealed else 2
    except Exception as exc:
        _status(root, state="FAILED_SEAL", reason=f"{type(exc).__name__}:{exc}", terminal=True, sealed=False)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--composition-sha", required=True)
    parser.add_argument("--origin-main-sha", required=True)
    parser.add_argument("--timeout-sec", required=True, type=float)
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
