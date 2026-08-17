#!/usr/bin/env python3
"""Fail-closed local operator preflight for the 2026-08-18 observation session.

Run from any checkout. This script never starts TradeBot, never contacts the
broker directly, and never changes runtime authority. It validates the frozen
producer worktree, disk, process isolation, safety environment, and the frozen
producer's read-only cached pre-live readiness gate.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

FROZEN_PRODUCER_SHA = "f0f5b3d3659415ab36662291e91b8f57fd8d1e07"
DEFAULT_PRODUCER = Path("/Users/madhuram/tradebot-live-20260818")
DEFAULT_RUNTIME = Path("/Users/madhuram/.tradebot/runtime/2026-08-18-live-observation")
MIN_FREE_GIB = 10.0
AUTHORITY_ENV = ("BROKER_WRITE_AUTHORITY", "ORDER_AUTHORITY", "PAPER_AUTHORIZED", "LIVE_AUTHORIZED")


class PreflightError(ValueError):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _git(root: Path, *args: str) -> str:
    p = _run(["git", "-C", str(root), *args])
    if p.returncode != 0:
        raise PreflightError(f"GIT_CHECK_FAILED:{' '.join(args)}:{p.stderr.strip()}")
    return p.stdout.strip()


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _competing_processes(producer: Path) -> list[dict[str, Any]]:
    p = _run(["ps", "-axo", "pid=,command="])
    if p.returncode != 0:
        raise PreflightError("PROCESS_LIST_FAILED")
    matches: list[dict[str, Any]] = []
    needles = (str(producer), "run_live_safe.sh", " main.py")
    self_pid = os.getpid()
    for line in p.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[1]
        if pid == self_pid:
            continue
        if "run_20260818_operator_preflight_v1.py" in command:
            continue
        if any(needle in command for needle in needles):
            matches.append({"pid": pid, "command": command})
    return matches


def _readiness_gate(producer: Path) -> dict[str, Any]:
    script = producer / "scripts" / "pre_live_readiness_gate.py"
    if not script.is_file():
        raise PreflightError("PRE_LIVE_GATE_MISSING")
    p = _run(["python3", str(script), "--mode", "LIVE", "--json"])
    if p.returncode not in {0, 2}:
        raise PreflightError(f"PRE_LIVE_GATE_EXECUTION_FAILED:{p.returncode}:{p.stderr.strip()}")
    try:
        payload = json.loads(p.stdout.strip())
    except json.JSONDecodeError as exc:
        raise PreflightError("PRE_LIVE_GATE_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise PreflightError("PRE_LIVE_GATE_PAYLOAD_INVALID")
    return payload


def preflight(producer: Path, runtime: Path, *, min_free_gib: float = MIN_FREE_GIB) -> dict[str, Any]:
    producer = producer.expanduser().resolve()
    runtime = runtime.expanduser().resolve()
    if not producer.is_dir():
        raise PreflightError("PRODUCER_WORKTREE_MISSING")
    actual_sha = _git(producer, "rev-parse", "HEAD")
    if actual_sha != FROZEN_PRODUCER_SHA:
        raise PreflightError(f"PRODUCER_SHA_MISMATCH:{actual_sha}")
    if _git(producer, "status", "--porcelain"):
        raise PreflightError("PRODUCER_WORKTREE_DIRTY")

    usage = shutil.disk_usage(producer)
    free_gib = usage.free / (1024 ** 3)
    if free_gib < float(min_free_gib):
        raise PreflightError(f"DISK_FREE_BELOW_GATE:{free_gib:.2f}GiB")

    try:
        runtime.relative_to(producer)
        raise PreflightError("RUNTIME_ROOT_INSIDE_PRODUCER")
    except ValueError:
        pass
    runtime_parent = runtime if runtime.exists() else runtime.parent
    if not runtime_parent.exists() or not os.access(runtime_parent, os.W_OK):
        raise PreflightError("RUNTIME_ROOT_NOT_WRITABLE")

    enabled_authority = {name: os.getenv(name) for name in AUTHORITY_ENV if _truthy(os.getenv(name))}
    if enabled_authority:
        raise PreflightError(f"AUTHORITY_ENV_ENABLED:{sorted(enabled_authority)}")

    processes = _competing_processes(producer)
    if processes:
        raise PreflightError(f"COMPETING_LIVE_PROCESS:{processes}")

    gate = _readiness_gate(producer)
    outcome = str(gate.get("outcome") or "")
    if outcome == "FAIL" or gate.get("hard_fail") is True:
        raise PreflightError(f"FROZEN_PRE_LIVE_GATE_FAIL:{gate.get('blockers')}")
    if outcome not in {"MARKET_CLOSED_PENDING_TICK_PROOF", "PASS"}:
        raise PreflightError(f"FROZEN_PRE_LIVE_GATE_UNKNOWN:{outcome}")

    return {
        "schema": "tradebot-operator-preflight-20260818-v1",
        "status": "PREMARKET_OBSERVATION_READY",
        "producer_worktree": str(producer),
        "producer_sha": actual_sha,
        "producer_clean": True,
        "runtime_root": str(runtime),
        "disk_free_gib": round(free_gib, 3),
        "disk_gate_gib": float(min_free_gib),
        "competing_live_processes": [],
        "frozen_pre_live_gate_outcome": outcome,
        "frozen_pre_live_gate_blockers": list(gate.get("blockers") or []),
        "live_tick_proof_accepted_from_clock_only": False,
        "actual_live_tick_proof_required_after_open": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "LIVE_READY": False,
        "LIVE_VERIFIED": False,
        "STRUCTURAL_EDGE_CERTIFIED": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", type=Path, default=DEFAULT_PRODUCER)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--min-free-gib", type=float, default=MIN_FREE_GIB)
    args = parser.parse_args()
    payload = preflight(args.producer, args.runtime, min_free_gib=args.min_free_gib)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
