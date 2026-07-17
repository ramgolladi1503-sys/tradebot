from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, research_id: str) -> Path:
        path = self.root / research_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, research_id: str, filename: str, payload: Any) -> tuple[Path, str]:
        path = self.run_dir(research_id) / filename
        encoded = json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8")
        path.write_bytes(encoded + b"\n")
        return path, hashlib.sha256(encoded).hexdigest()

    def read_json(self, research_id: str, filename: str) -> Any:
        return json.loads((self.run_dir(research_id) / filename).read_text(encoding="utf-8"))

    def exists(self, research_id: str, filename: str) -> bool:
        return (self.run_dir(research_id) / filename).exists()
