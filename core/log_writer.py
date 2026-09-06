from __future__ import annotations

import atexit
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
import time
import os
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class JsonlWriter:
    """
    Thread-safe JSONL writer with basic EMFILE protection and minimal stderr spam.

    Design goals:
    - Keep a single file handle open per path to avoid FD churn.
    - Fail closed on errors (drop log line) but surface errors explicitly.
    - Rate-limit error prints to avoid log storms.
    """

    def __init__(self, path: Path, error_cooldown_sec: float = 60.0,
                 max_record_bytes: int = 64 * 1024,
                 max_file_bytes: int = 1024 * 1024,
                 backup_count: int = 3) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._fh = None
        self._disable_until = 0.0
        self._last_error_ts = 0.0
        self._error_cooldown_sec = float(error_cooldown_sec)
        self.max_record_bytes = max(1, int(max_record_bytes))
        self.max_file_bytes = max(self.max_record_bytes, int(max_file_bytes))
        self.backup_count = max(0, int(backup_count))

    def close(self) -> None:
        with self._lock:
            self._close_noexcept()

    def write(self, payload: dict) -> bool:
        now = time.time()
        with self._lock:
            if now < self._disable_until:
                return False
            try:
                encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True,
                                      separators=(",", ":")) + "\n").encode("utf-8")
                if len(encoded) > self.max_record_bytes:
                    self._print_error_once(now, "record_bytes_exceeded")
                    return False
                if self._fh is None or getattr(self._fh, "closed", False):
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = self.path.open("ab")
                current = int(self._fh.tell()) if self._fh is not None else 0
                if current + len(encoded) > self.max_file_bytes:
                    self._rotate_noexcept()
                    self._fh = self.path.open("ab")
                self._fh.write(encoded)
                self._fh.flush()
                return True
            except OSError as exc:
                # EMFILE: too many open files
                if getattr(exc, "errno", None) == 24:
                    self._disable_until = now + self._error_cooldown_sec
                self._close_noexcept()
                self._print_error_once(now, f"OSError:{exc}")
                return False
            except Exception as exc:
                self._close_noexcept()
                self._print_error_once(now, f"{type(exc).__name__}:{exc}")
                return False

    def _close_noexcept(self) -> None:
        try:
            if self._fh:
                self._fh.close()
        except Exception:
            pass
        self._fh = None

    def _rotate_noexcept(self) -> None:
        self._close_noexcept()
        try:
            if self.backup_count <= 0:
                self.path.unlink(missing_ok=True)
                return
            oldest = self.path.with_name(self.path.name + f".{self.backup_count}")
            oldest.unlink(missing_ok=True)
            for index in range(self.backup_count - 1, 0, -1):
                source = self.path.with_name(self.path.name + f".{index}")
                target = self.path.with_name(self.path.name + f".{index + 1}")
                if source.exists():
                    os.replace(source, target)
            if self.path.exists():
                os.replace(self.path, self.path.with_name(self.path.name + ".1"))
        except Exception as exc:
            self._print_error_once(time.time(), f"rotation_failed:{type(exc).__name__}")

    def _print_error_once(self, now: float, msg: str) -> None:
        if (now - self._last_error_ts) >= self._error_cooldown_sec:
            logger.warning("jsonl_log_write_error path=%s err=%s", self.path, msg)
            self._last_error_ts = now


_WRITERS: Dict[str, JsonlWriter] = {}
_WRITERS_LOCK = threading.Lock()


def get_jsonl_writer(path: Path, **kwargs) -> JsonlWriter:
    key = str(Path(path))
    with _WRITERS_LOCK:
        writer = _WRITERS.get(key)
        if writer is None:
            writer = JsonlWriter(Path(path), **kwargs)
            _WRITERS[key] = writer
        return writer


def get_rotating_logger(
    name: str,
    path: Path,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    level: int = logging.INFO,
) -> logging.Logger:
    """Return a file-backed rotating logger without duplicating handlers."""

    logger_name = str(name or "").strip() or "rotating_logger"
    target = Path(path)
    file_key = str(target.resolve()) if target.is_absolute() else str(target)
    file_logger = logging.getLogger(logger_name)
    file_logger.setLevel(level)
    file_logger.propagate = False
    for handler in file_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == file_key:
            return file_logger
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        target,
        maxBytes=max(1, int(max_bytes)),
        backupCount=max(0, int(backup_count)),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    file_logger.addHandler(handler)
    return file_logger


def _close_all_writers() -> None:
    with _WRITERS_LOCK:
        for writer in list(_WRITERS.values()):
            try:
                writer.close()
            except Exception:
                pass


atexit.register(_close_all_writers)
