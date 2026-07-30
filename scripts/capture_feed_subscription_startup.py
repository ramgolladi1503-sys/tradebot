#!/usr/bin/env python3
"""Capture a sealed, credential-free feed subscription startup evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_CONFIRMATIONS = (
    "no_open_position",
    "no_pending_approval",
    "no_order_in_progress",
    "kite_auth_valid",
    "rollback_ready",
)
EVENT_PREFIXES = (
    "FEED_SOCKET_GENERATION_STARTED",
    "FEED_CONNECT",
    "FEED_CLOSE",
    "FEED_SUBSCRIBE_",
    "FEED_MODE_FULL_",
    "FEED_OLD_GENERATION_CALLBACK_IGNORED",
    "FEED_SUBSCRIPTION_REGISTRY_SNAPSHOT",
    "FEED_RECOVERY",
    "FEED_RECONNECT",
    "FEED_TICK",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _event_from_line(line: str) -> dict | None:
    start = line.find("{")
    if start < 0:
        return None
    try:
        payload = json.loads(line[start:])
    except json.JSONDecodeError:
        return None
    event = str(payload.get("event") or "")
    if not any(event.startswith(prefix) for prefix in EVENT_PREFIXES):
        return None
    payload.pop("access_token", None)
    payload.pop("api_key", None)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--watchdog-log", type=Path, required=True)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--duration-sec", type=int, default=120)
    for name in REQUIRED_CONFIRMATIONS:
        parser.add_argument(f"--confirm-{name.replace('_', '-')}", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    missing = [name for name in REQUIRED_CONFIRMATIONS if not getattr(args, f"confirm_{name}")]
    if missing:
        raise SystemExit(f"refusing capture; missing confirmations: {','.join(missing)}")
    repo = args.repo.resolve()
    log_path = args.watchdog_log.resolve()
    start_offset = log_path.stat().st_size if log_path.exists() else 0
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = repo / "runtime" / "diagnostics" / f"feed_subscription_startup_{timestamp}"
    output.mkdir(parents=True, exist_ok=False)
    process = None
    if args.pid:
        process = subprocess.run(
            ["ps", "-p", str(args.pid), "-o", "pid=,ppid=,lstart=,command="],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
    identity = {
        "capture_started_epoch": time.time(),
        "branch": _git(repo, "branch", "--show-current"),
        "commit": _git(repo, "rev-parse", "HEAD"),
        "pid": args.pid,
        "process": process,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "confirmations": {name: True for name in REQUIRED_CONFIRMATIONS},
    }
    (output / "process_identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    deadline = time.monotonic() + max(1, args.duration_sec)
    while time.monotonic() < deadline:
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    events = []
    if log_path.exists():
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(start_offset)
            for line in handle:
                payload = _event_from_line(line)
                if payload is not None:
                    events.append(payload)
    events_path = output / "subscription_events.jsonl"
    events_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in events))
    manifest = {
        "sealed_epoch": time.time(),
        "event_count": len(events),
        "files": [],
    }
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json":
            continue
        manifest["files"].append(
            {"path": path.name, "size": path.stat().st_size, "sha256": _sha256(path)}
        )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "SEALED").write_text(f"sealed_at={manifest['sealed_epoch']}\n")
    for path in output.iterdir():
        path.chmod(0o444)
    output.chmod(0o555)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
