from __future__ import annotations

from pathlib import Path
from core.paths import ensure_dir


def ensure_parent_dir(path: Path) -> Path:
    target = Path(path).expanduser()
    ensure_dir(target.parent)
    return target
