#!/usr/bin/env python3
"""Bounded supervisor for the governed read-only observer.

It does not restart an unsealed session and never changes broker authority.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def _safe_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "TRADING_MODE": "SIM", "EXECUTION_MODE": "SIM",
        "LIVE_BROKER_ADAPTER_ACTIVE": "0", "ALLOW_LIVE_ORDERS": "0",
        "AUTO_TRADE": "0", "AUTO_ORDER": "0", "PAPER_TRADING_ENABLED": "false",
        "LIVE_TRADING_ENABLED": "false", "TRADEBOT_READ_ONLY": "true",
    })
    return env


def supervise(command: list[str], *, status_path: Path, poll_seconds: float = 1.0) -> int:
    env = _safe_env()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    proc = subprocess.Popen(command, env=env)
    status = {
        "state": "RUNNING", "pid": proc.pid, "started_epoch": started,
        "command": command, "read_only": True, "broker_write_authority": False,
        "order_authority": False, "orders_placed": 0, "restart_performed": False,
    }
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    try:
        while proc.poll() is None:
            time.sleep(max(0.1, poll_seconds))
            status["alive"] = proc.poll() is None
            status["last_poll_epoch"] = time.time()
            status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    except KeyboardInterrupt:
        status["state"] = "STOP_REQUESTED"
        status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)
    code = proc.returncode
    status.update({"state": "STOPPED" if code == 0 else "FAILED", "returncode": code, "ended_epoch": time.time(), "alive": False})
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    return int(code or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="child command after --")
    args = parser.parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("child command required")
    return supervise(command, status_path=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
