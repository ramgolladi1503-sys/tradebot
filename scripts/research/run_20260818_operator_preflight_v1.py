#!/usr/bin/env python3
"""Fail-closed local operator preflight for the 2026-08-18 observation session.

Run from any checkout. This script never starts TradeBot or a WebSocket feed and
never changes trading authority. It validates the frozen producer worktree,
disk, process isolation, safety environment, the frozen producer's cached
pre-live readiness gate, and optionally the frozen producer's real read-only
Kite network authentication path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import contextlib
from pathlib import Path
from typing import Any

FROZEN_PRODUCER_SHA = "f0f5b3d3659415ab36662291e91b8f57fd8d1e07"
DEFAULT_PRODUCER = Path("/Users/madhuram/tradebot-live-20260818")
DEFAULT_RUNTIME = Path("/Users/madhuram/.tradebot/runtime/2026-08-18-live-observation")
MIN_FREE_GIB = 10.0
AUTHORITY_ENV = ("BROKER_WRITE_AUTHORITY", "ORDER_AUTHORITY", "PAPER_AUTHORIZED", "LIVE_AUTHORIZED")


class PreflightError(ValueError):
    pass


def _normalize_json_value(value: Any, *, path: str = "$", _set_context: bool = False) -> Any:
    """Convert only explicitly supported representation types to JSON values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PreflightError(f"JSON_NORMALIZATION_UNKNOWN_TYPE:{path}.<key>:{type(key).__name__}")
            normalized[key] = _normalize_json_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, tuple):
        return [_normalize_json_value(item, path=f"{path}[{idx}]") for idx, item in enumerate(value)]
    if isinstance(value, list):
        return [_normalize_json_value(item, path=f"{path}[{idx}]") for idx, item in enumerate(value)]
    if isinstance(value, set):
        normalized = [_normalize_json_value(item, path=f"{path}{{{idx}}}", _set_context=True) for idx, item in enumerate(value)]
        try:
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError as exc:
            raise PreflightError(f"JSON_NORMALIZATION_UNKNOWN_TYPE:{path}:set") from exc
    module_name = type(value).__module__
    if module_name.startswith("numpy") and hasattr(value, "item"):
        return _normalize_json_value(value.item(), path=path)
    raise PreflightError(f"JSON_NORMALIZATION_UNKNOWN_TYPE:{path}:{type(value).__name__}")


_READINESS_ADAPTER = r'''
import datetime as _dt
import contextlib as _contextlib
import io as _io
import json as _json
import os as _os
from pathlib import Path as _Path
from core.pre_live_readiness_gate import evaluate_pre_live_readiness

def _normalize(value, path="$", set_context=False):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, _Path):
        return str(value)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON_NORMALIZATION_UNKNOWN_TYPE:%s.<key>:%s" % (path, type(key).__name__))
            result[key] = _normalize(item, "%s.%s" % (path, key))
        return result
    if isinstance(value, tuple):
        return [_normalize(item, "%s[%d]" % (path, idx)) for idx, item in enumerate(value)]
    if isinstance(value, list):
        return [_normalize(item, "%s[%d]" % (path, idx)) for idx, item in enumerate(value)]
    if isinstance(value, set):
        result = [_normalize(item, "%s{%d}" % (path, idx), True) for idx, item in enumerate(value)]
        return sorted(result, key=lambda item: _json.dumps(item, sort_keys=True))
    if type(value).__module__.startswith("numpy") and hasattr(value, "item"):
        return _normalize(value.item(), path)
    raise TypeError("JSON_NORMALIZATION_UNKNOWN_TYPE:%s:%s" % (path, type(value).__name__))

with _contextlib.redirect_stdout(_io.StringIO()):
    payload = evaluate_pre_live_readiness(mode="LIVE")
print(_json.dumps(_normalize(payload), sort_keys=True))
'''


def _producer_child_env(producer: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(producer) + (os.pathsep + existing if existing else "")
    return env


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        cwd=str(cwd) if cwd else None,
        env=env,
    )


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


