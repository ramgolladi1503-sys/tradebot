from __future__ import annotations

import hashlib
from pathlib import Path


def build_vwap_adapter(repo_root: Path) -> dict[str, str]:
    path = repo_root / "strategies" / "movement" / "vwap_reclaim.py"
    return {
        "path": str(path),
        "hash": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
