from __future__ import annotations

import atexit
import json
import threading
import time
from pathlib import Path
from typing import Dict


class JsonlWriter:
    """
    Thread-safe JSONL writer with basic EMFILE protection and minimal stderr spam.

    Design goals:
    - Keep a single file handle open per path to avoid FD churn.
    - Fail closed on errors (drop log line) but surface errors explicitly.
    - Rate-limit error prints to avoid log storms.
    """

    def __init__(self, path: Path, error_cooldown_sec: float = 60.0) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._fh = None
        self._disable_until = 0.0
        self._last_error_ts = 0.0
        self._error_cooldown_sec = float(error_cooldown_sec)

    def close(self) -> None:
        with self._lock:
            self._close_noexcept()

    def write(self, payload: dict) -> bool:
        now = time.time()
        with self._lock:
            if now < self._disable_until:
                return False
            try:
                if self._fh is None or getattr(self._fh, "closed", False):
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = self.path.open("a")
                self._fh.write(json.dumps(payload) + "\n")
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

    def _print_error_once(self, now: float, msg: str) -> None:
        if (now - self._last_error_ts) >= self._error_cooldown_sec:
            print(f"[LOG_WRITE_ERROR] path={self.path} err={msg}")
            self._last_error_ts = now


_WRITERS: Dict[str, JsonlWriter] = {}
_WRITERS_LOCK = threading.Lock()


def get_jsonl_writer(path: Path) -> JsonlWriter:
    key = str(Path(path))
    with _WRITERS_LOCK:
        writer = _WRITERS.get(key)
        if writer is None:
            writer = JsonlWriter(Path(path))
            _WRITERS[key] = writer
        return writer


def _close_all_writers() -> None:
    with _WRITERS_LOCK:
        for writer in list(_WRITERS.values()):
            try:
                writer.close()
            except Exception:
                pass


atexit.register(_close_all_writers)
