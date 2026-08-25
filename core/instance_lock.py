from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

from core.paths import repo_root, locks_dir

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - non-posix fallback
    fcntl = None


class InstanceLock:
    """
    Process-wide single-instance lock for Kite sessions.
    Uses a POSIX file lock so stale lock files do not block forever.
    """

    def __init__(self, lock_path: Path | str | None = None, repo_root_path: Path | str | None = None):
        root = Path(repo_root_path).resolve() if repo_root_path is not None else repo_root()
        default = locks_dir() / "kite_session.lock"
        self.lock_path = Path(lock_path).resolve() if lock_path is not None else default.resolve()
        self._fd: int | None = None
        self._acquired = False

    def holder_info(self) -> dict[str, Any]:
        try:
            raw = self.lock_path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def acquire(self) -> tuple[bool, dict[str, Any]]:
        if self._acquired:
            return True, self.holder_info()
        if fcntl is None:
            raise RuntimeError("instance_lock_unavailable:fcntl_missing")

        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise RuntimeError(f"instance_lock_permission_denied:path={self.lock_path}") from exc
        try:
            fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        except PermissionError as exc:
            raise RuntimeError(f"instance_lock_permission_denied:path={self.lock_path}") from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False, self.holder_info()
        except Exception:
            os.close(fd)
            raise

        self._fd = fd
        self._acquired = True
        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "acquired_at_epoch": time.time(),
            "lock_path": str(self.lock_path),
        }
        self._write_payload(payload)
        return True, payload

    def _write_payload(self, payload: dict[str, Any]) -> None:
        if self._fd is None:
            return
        data = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.ftruncate(self._fd, 0)
        os.write(self._fd, data)
        os.fsync(self._fd)

    def release(self) -> None:
        lock_path = self.lock_path
        if self._fd is None:
            self._acquired = False
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
            self._acquired = False
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass

    def __enter__(self) -> "InstanceLock":
        ok, holder = self.acquire()
        if not ok:
            pid = holder.get("pid")
            raise RuntimeError(f"instance_lock_active:pid={pid}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
