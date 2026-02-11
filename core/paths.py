from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def logs_dir() -> Path:
    override = os.getenv("LOG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / "logs"
