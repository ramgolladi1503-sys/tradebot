from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol
import os

from .contracts import CanonicalEvent

try:  # Unix and macOS, which are the supported TradeBot hosts.
    import fcntl
except ImportError:  # pragma: no cover - defensive portability fallback
    fcntl = None


class EventPublisher(Protocol):
    def publish(self, event: CanonicalEvent) -> None: ...


class NoOpPublisher:
    def publish(self, event: CanonicalEvent) -> None:
        del event


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    event_id: str
    offset_before: int
    bytes_written: int


class FilePublisher:
    """Thread- and process-safe append-only JSONL publisher.

    `O_APPEND` prevents accidental overwrite. An advisory file lock prevents two
    observer processes from interleaving large JSON records. The implementation
    performs no TradeBot mutation and exposes fsync as an explicit durability
    choice rather than hiding it behind a heuristic.
    """

    def __init__(self, path: str | Path, *, fsync: bool = True, mode: int = 0o640) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._fsync = bool(fsync)
        self._mode = mode

    def publish(self, event: CanonicalEvent) -> PublishReceipt:
        encoded = (event.to_json() + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        with self._lock:
            fd = os.open(self.path, flags, self._mode)
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                offset = os.lseek(fd, 0, os.SEEK_END)
                view = memoryview(encoded)
                total = 0
                while total < len(encoded):
                    written = os.write(fd, view[total:])
                    if written <= 0:
                        raise OSError("append returned no progress")
                    total += written
                if self._fsync:
                    os.fsync(fd)
            finally:
                if fcntl is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(fd)
        return PublishReceipt(event_id=event.event_id, offset_before=offset, bytes_written=total)