def _readiness_gate(producer: Path, *, python_command: str = "python") -> dict[str, Any]:
    evaluator = producer / "core" / "pre_live_readiness_gate.py"
    if not evaluator.is_file():
        raise PreflightError("PRE_LIVE_GATE_EVALUATOR_MISSING")
    p = _run(
        [python_command, "-c", _READINESS_ADAPTER],
        cwd=producer,
        env=_producer_child_env(producer),
    )
    if p.returncode != 0:
        raise PreflightError(f"PRE_LIVE_GATE_EXECUTION_FAILED:{p.returncode}:{p.stderr.strip()}")
    try:
        payload = json.loads(p.stdout.strip())
    except json.JSONDecodeError as exc:
        raise PreflightError("PRE_LIVE_GATE_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise PreflightError("PRE_LIVE_GATE_PAYLOAD_INVALID")
    payload["_preflight_evaluator_source_sha256"] = hashlib.sha256(evaluator.read_bytes()).hexdigest()
    payload["_preflight_normalization_schema"] = "strict-json-v1"
    return payload


def _kite_network_auth(producer: Path, *, python_command: str = "python") -> dict[str, Any]:
    """Run the exact frozen launcher's auth checker and return redacted truth.

    The frozen checker resolves canonical credentials, acquires/releases the
    single-instance lock, and `validate_token(force=True)` performs the real
    read-only Kite `profile()` REST request. No WebSocket or order path is used.
    Raw stdout is deliberately not returned because successful output contains
    the account user_id.
    """
    script = producer / "scripts" / "check_kite_auth.py"
    if not script.is_file():
        raise PreflightError("KITE_AUTH_CHECKER_MISSING")
    p = _run(
        [python_command, str(script), "--mode", "LIVE"],
        cwd=producer,
        env=_producer_child_env(producer),
    )
    stdout = p.stdout.strip()
    stderr = p.stderr.strip()
    if p.returncode != 0:
        if p.returncode == 3 or "AUTH_REQUIRED" in stdout:
            reason = "AUTH_REQUIRED"
        elif p.returncode == 2 and "LOCK_HELD" in stdout:
            reason = "LOCK_HELD"
        elif p.returncode == 4 or "LOCK_ERROR" in stdout:
            reason = "LOCK_ERROR"
        elif p.returncode == 2 and "AUTH_CONFIG_ERROR" in stdout:
            reason = "AUTH_CONFIG_ERROR"
        else:
            reason = f"EXIT_{p.returncode}"
        # Never echo child stdout: it may include account identifiers. Stderr is
        # reduced to its exception class/message path and should not contain the
        # token, but keep the surfaced failure bounded regardless.
        bounded_error = stderr[-500:] if stderr else ""
        raise PreflightError(f"KITE_NETWORK_AUTH_FAILED:{reason}:{bounded_error}")
    if not stdout.startswith("OK user_id="):
        raise PreflightError("KITE_NETWORK_AUTH_RESULT_UNRECOGNIZED")
    user_id_present = bool(stdout.partition("OK user_id=")[2].strip())
    if not user_id_present:
        raise PreflightError("KITE_NETWORK_AUTH_PROFILE_MISSING_USER_ID")
    return {
        "verified": True,
        "method": "FROZEN_CHECK_KITE_AUTH_PROFILE_REST",
        "user_id_present": True,
        "raw_profile_exposed": False,
        "access_token_exposed": False,
        "websocket_started": False,
        "broker_write_authority": False,
        "order_authority": False,
    }


def preflight(
    producer: Path,
    runtime: Path,
    *,
    min_free_gib: float = MIN_FREE_GIB,
    verify_kite_network_auth: bool = False,
    python_command: str = "python",
) -> dict[str, Any]:
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

    gate = _readiness_gate(producer, python_command=python_command)
    outcome = str(gate.get("outcome") or "")
    if outcome == "FAIL" or gate.get("hard_fail") is True:
        raise PreflightError(f"FROZEN_PRE_LIVE_GATE_FAIL:{gate.get('blockers')}")
    if outcome not in {"MARKET_CLOSED_PENDING_TICK_PROOF", "PASS"}:
        raise PreflightError(f"FROZEN_PRE_LIVE_GATE_UNKNOWN:{outcome}")

    network_auth = (
        _kite_network_auth(producer, python_command=python_command)
        if verify_kite_network_auth
        else {
            "verified": False,
            "method": "NOT_REQUESTED",
            "user_id_present": False,
            "raw_profile_exposed": False,
            "access_token_exposed": False,
            "websocket_started": False,
            "broker_write_authority": False,
            "order_authority": False,
        }
    )

    return {
        "schema": "tradebot-operator-preflight-20260818-v2",
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
        "kite_network_auth_requested": bool(verify_kite_network_auth),
        "kite_network_auth_verified": bool(network_auth["verified"]),
        "kite_network_auth_method": network_auth["method"],
        "kite_profile_user_id_present": bool(network_auth["user_id_present"]),
        "kite_profile_or_token_exposed": False,
        "kite_auth_probe_websocket_started": False,
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
    parser.add_argument(
        "--verify-kite-network-auth",
        action="store_true",
        help="Require the frozen producer's real read-only Kite profile REST auth check to pass.",
    )
    parser.add_argument(
        "--python-command",
        default="python",
        help="Python executable used by the live launcher environment (default: python).",
    )
    args = parser.parse_args()
    payload = preflight(
        args.producer,
        args.runtime,
        min_free_gib=args.min_free_gib,
        verify_kite_network_auth=args.verify_kite_network_auth,
        python_command=args.python_command,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
