from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from .contracts import CanonicalEvent


class EventPublisher(Protocol):
    def publish(self, event: CanonicalEvent) -> bool: ...


class NoOpEventPublisher:
    def publish(self, event: CanonicalEvent) -> bool:
        del event
        return True


class FileEventPublisher:
    """Append-only JSONL publisher with idempotency and crash-safe fsync.

    This publisher is deliberately local and bounded. It never calls a broker,
    never mutates TradeBot objects, and reports failure to the caller instead of
    hiding lost evidence.
    """

    def __init__(self, root: str | Path, *, fsync: bool = True) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fsync = fsync
        self._lock = threading.Lock()
        self._seen: dict[str, set[str]] = {}

    def _paths(self, session_id: str) -> tuple[Path, Path]:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"})
        if not safe or safe != session_id:
            raise ValueError("unsafe_session_id")
        session_dir = self.root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "events.jsonl", session_dir / "event_ids.txt"

    def _load_seen(self, session_id: str, index_path: Path) -> set[str]:
        cached = self._seen.get(session_id)
        if cached is not None:
            return cached
        seen: set[str] = set()
        if index_path.exists():
            for line in index_path.read_text(encoding="utf-8").splitlines():
                value = line.strip()
                if value:
                    seen.add(value)
        self._seen[session_id] = seen
        return seen

    def publish(self, event: CanonicalEvent) -> bool:
        event_path, index_path = self._paths(event.session_id)
        record = event.to_record()
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._lock:
            seen = self._load_seen(event.session_id, index_path)
            if event.event_id in seen:
                return False
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
                handle.flush()
                if self.fsync:
                    os.fsync(handle.fileno())
            with index_path.open("a", encoding="utf-8") as handle:
                handle.write(event.event_id)
                handle.write("\n")
                handle.flush()
                if self.fsync:
                    os.fsync(handle.fileno())
            seen.add(event.event_id)
        return True

    def healthcheck(self) -> bool:
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, delete=True) as handle:
                handle.write(b"ok")
                handle.flush()
            return True
        except OSError:
            return False
