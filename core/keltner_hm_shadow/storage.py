from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Any

def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

class JsonlPublisher:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def append(self, row: dict) -> None:
        data = json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {"emitted_ids": [], "pending": {}}
    def save(self, state: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True, default=str) + "\n")
        os.replace(tmp, self.path)
