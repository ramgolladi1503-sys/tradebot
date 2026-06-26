import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict

class RawStore:
    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            import os
            base_dir = os.path.join("logs", "mip_raw")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, source_name: str, url: str, content: str) -> str:
        """Saves raw content with content hash, returning file path."""
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        ts = int(time.time())
        filename = f"{source_name}_{ts}_{content_hash[:8]}.txt"

        path = self.base_dir / filename
        path.write_text(content, encoding='utf-8')
        return str(path)

class EvidenceStore:
    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            import os
            base_dir = os.path.join("logs", "mip_evidence")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append_evidence(self, payload: Dict[str, Any]) -> None:
        """Appends to an NDJSON evidence log."""
        ts_date = time.strftime("%Y%m%d")
        path = self.base_dir / f"evidence_{ts_date}.jsonl"

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
