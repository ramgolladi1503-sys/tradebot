"""Git, hashing, command execution, and evidence file helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Mapping

from core.agent_supervisor_types import (
    AGENT_SUPERVISOR_SCHEMA_VERSION,
    _MAX_CAPTURE_CHARS,
    _SECRET_ENV_FRAGMENTS,
    AcceptanceCommand,
    _normalize_rel_path,
    _stable_hash,
    _text,
)

def _run_git(worktree: Path, *args: str, timeout: int = 30) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=worktree,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git_command_failed"
        raise RuntimeError(f"git_{'_'.join(args)}:{message}")
    return completed.stdout.strip()


def _common_git_dir(worktree: Path) -> Path:
    raw = _run_git(worktree, "rev-parse", "--git-common-dir")
    common = Path(raw)
    if not common.is_absolute():
        common = (worktree / common).resolve()
    return common


def _claims_paths(worktree: Path) -> tuple[Path, Path]:
    root = _common_git_dir(worktree) / "agent-supervisor"
    root.mkdir(parents=True, exist_ok=True)
    return root / "claims.json", root / "claims.lock"


def _load_claim_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": AGENT_SUPERVISOR_SCHEMA_VERSION, "claims": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"claim_store_invalid:{type(exc).__name__}:{exc}") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("claims"), Mapping):
        raise RuntimeError("claim_store_shape_invalid")
    return {"schema_version": AGENT_SUPERVISOR_SCHEMA_VERSION, "claims": dict(payload["claims"])}


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, default=str)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        handle.write(encoded)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _hash_path(root: Path, relative_path: str) -> dict[str, Any]:
    target = root / relative_path
    if not target.exists() and not target.is_symlink():
        return {"path": relative_path, "kind": "missing", "sha256": None, "size_bytes": 0}
    if target.is_symlink():
        link_text = os.readlink(target)
        return {
            "path": relative_path,
            "kind": "symlink",
            "sha256": hashlib.sha256(link_text.encode("utf-8")).hexdigest(),
            "size_bytes": len(link_text.encode("utf-8")),
        }
    if target.is_file():
        digest = hashlib.sha256()
        size = 0
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        return {"path": relative_path, "kind": "file", "sha256": digest.hexdigest(), "size_bytes": size}

    digest = hashlib.sha256()
    size = 0
    file_count = 0
    for child in sorted(item for item in target.rglob("*") if item.is_file() and ".git" not in item.parts):
        rel = child.relative_to(root).as_posix()
        child_hash = _hash_path(root, rel)
        digest.update(rel.encode("utf-8"))
        digest.update(str(child_hash["sha256"]).encode("utf-8"))
        size += int(child_hash["size_bytes"])
        file_count += 1
    return {
        "path": relative_path,
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "size_bytes": size,
        "file_count": file_count,
    }


def _changed_paths(worktree: Path, base_commit: str, head_commit: str) -> tuple[str, ...]:
    output = _run_git(worktree, "diff", "--name-only", "--diff-filter=ACMRDT", f"{base_commit}..{head_commit}")
    return tuple(_normalize_rel_path(line) for line in output.splitlines() if _normalize_rel_path(line))


def _safe_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        upper = key.upper()
        if any(fragment in upper for fragment in _SECRET_ENV_FRAGMENTS):
            env.pop(key, None)
    env.update(
        {
            "TRADEBOT_AGENT_SUPERVISOR": "1",
            "KITE_USE_API": "false",
            "KITE_TRADES_SYNC": "false",
            "ENABLE_TELEGRAM": "false",
            "EMAIL_REPORTS": "false",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _capture_tail(text: str) -> str:
    return text if len(text) <= _MAX_CAPTURE_CHARS else text[-_MAX_CAPTURE_CHARS:]


def _run_acceptance_command(worktree: Path, command: AcceptanceCommand) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command.argv),
            cwd=worktree,
            env=_safe_environment(),
            text=True,
            capture_output=True,
            timeout=command.timeout_seconds,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return {
            "name": command.name,
            "argv": list(command.argv),
            "timeout_seconds": command.timeout_seconds,
            "timed_out": False,
            "exit_code": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 6),
            "stdout_tail": _capture_tail(stdout),
            "stderr_tail": _capture_tail(stderr),
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "name": command.name,
            "argv": list(command.argv),
            "timeout_seconds": command.timeout_seconds,
            "timed_out": True,
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 6),
            "stdout_tail": _capture_tail(stdout),
            "stderr_tail": _capture_tail(stderr),
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }


def _evidence_dir(worktree: Path, task_id: str) -> Path:
    return worktree / ".runtime" / "agent_supervisor" / "evidence" / task_id


def _write_hashed_manifest(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["manifest_sha256"] = _stable_hash(result)
    _atomic_write_json(path, result)
    return result


def _manifest_hash_is_valid(payload: Mapping[str, Any]) -> bool:
    expected = _text(payload.get("manifest_sha256"))
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    return bool(expected) and expected == _stable_hash(body)
