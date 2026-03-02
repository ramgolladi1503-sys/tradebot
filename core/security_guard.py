from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Iterable


REPO_TOKEN_FILE_PATTERNS: tuple[str, ...] = (
    "models/*token*.pkl",
    "**/*access_token*.pkl",
)


def _token_path() -> Path:
    override = os.getenv("TRADING_BOT_TOKEN_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    repo = Path(__file__).resolve().parents[1]
    return (repo / ".runtime" / "kite_access_token").resolve()


def token_storage_dir() -> Path:
    return _token_path().parent


def ensure_local_token_dir() -> Path:
    directory = token_storage_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        # Best effort on platforms/filesystems that do not support chmod.
        pass
    return directory


def local_token_path() -> Path:
    ensure_local_token_dir()
    return _token_path()


def write_local_kite_access_token(access_token: str) -> Path:
    token = (access_token or "").strip()
    if not token:
        raise RuntimeError("[SECURITY_GUARD] empty_access_token")
    path = local_token_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(token + "\n")
    try:
        tmp_path.chmod(0o600)
    except OSError:
        pass
    tmp_path.replace(path)
    return path


def read_local_kite_access_token() -> str:
    path = local_token_path()
    if not path.exists():
        return ""
    token = path.read_text().strip()
    if not token:
        return ""
    return token


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path.resolve())
    return sorted(out)


def find_repo_token_artifacts(repo_root: Path | str) -> list[Path]:
    root = Path(repo_root).resolve()
    hits: list[Path] = []
    for pattern in REPO_TOKEN_FILE_PATTERNS:
        for candidate in root.glob(pattern):
            if candidate.is_file():
                hits.append(candidate)
    return _unique_paths(hits)


def _token_artifact_message(repo_root: Path, artifacts: list[Path]) -> str:
    rel_paths = [str(path.relative_to(repo_root)) for path in artifacts]
    rm_cmd = " ".join(rel_paths)
    return (
        "[SECURITY_GUARD] token_artifact_in_repo\n"
        "Detected token artifacts inside repository:\n"
        + "\n".join(f"  - {item}" for item in rel_paths)
        + "\n"
        "Remediation:\n"
        f"  1) Remove files: rm {rm_cmd}\n"
        "  2) Rotate token in Kite dashboard\n"
        "  3) Re-create token via models/generate_kite_token.py or "
        "scripts/generate_kite_access_token.py (stores in .runtime/kite_access_token)\n"
        "  4) Re-run startup"
    )


def enforce_no_repo_token_artifacts(repo_root: Path | str) -> None:
    root = Path(repo_root).resolve()
    artifacts = find_repo_token_artifacts(root)
    if artifacts:
        raise RuntimeError(_token_artifact_message(root, artifacts))


def resolve_kite_access_token(repo_root: Path | str, require_token: bool = True) -> str:
    from core.auth_manager import resolve_access_token

    return resolve_access_token(
        repo_root_path=repo_root,
        require_token=require_token,
        enforce_artifact_check=True,
    )


def enforce_startup_security(repo_root: Path | str, require_token: bool = True) -> str:
    token = resolve_kite_access_token(repo_root=repo_root, require_token=require_token)
    _write_guard_event(repo_root, token_present=bool(token))
    return token


def _write_guard_event(repo_root: Path | str, token_present: bool) -> None:
    root = Path(repo_root).resolve()
    log_path = root / "logs" / "security_guard.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_epoch": time.time(),
        "event": "startup_guard_pass" if token_present else "startup_guard_no_token",
        "repo_root": str(root),
        "token_source": "repo_or_env_ci" if token_present else "none",
    }
    serialized = json.dumps(row, ensure_ascii=True) + "\n"
    with log_path.open("a") as handle:
        handle.write(serialized)
    try:
        mode = log_path.stat().st_mode
        if mode & stat.S_IWOTH:
            log_path.chmod(mode & ~stat.S_IWOTH)
    except OSError:
        pass
