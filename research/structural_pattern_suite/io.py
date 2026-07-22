from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import canonical_json_bytes


def write_json_with_sidecar(path: Path, payload: Any) -> str:
    import hashlib

    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload)
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest

