import json
import os
import time
from pathlib import Path
from typing import Tuple

from config import config as cfg
from core.paths import locks_dir


class RunLock:
    def __init__(self, name: str | None = None, max_age_sec: float | None = None, lock_dir: Path | None = None):
        self.name = name or getattr(cfg, "RUN_LOCK_NAME", "live_monitoring.lock")
        self.max_age_sec = float(max_age_sec if max_age_sec is not None else getattr(cfg, "RUN_LOCK_MAX_AGE_SEC", 3600))
        self.lock_dir = Path(lock_dir) if lock_dir is not None else locks_dir()
        self.lock_path = self.lock_dir / self.name
        self._active_lock_path = self.lock_path
        self._last_reason = "UNINITIALIZED"

    def _resolve_active_lock_path(self) -> Path:
        target_dir = self.lock_dir
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            self._active_lock_path = target_dir / self.name
            return self._active_lock_path
        except PermissionError:
            fallback_dir = locks_dir()
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self._active_lock_path = fallback_dir / self.name
            self._last_reason = "LOCK_DIR_FALLBACK"
            return self._active_lock_path

    def _atomic_write(self, payload: dict) -> None:
        lock_path = self._resolve_active_lock_path()
        tmp_path = lock_path.with_suffix(lock_path.suffix + ".tmp")
        try:
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
            tmp_path.replace(lock_path)
        except PermissionError:
            fallback_dir = locks_dir()
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback_lock = fallback_dir / self.name
            fallback_tmp = fallback_lock.with_suffix(fallback_lock.suffix + ".tmp")
            fallback_tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            fallback_tmp.replace(fallback_lock)
            self._active_lock_path = fallback_lock
            self._last_reason = "LOCK_DIR_FALLBACK"

    def _read(self) -> dict:
        lock_path = self._resolve_active_lock_path()
        if not lock_path.exists():
            return {}
        try:
            return json.loads(lock_path.read_text())
        except Exception:
            return {}

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            # Conservative: assume alive if we lack permission.
            return True
        except Exception:
            return False

    def acquire(self) -> Tuple[bool, str]:
        now = time.time()
        current = self._read()
        if current.get("locked") is True:
            # Allow re-entrant lock acquisition by the same PID.
            if current.get("pid") == os.getpid():
                self._last_reason = "RUN_LOCK_REENTRANT"
                return True, self._last_reason
            pid = current.get("pid")
            stale_pid = False
            if pid is not None:
                try:
                    pid_val = int(pid)
                except (TypeError, ValueError):
                    pid_val = None
                if pid_val is not None and not self._pid_alive(pid_val):
                    stale_pid = True
            else:
                stale_pid = True

            if not stale_pid and pid is not None:
                ts = current.get("timestamp_epoch")
                try:
                    ts_val = float(ts)
                except (TypeError, ValueError):
                    ts_val = None
                if ts_val is not None:
                    age = max(0.0, now - ts_val)
                    if age <= self.max_age_sec:
                        self._last_reason = "RUN_LOCK_ACTIVE"
                        return False, self._last_reason
                # If timestamp missing/invalid but PID alive, block.
                if ts is None or ts_val is None:
                    self._last_reason = "RUN_LOCK_ACTIVE"
                    return False, self._last_reason
        payload = {
            "locked": True,
            "timestamp_epoch": now,
            "pid": os.getpid(),
            "name": self.name,
            "reason": "ACTIVE",
        }
        self._atomic_write(payload)
        self._last_reason = "OK"
        return True, self._last_reason

    def release(self) -> None:
        now = time.time()
        payload = {
            "locked": False,
            "timestamp_epoch": now,
            "pid": os.getpid(),
            "name": self.name,
            "reason": "RELEASED",
        }
        self._atomic_write(payload)
        self._last_reason = "RELEASED"

    def state_dict(self) -> dict:
        now = time.time()
        lock_path = self._resolve_active_lock_path()
        current = self._read()
        ts = current.get("timestamp_epoch")
        age = None
        if ts is not None:
            try:
                age = max(0.0, now - float(ts))
            except (TypeError, ValueError):
                age = None
        return {
            "lock_name": self.name,
            "lock_path": str(lock_path),
            "max_age_sec": self.max_age_sec,
            "exists": lock_path.exists(),
            "locked": bool(current.get("locked")),
            "timestamp_epoch": current.get("timestamp_epoch"),
            "age_sec": age,
            "last_reason": self._last_reason,
        }
