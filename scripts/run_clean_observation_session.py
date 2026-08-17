#!/usr/bin/env python3
"""Launch exactly one clean-checkout producer in observation-only mode."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


LAUNCHER_VERSION = "clean-observation-v1"
TRUTHY = {"1", "true", "yes", "on", "live"}
AUTHORITY_KEYS = (
    "ALLOW_LIVE_PLACEMENT",
    "LIVE_TRADING_ENABLED",
    "PAPER_TRADING_ENABLED",
    "AUTO_TRADE",
    "AUTO_ORDER",
)


class LaunchBlocked(RuntimeError):
    pass


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _absolute_external_path(name: str, value: str, repo_root: Path) -> Path:
    if not str(value or "").strip():
        raise LaunchBlocked(f"{name}_REQUIRED")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise LaunchBlocked(f"{name}_MUST_BE_ABSOLUTE")
    path = path.resolve()
    if path == repo_root or repo_root in path.parents:
        raise LaunchBlocked(f"{name}_INSIDE_REPOSITORY")
    return path


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _load_external_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise LaunchBlocked("TRADEBOT_ENV_FILE_MISSING")
    try:
        from dotenv import dotenv_values

        values = dotenv_values(path)
    except ImportError as exc:
        raise LaunchBlocked("DOTENV_LOADER_UNAVAILABLE") from exc
    return {str(key): str(value) for key, value in values.items() if key and value is not None}


def _assert_safety(env: dict[str, str]) -> None:
    if str(env.get("OBSERVATION_ONLY_MODE", "true")).strip().lower() != "true":
        raise LaunchBlocked("OBSERVATION_ONLY_MODE_REQUIRED")
    conflicts = [key for key in AUTHORITY_KEYS if _truthy(env.get(key))]
    if conflicts:
        raise LaunchBlocked("AUTHORITY_CONFLICT:" + ",".join(conflicts))
    env.update(
        {
            "OBSERVATION_ONLY_MODE": "true",
            "ALLOW_LIVE_PLACEMENT": "0",
            "LIVE_TRADING_ENABLED": "false",
            "PAPER_TRADING_ENABLED": "false",
            "AUTO_TRADE": "0",
            "AUTO_ORDER": "0",
            "LIVE_AUDIT_ONLY": "1",
            "TRADEBOT_READ_ONLY": "true",
        }
    )
    for key in ("broker_write_authority", "order_authority", "paper_authorized", "live_authorized"):
        if _truthy(env.get(key)):
            raise LaunchBlocked(f"AUTHORITY_CONFLICT:{key}")


def prepare_session() -> tuple[Path, dict[str, str], dict[str, object]]:
    repo_root = _repo_root()
    expected_sha = os.environ.get("EXPECTED_MAIN_SHA", "").strip()
    if not expected_sha:
        raise LaunchBlocked("EXPECTED_MAIN_SHA_REQUIRED")
    env_file = _absolute_external_path("TRADEBOT_ENV_FILE", os.environ.get("TRADEBOT_ENV_FILE", ""), repo_root)
    runtime_root = _absolute_external_path("TRADEBOT_RUNTIME_ROOT", os.environ.get("TRADEBOT_RUNTIME_ROOT", ""), repo_root)
    head = _git(repo_root, "rev-parse", "HEAD")
    if head != expected_sha:
        raise LaunchBlocked("HEAD_MISMATCH")
    if _git(repo_root, "status", "--porcelain"):
        raise LaunchBlocked("CLEAN_TREE_REQUIRED")
    env = dict(os.environ)
    env.update(_load_external_env(env_file))
    _assert_safety(env)
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    session_id = f"clean-observation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    session_root = runtime_root / session_id
    roots = {name: session_root / name for name in ("manifest", "logs", "evidence", "locks", "observers")}
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=False)
        probe = path / ".write_probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    env.update(
        {
            "DATA_ROOT": str(session_root),
            "LOGS_ROOT": str(roots["logs"]),
            "REPORTS_ROOT": str(roots["evidence"]),
            "LOCKS_ROOT": str(roots["locks"]),
            "DB_ROOT": str(session_root / "db"),
            "TRADEBOT_RUN_ID": session_id,
        }
    )
    (session_root / "db").mkdir(exist_ok=True)
    sys.path.insert(0, str(repo_root))
    from core.observation_execution_guard import observation_only_enabled

    if not callable(observation_only_enabled) or env.get("OBSERVATION_ONLY_MODE") != "true":
        raise LaunchBlocked("OBSERVATION_GUARD_UNAVAILABLE")
    manifest = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "head_sha": head,
        "git_clean": True,
        "observation_only_mode": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "credential_source_path": str(env_file),
        "credential_source_present": True,
        "runtime_root": str(session_root),
        "tracked_runtime_write_risk": False,
        "launcher_version": LAUNCHER_VERSION,
        "launcher_path": str(Path(__file__).resolve()),
    }
    manifest_path = roots["manifest"] / "session_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return session_root, env, {"manifest": manifest_path, "session_id": session_id}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        session_root, env, metadata = prepare_session()
    except LaunchBlocked as exc:
        print(f"OBSERVATION_LAUNCH_BLOCKED={exc}", file=sys.stderr)
        return 2
    print(f"OBSERVATION_SESSION_MANIFEST={metadata['manifest']}")
    if args.validate_only:
        return 0
    producer = subprocess.Popen([sys.executable, str(_repo_root() / "main.py")], cwd=_repo_root(), env=env)
    print(f"OBSERVATION_PRODUCER_PID={producer.pid}")
    return producer.wait()


if __name__ == "__main__":
    raise SystemExit(main())
